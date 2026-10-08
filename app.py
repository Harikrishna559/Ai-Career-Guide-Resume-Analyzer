import io
import json
import logging
import math
import os
import re
import secrets
import tempfile
import uuid
from html import escape
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
except ImportError:  # pragma: no cover
    letter = None
    getSampleStyleSheet = None
    Paragraph = None
    SimpleDocTemplate = None
    Spacer = None
from werkzeug.exceptions import BadRequest, HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename

from services.ats_analyzer import (
    analyze_job_description,
    analyze_resume_text,
    generate_professional_summary,
    generate_summary_versions,
    job_search_recommendations,
)
from services.career_service import build_role_library, generate_roadmap_from_profile
from services.ai import AIServiceError, create_ai_service
from services.ai.rate_limit import AIRateLimiter, trusted_proxy_count
from services.interview_service import InterviewService
from services.jd_parser import parse_job_description
from services.matching_service import match_resume_to_job
from services.resume_parser import (
    MAX_EXTRACTED_TEXT_CHARS,
    MAX_UPLOAD_BYTES,
    ResumeFileError,
    extract_text_from_resume,
    get_resume_health,
    parse_resume_details,
    parse_resume_profile,
)

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
app.config["MAX_UPLOAD_SIZE_BYTES"] = MAX_UPLOAD_BYTES
app.config["MAX_EXTRACTED_TEXT_CHARS"] = MAX_EXTRACTED_TEXT_CHARS
app.config["MAX_JOB_DESCRIPTION_CHARS"] = 50_000
app.config["MAX_PARSER_OUTPUT_BYTES"] = 1 * 1024 * 1024
app.config["MAX_REPORT_INPUT_BYTES"] = 1 * 1024 * 1024
app.config["MAX_REPORT_PDF_BYTES"] = 10 * 1024 * 1024
app.config["APP_ENV"] = (os.getenv("APP_ENV") or os.getenv("FLASK_ENV") or "development").strip().lower()
app.config["UPLOAD_FOLDER"] = str(UPLOAD_DIR)
ai_rate_limiter = AIRateLimiter.from_env()


def _configure_trusted_proxy(flask_app, raw_count):
    count = trusted_proxy_count(raw_count)
    if count:
        flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_for=count, x_proto=count)
    return count


_configure_trusted_proxy(app, os.getenv("TRUSTED_PROXY_COUNT"))


def _configure_secret_key(flask_app, environment, secret_key):
    environment = str(environment or "").strip().lower()
    if secret_key and secret_key.strip():
        flask_app.config["SECRET_KEY"] = secret_key
        return
    if environment == "development":
        flask_app.config["SECRET_KEY"] = secrets.token_hex(32)
        return
    raise RuntimeError("SECRET_KEY must be configured outside development.")


_configure_secret_key(
    app,
    app.config["APP_ENV"],
    os.getenv("SECRET_KEY"),
)
app.config["ALLOWED_EXTENSIONS"] = {"pdf", "docx", "txt"}


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'self'; object-src 'none'; "
        "frame-ancestors 'none'; form-action 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "font-src 'self' data:; connect-src 'self'"
    )
    response.headers["X-Frame-Options"] = "DENY"
    if app.config.get("APP_ENV") == "production" and request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


def json_error(status_code, code, message):
    payload = {
        "success": False,
        "error": {"code": code, "message": message},
    }
    return jsonify(payload), status_code


def _ai_rate_limit_response():
    # request.remote_addr only reflects forwarded data accepted by configured ProxyFix.
    if ai_rate_limiter.allow(request.remote_addr):
        return None
    return json_error(
        429,
        "AI_RATE_LIMIT",
        "Too many AI requests. Please try again later.",
    )


def _ai_consent_response(payload):
    consent = payload.get("ai_consent")
    if consent is True or (
        isinstance(consent, str) and consent.strip().lower() == "true"
    ):
        return None
    return json_error(
        400,
        "AI_CONSENT_REQUIRED",
        "AI processing consent is required before using this feature.",
    )


def _is_api_request():
    return request.path == "/api" or request.path.startswith("/api/")


def _get_json_payload(require_json=False):
    if not request.is_json:
        if require_json:
            return None, json_error(415, "UNSUPPORTED_MEDIA_TYPE", "Send this request with a JSON content type.")
        return {}, None
    try:
        payload = request.get_json()
    except (BadRequest, RecursionError):
        return None, json_error(400, "INVALID_JSON", "Request body must contain valid JSON.")
    if not isinstance(payload, dict):
        return None, json_error(400, "INVALID_JSON", "Request body must be a JSON object.")
    return payload, None


def _remove_temporary_upload(path):
    if not path or not os.path.exists(path):
        return
    try:
        os.remove(path)
    except OSError:
        app.logger.error("Temporary upload cleanup failed")


def _parser_output_within_limit(payload):
    return len(app.json.dumps(payload).encode("utf-8")) <= app.config["MAX_PARSER_OUTPUT_BYTES"]


def _ai_error_response(error):
    responses = {
        "AI_NOT_CONFIGURED": (503, "AI service is not configured. Please contact the administrator."),
        "AI_AUTHENTICATION_ERROR": (502, "AI service authentication failed. Please contact the administrator."),
        "AI_RATE_LIMIT": (503, "AI service is temporarily busy. Please try again later."),
        "AI_UNAVAILABLE": (502, "AI service could not be reached. Please try again."),
        "AI_INVALID_RESPONSE": (502, "AI service returned an unexpected response. Please try again."),
        "AI_PROVIDER_ERROR": (502, "AI service could not complete the request. Please try again."),
    }
    status_code, message = responses.get(
        error.code,
        (502, "AI service could not complete the request. Please try again."),
    )
    return json_error(status_code, error.code, message)


def _api_http_error(error):
    status_code = error.code or 500
    errors = {
        400: ("BAD_REQUEST", "The request could not be processed. Check the submitted data and try again."),
        404: ("NOT_FOUND", "API endpoint not found."),
        405: ("METHOD_NOT_ALLOWED", "This method is not supported for this API endpoint."),
        413: ("REQUEST_TOO_LARGE", "Request is too large. Please reduce the upload or request size and try again."),
        415: ("UNSUPPORTED_MEDIA_TYPE", "Unsupported request content type."),
    }
    code, message = errors.get(
        status_code,
        ("REQUEST_ERROR", "The API request could not be processed."),
    )
    return json_error(status_code, code, message)


REPORT_TYPES = {"resume", "job-description", "interview", "career"}
MAX_REPORT_DEPTH = 8
MAX_REPORT_NODES = 10_000
MAX_REPORT_ARRAY_ITEMS = 200
MAX_REPORT_OBJECT_FIELDS = 100
MAX_REPORT_STRING_CHARS = 100_000
MAX_REPORT_SCORE = 100

REPORT_PAYLOAD_SHAPES = {
    "resume": {
        "objects": {"score_breakdown", "resume_health", "summary_versions", "parsed_details"},
        "arrays": {
            "resume_strengths", "missing_skills", "missing_keywords", "strong_keywords",
            "priority_keywords", "certifications", "projects_to_add", "sections_to_improve",
            "recommended_searches", "job_portals",
        },
    },
    "job-description": {
        "objects": {"match_result"},
        "arrays": {
            "matched_skills", "missing_skills", "missing_keywords", "learning_plan",
            "resume_improvements", "interview_topics",
        },
    },
    "interview": {
        "objects": set(),
        "arrays": {"strengths", "weaknesses", "weak_questions", "study_plan", "results"},
    },
}

REPORT_LABELS = {
    "ats_score": "ATS Compatibility Score",
    "match_score": "Role Keyword Estimate",
    "overall_match": "Overall Resume-to-JD Match",
    "skill_match": "Skills Match",
    "experience_match": "Experience Match",
    "education_match": "Education Match",
    "keyword_match": "Keyword Match",
    "matched_skills": "Matched Skills",
    "missing_required_skills": "Missing Required Skills",
    "missing_preferred_skills": "Missing Preferred Skills",
    "readiness_score": "AI-Generated Career Readiness Estimate",
    "overall_score": "Interview Overall Score",
    "technical": "Technical Score",
    "communication": "Communication Score",
    "problem_solving": "Problem-Solving Estimate",
    "project_knowledge": "Project-Knowledge Estimate",
    "hr_readiness": "HR-Readiness Estimate",
}


def _validate_report_tree(value, *, depth=0, counter=None, key=None):
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > MAX_REPORT_NODES or depth > MAX_REPORT_DEPTH:
        raise ValueError("Report data exceeds supported complexity.")

    if value is None or isinstance(value, str):
        if isinstance(value, str) and len(value) > MAX_REPORT_STRING_CHARS:
            raise ValueError("Report text exceeds the supported length.")
        return
    if isinstance(value, bool):
        if key and "score" in key:
            raise ValueError("Report scores must be numeric or unassessed.")
        return
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Report numbers must be finite.")
        if key and ("score" in key or key in {"technical", "communication", "problem_solving", "project_knowledge", "hr_readiness"}):
            if not 0 <= value <= MAX_REPORT_SCORE:
                raise ValueError("Report scores must be between 0 and 100.")
        return
    if isinstance(value, list):
        if len(value) > MAX_REPORT_ARRAY_ITEMS:
            raise ValueError("Report list exceeds the supported number of items.")
        for item in value:
            _validate_report_tree(item, depth=depth + 1, counter=counter)
        return
    if isinstance(value, dict):
        if len(value) > MAX_REPORT_OBJECT_FIELDS:
            raise ValueError("Report object contains too many fields.")
        for child_key, child_value in value.items():
            if not isinstance(child_key, str) or len(child_key) > 100:
                raise ValueError("Report field name is invalid.")
            _validate_report_tree(child_value, depth=depth + 1, counter=counter, key=child_key)
        return
    raise ValueError("Report data contains an unsupported value.")


def _validate_report_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Report payload must be a JSON object.")
    if not payload:
        raise ValueError("Report payload must contain report data.")
    shape = REPORT_PAYLOAD_SHAPES
    for field in shape["resume"]["objects"] | shape["job-description"]["objects"]:
        if field in payload and not isinstance(payload[field], dict):
            raise ValueError(f"Report field {field} must be an object.")
    for field in shape["resume"]["arrays"] | shape["job-description"]["arrays"] | shape["interview"]["arrays"]:
        if field in payload and not isinstance(payload[field], list):
            raise ValueError(f"Report field {field} must be an array.")
    for field in (
        shape["resume"]["arrays"] - {"job_portals"}
        | shape["job-description"]["arrays"]
        | {"strengths", "weaknesses"}
    ):
        if field in payload and any(not isinstance(item, str) for item in payload[field]):
            raise ValueError(f"Report field {field} must contain text items.")
    score_breakdown = payload.get("score_breakdown")
    if isinstance(score_breakdown, dict) and any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= MAX_REPORT_SCORE
        for value in score_breakdown.values()
    ):
        raise ValueError("Report field score_breakdown must contain scores from 0 to 100.")
    for field in ("resume_health", "summary_versions"):
        nested = payload.get(field)
        if isinstance(nested, dict) and any(not isinstance(value, (str, type(None))) for value in nested.values()):
            raise ValueError(f"Report field {field} contains an invalid value.")
    if "job_portals" in payload and any(
        not isinstance(item, dict)
        or not {"portal_name", "why", "url"}.issubset(item)
        or any(not isinstance(item[field], str) for field in ("portal_name", "why", "url"))
        for item in payload["job_portals"]
    ):
        raise ValueError("Report field job_portals must contain complete portal objects.")
    if "match_result" in payload:
        match_result = payload["match_result"]
        for field in ("matched_skills", "missing_required_skills", "missing_preferred_skills", "strengths", "gaps", "recommendations"):
            if field in match_result and (
                not isinstance(match_result[field], list)
                or any(not isinstance(item, str) for item in match_result[field])
            ):
                raise ValueError(f"Match result field {field} must be a list of strings.")
        score_method = match_result.get("score_method")
        if score_method is not None and (
            not isinstance(score_method, dict)
            or not isinstance(score_method.get("weights", {}), dict)
            or not isinstance(score_method.get("available_dimensions", []), list)
            or any(not isinstance(name, str) for name in score_method.get("available_dimensions", []))
            or any(
                not isinstance(weight, (int, float))
                or isinstance(weight, bool)
                or not math.isfinite(weight)
                or not 0 <= weight <= 1
                for weight in score_method.get("weights", {}).values()
            )
        ):
            raise ValueError("Match result score_method must contain an object of weights and a list of dimensions.")
    for field in ("weak_questions", "study_plan", "results"):
        if field in payload and any(not isinstance(item, dict) for item in payload[field]):
            raise ValueError(f"Report field {field} must contain objects.")
    for field, required in {
        "weak_questions": {"question"},
        "study_plan": {"day", "topic", "why", "task"},
        "results": {"question", "category", "score", "evaluation"},
    }.items():
        if field in payload and any(not required.issubset(item) for item in payload[field]):
            raise ValueError(f"Report field {field} contains an incomplete item.")
    for item in payload.get("weak_questions", []):
        if not isinstance(item["question"], str):
            raise ValueError("Interview weak-question text must be a string.")
    for item in payload.get("study_plan", []):
        if (
            isinstance(item["day"], bool)
            or not isinstance(item["day"], int)
            or any(not isinstance(item[field], str) for field in ("topic", "why", "task"))
        ):
            raise ValueError("Interview study-plan items have invalid fields.")
    for item in payload.get("results", []):
        if (
            not isinstance(item["question"], str)
            or not isinstance(item["category"], str)
            or isinstance(item["score"], bool)
            or not isinstance(item["score"], (int, float))
            or not isinstance(item["evaluation"], dict)
        ):
            raise ValueError("Interview result items have invalid fields.")
    for field in ("ats_score", "match_score", "overall_match", "skill_match", "experience_match",
                  "education_match", "keyword_match", "readiness_score", "overall_score",
                  "technical", "communication", "problem_solving", "project_knowledge", "hr_readiness"):
        score = payload.get(field)
        if score is not None and (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
            or not 0 <= score <= MAX_REPORT_SCORE
        ):
            raise ValueError(f"Report score {field} must be between 0 and 100 or unassessed.")
    _validate_report_tree(payload)


def _validate_export_request(payload):
    if set(payload) - {"title", "report_type", "payload"}:
        raise ValueError("Request contains unexpected fields.")
    title = payload.get("title", "Career Guide Report")
    report_type = payload.get("report_type", "resume")
    report_data = payload.get("payload")
    if not isinstance(title, str) or len(title) > 200:
        raise ValueError("Report title must be text of 200 characters or fewer.")
    if not isinstance(report_type, str):
        raise ValueError("Report type is not supported.")
    report_type = report_type.strip() or "resume"
    if report_type not in REPORT_TYPES:
        raise ValueError("Report type is not supported.")
    _validate_report_payload(report_data)
    return title.strip() or "Career Guide Report", report_type, report_data


def _report_methodology(report_type, payload):
    if report_type == "resume" and ("ats_score" in payload or "score_breakdown" in payload):
        return (
            "ATS Compatibility Score is a rule-based estimate, not an official company ATS score. "
            "Role-keyword categories vary with the selected role; several other categories use fixed baselines."
        )
    if report_type == "job-description":
        notes = []
        if "match_score" in payload:
            notes.append("Role Keyword Estimate is a rule-based estimate, not AI-generated.")
        match = payload.get("match_result")
        if isinstance(match, dict):
            notes.append(
                "Structured resume-to-JD dimensions are deterministic. Unavailable dimensions remain unassessed; "
                "available dimensions are reweighted for the overall match estimate."
            )
        return " ".join(notes)
    if report_type == "interview":
        return (
            "Per-answer scores may come from a valid AI evaluation or the deterministic heuristic fallback. "
            "Problem-solving, project-knowledge, and HR-readiness values are locally derived estimates with a "
            "50-point minimum; the overall score averages the reported categories."
        )
    if report_type == "career" and "readiness_score" in payload:
        return "Career readiness is an AI-generated estimate, not a validated hiring or placement prediction."
    return ""


def _pdf_safe_text(value):
    text = str(value)
    xml_safe = "".join(
        character if character in "\t\n\r" or ord(character) >= 32 and not 0xD800 <= ord(character) <= 0xDFFF else "\uFFFD"
        for character in text
    )
    return xml_safe.encode("cp1252", errors="replace").decode("cp1252")


def _append_pdf_field(story, label, value, styles, depth=0):
    label = REPORT_LABELS.get(label, label.replace("_", " ").replace("-", " ").title())
    prefix = "  " * min(depth, MAX_REPORT_DEPTH)
    if value is None:
        text = "Not assessed"
    elif isinstance(value, dict):
        if not value:
            text = "No details provided"
            story.append(Paragraph(f"{prefix}<b>{escape(_pdf_safe_text(label))}:</b> {escape(text)}", styles["BodyText"]))
            story.append(Spacer(1, 5))
            return
        story.append(Paragraph(f"{prefix}<b>{escape(_pdf_safe_text(label))}</b>", styles["Heading3"] if depth == 0 else styles["Heading4"]))
        for child_key, child_value in value.items():
            _append_pdf_field(story, child_key, child_value, styles, depth + 1)
        return
    elif isinstance(value, list):
        if not value:
            text = "None"
            story.append(Paragraph(f"{prefix}<b>{escape(_pdf_safe_text(label))}:</b> {escape(text)}", styles["BodyText"]))
            story.append(Spacer(1, 5))
            return
        story.append(Paragraph(f"{prefix}<b>{escape(_pdf_safe_text(label))}</b>", styles["Heading3"] if depth == 0 else styles["Heading4"]))
        for index, item in enumerate(value, start=1):
            _append_pdf_field(story, f"Item {index}", item, styles, depth + 1)
        return
    elif isinstance(value, bool):
        text = "Yes" if value else "No"
    elif isinstance(value, float):
        text = str(int(value)) if value.is_integer() else f"{value:g}"
    else:
        text = value

    safe_text = _pdf_safe_text(text)
    story.append(Paragraph(f"{prefix}<b>{escape(_pdf_safe_text(label))}:</b> {escape(safe_text)}", styles["BodyText"]))
    story.append(Spacer(1, 5))


def _build_report_pdf(title, payload):
    if SimpleDocTemplate is None or getSampleStyleSheet is None or Paragraph is None or Spacer is None:
        raise RuntimeError("PDF export dependency is not installed.")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    styles["BodyText"].wordWrap = "CJK"
    story = [Paragraph(escape(_pdf_safe_text(title)), styles["Title"]), Spacer(1, 18)]

    if isinstance(payload, dict):
        report_type = payload.get("report_type", "resume")
        methodology = _report_methodology(report_type, payload)
        if methodology:
            story.extend([
                Paragraph("Methodology / Score Type", styles["Heading2"]),
                Paragraph(escape(_pdf_safe_text(methodology)), styles["BodyText"]),
                Spacer(1, 12),
            ])
        for key, value in payload.items():
            if key != "report_type":
                _append_pdf_field(story, key, value, styles)
    else:
        _append_pdf_field(story, "Report", payload, styles)

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


@app.route("/")
def index():
    role_library = build_role_library()
    return render_template("index.html", roles=role_library)


@app.route("/career-guide")
def career_guide_page():
    role_library = build_role_library()
    return render_template("career-guide.html", roles=role_library)


@app.route("/career-result")
def career_result_page():
    return render_template("career-result.html")


@app.route("/resume-analyzer")
def resume_analyzer_page():
    return render_template("resume-analyzer.html")


@app.route("/resume-result")
def resume_result_page():
    return render_template("resume-result.html")


@app.route("/job-description")
def job_description_page():
    role_library = build_role_library()
    return render_template("job-description.html", roles=role_library)


@app.route("/job-description-result")
def job_description_result_page():
    return render_template("job-description-result.html")


@app.route("/dashboard")
def dashboard_page():
    return render_template("dashboard.html")


@app.route("/interview-simulator")
def interview_simulator_page():
    return render_template("interview-simulator.html")


@app.route("/health")
def health_check_simple():
    return jsonify({"status": "ok"})


@app.route("/api/health")
def health_check():
    try:
        configured = create_ai_service().is_configured()
        return jsonify({
            "status": "ok",
            "gemini_configured": configured,
            "service": "career-guide-resume-analyzer",
        })
    except AIServiceError as exc:
        return _ai_error_response(exc)


@app.route("/api/roles")
def role_library_route():
    return jsonify({"success": True, "roles": build_role_library()})


@app.route("/api/career-plan", methods=["POST"])
def career_plan():
    payload, error_response = _get_json_payload(require_json=True)
    if error_response:
        return error_response
    consent_response = _ai_consent_response(payload)
    if consent_response:
        return consent_response

    name = (payload.get("name") or "").strip()
    target_role = (payload.get("target_role") or "").strip()
    current_skills = (payload.get("current_skills") or "").strip()
    experience_level = (payload.get("experience_level") or "").strip()
    hours_per_day = payload.get("hours_per_day")
    preferred_learning_style = (payload.get("preferred_learning_style") or "").strip()
    career_goal = (payload.get("career_goal") or "").strip()

    if not name:
        return json_error(400, "VALIDATION_ERROR", "Name cannot be empty.")
    if not target_role:
        return json_error(400, "VALIDATION_ERROR", "Target role cannot be empty.")
    if not current_skills:
        return json_error(400, "VALIDATION_ERROR", "Current skills cannot be empty.")
    if not experience_level:
        return json_error(400, "VALIDATION_ERROR", "Experience level is required.")
    try:
        hours = int(hours_per_day)
    except (TypeError, ValueError):
        return json_error(400, "VALIDATION_ERROR", "Hours per day must be a valid number.")
    if hours < 1 or hours > 12:
        return json_error(400, "VALIDATION_ERROR", "Hours per day must be between 1 and 12.")

    rate_limit_response = _ai_rate_limit_response()
    if rate_limit_response:
        return rate_limit_response

    try:
        ai_service = create_ai_service()
        result = ai_service.generate_career_plan({
            "name": name,
            "target_role": target_role,
            "current_skills": current_skills,
            "experience_level": experience_level,
            "hours_per_day": hours,
            "preferred_learning_style": preferred_learning_style,
            "career_goal": career_goal,
        })
        return jsonify({"success": True, **result})
    except AIServiceError as exc:
        return _ai_error_response(exc)
    except Exception:
        return json_error(500, "AI_PROVIDER_ERROR", "We couldn't generate your career plan. Please try again.")


@app.route("/api/analyze-resume", methods=["POST"])
def analyze_resume():
    file = request.files.get("resume")
    if not file:
        return json_error(400, "UPLOAD_ERROR", "Please upload a resume in PDF, DOCX, or TXT format.")
    target_role = request.form.get("target_role")
    if not isinstance(target_role, str) or not target_role.strip():
        return json_error(400, "VALIDATION_ERROR", "Target role cannot be empty.")
    target_role = target_role.strip()
    if len(target_role) > 200:
        return json_error(400, "VALIDATION_ERROR", "Target role is too long.")

    allowed = app.config["ALLOWED_EXTENSIONS"]
    filename = secure_filename(file.filename or "")
    if not filename:
        return json_error(400, "UPLOAD_ERROR", "Resume file is missing.")
    extension = Path(filename).suffix.lower().lstrip(".")
    if extension not in allowed:
        return json_error(400, "UPLOAD_ERROR", "Unsupported file type. Please upload a PDF, DOCX, or TXT file.")
    if len(filename) > 255:
        return json_error(400, "UPLOAD_ERROR", "The uploaded file name is invalid.")

    temp_path = None
    try:
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        temp_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
        file.save(temp_path)

        raw_text = extract_text_from_resume(temp_path)
        if len(raw_text) > app.config["MAX_EXTRACTED_TEXT_CHARS"]:
            raise ResumeFileError

        parsed = parse_resume_details(raw_text)
        ats_result = analyze_resume_text(raw_text, target_role, parsed)
        summary_versions = generate_summary_versions(raw_text, target_role, parsed)
        summary = generate_professional_summary(raw_text, target_role, parsed)
        health = get_resume_health(raw_text, parsed)

        response = {
            "success": True,
            "resume_text": raw_text,
            "target_role": target_role,
            "ats_score": ats_result["ats_score"],
            "score_breakdown": ats_result["score_breakdown"],
            "resume_strengths": ats_result["resume_strengths"],
            "missing_skills": ats_result["missing_skills"],
            "missing_keywords": ats_result["missing_keywords"],
            "strong_keywords": ats_result["strong_keywords"],
            "priority_keywords": ats_result["priority_keywords"],
            "professional_summary": summary,
            "summary_versions": summary_versions,
            "certifications": ats_result["certifications"],
            "projects_to_add": ats_result["projects_to_add"],
            "sections_to_improve": ats_result["sections_to_improve"],
            "job_portals": ats_result["job_portals"],
            "recommended_searches": job_search_recommendations(target_role),
            "resume_health": health,
            "parsed_details": parsed,
        }
        if not _parser_output_within_limit(response):
            raise ResumeFileError
        return jsonify(response)
    except ResumeFileError:
        return json_error(400, "INVALID_FILE", "The uploaded file could not be processed safely.")
    except Exception:
        return json_error(500, "RESUME_ANALYSIS_ERROR", "We couldn't analyze this resume. Please try another file.")
    finally:
        _remove_temporary_upload(temp_path)


@app.route("/api/improve-summary", methods=["POST"])
def improve_summary():
    payload, error_response = _get_json_payload(require_json=True)
    if error_response:
        return error_response
    resume_text = (payload.get("resume_text") or "").strip()
    target_role = (payload.get("target_role") or "").strip()
    experience = (payload.get("experience") or "").strip()

    if not resume_text:
        return json_error(400, "VALIDATION_ERROR", "Resume text is required to generate a professional summary.")
    if not target_role:
        return json_error(400, "VALIDATION_ERROR", "Target role cannot be empty.")

    summary = generate_professional_summary(resume_text, target_role, {"experience": experience})
    return jsonify({"success": True, "summary": summary})


def _improve_resume_bullet(bullet, target_role=""):
    normalized = (bullet or "").strip()
    if not normalized:
        raise ValueError("Bullet text is required to improve it.")
    cleaned = re.sub(r"\s+", " ", normalized).strip()
    cleaned = cleaned.rstrip(".")

    if not re.match(r"^(Built|Developed|Designed|Implemented|Optimized|Led|Created|Delivered|Improved|Managed|Scaled)\b", cleaned, flags=re.IGNORECASE):
        cleaned = f"Developed {cleaned}"

    if target_role and "data" in target_role.lower() and "model" not in cleaned.lower() and any(token in cleaned.lower() for token in ["analysis", "pipeline", "dashboard", "forecast", "insights"]):
        cleaned = f"{cleaned} to drive data-informed decisions."
    elif target_role and "python" in target_role.lower() and "api" not in cleaned.lower() and any(token in cleaned.lower() for token in ["flask", "fastapi", "sql", "database"]):
        cleaned = f"{cleaned} to support scalable backend functionality."
    elif target_role and "frontend" in target_role.lower() and "ui" not in cleaned.lower() and any(token in cleaned.lower() for token in ["html", "css", "javascript", "react"]):
        cleaned = f"{cleaned} to improve the user experience."
    else:
        cleaned = f"{cleaned} to improve delivery and business impact."

    return cleaned.rstrip(".") + "."


@app.route("/api/improve-bullet", methods=["POST"])
def improve_bullet():
    payload, error_response = _get_json_payload()
    if error_response:
        return error_response
    bullet = (payload.get("bullet") or "").strip() or (request.form.get("bullet") or "").strip()
    target_role = (payload.get("target_role") or "").strip() or (request.form.get("target_role") or "").strip()

    if not bullet:
        return json_error(400, "VALIDATION_ERROR", "Bullet text is required to improve it.")

    try:
        improved_bullet = _improve_resume_bullet(bullet, target_role)
        return jsonify({"success": True, "improved_bullet": improved_bullet, "target_role": target_role})
    except ValueError as exc:
        return json_error(400, "VALIDATION_ERROR", str(exc))
    except Exception:
        return json_error(500, "BULLET_IMPROVEMENT_ERROR", "We couldn't improve this bullet. Please try again.")


@app.route("/api/analyze-job-description", methods=["POST"])
@app.route("/api/analyze-jd", methods=["POST"])
def analyze_job_description_route():
    payload, error_response = _get_json_payload()
    if error_response:
        return error_response
    job_description = payload.get("job_description") or request.form.get("job_description") or ""
    target_role = payload.get("target_role") or request.form.get("target_role") or ""
    resume_text = payload.get("resume_text") or request.form.get("resume_text") or ""
    if not all(isinstance(value, str) for value in (job_description, target_role, resume_text)):
        return json_error(400, "VALIDATION_ERROR", "Job description, target role, and resume text must be text.")
    job_description = job_description.strip()
    target_role = target_role.strip()
    resume_text = resume_text.strip()

    if not job_description:
        return json_error(400, "VALIDATION_ERROR", "Job description cannot be empty.")
    if not target_role:
        return json_error(400, "VALIDATION_ERROR", "Target role cannot be empty.")
    if (
        len(job_description) > app.config["MAX_JOB_DESCRIPTION_CHARS"]
        or len(resume_text) > app.config["MAX_EXTRACTED_TEXT_CHARS"]
        or len(target_role) > 200
    ):
        return json_error(400, "INVALID_FILE", "The submitted document could not be processed safely.")

    parsed = parse_resume_details(resume_text) if resume_text else {}
    result = analyze_job_description(job_description, target_role, parsed)
    response = {"success": True, **result}
    if resume_text:
        resume_profile = parse_resume_profile(resume_text)
        jd_profile = parse_job_description(job_description)
        response["match_result"] = match_resume_to_job(resume_profile, jd_profile)
    if not _parser_output_within_limit(response):
        return json_error(400, "INVALID_FILE", "The submitted document could not be processed safely.")
    return jsonify(response)


@app.route("/api/export-report", methods=["POST"])
@app.route("/api/generate-pdf", methods=["POST"])
def export_report():
    if request.content_length is not None and request.content_length > app.config["MAX_REPORT_INPUT_BYTES"]:
        return json_error(413, "REQUEST_TOO_LARGE", "Report request is too large. Please reduce the report data and try again.")
    payload, error_response = _get_json_payload(require_json=True)
    if error_response:
        return error_response
    try:
        title, report_type, report_data = _validate_export_request(payload)
        serialized = app.json.dumps(payload, ensure_ascii=True).encode("utf-8")
        if len(serialized) > app.config["MAX_REPORT_INPUT_BYTES"]:
            return json_error(413, "REQUEST_TOO_LARGE", "Report request is too large. Please reduce the report data and try again.")
    except (ValueError, TypeError, UnicodeError):
        return json_error(400, "VALIDATION_ERROR", "Report data is invalid or exceeds the supported limits.")

    try:
        pdf_bytes = _build_report_pdf(title, {**report_data, "report_type": report_type})
    except RuntimeError:
        return json_error(503, "REPORT_EXPORT_UNAVAILABLE", "PDF export is temporarily unavailable. Please try again later.")
    except Exception:
        return json_error(500, "REPORT_EXPORT_ERROR", "The report could not be generated. Please review the report data and try again.")
    if not pdf_bytes.startswith(b"%PDF"):
        return json_error(500, "REPORT_EXPORT_ERROR", "The report could not be generated. Please try again.")
    if len(pdf_bytes) > app.config["MAX_REPORT_PDF_BYTES"]:
        return json_error(413, "REPORT_TOO_LARGE", "The generated report is too large to download.")
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{report_type}-report.pdf",
    )


@app.route("/api/interview/start", methods=["POST"])
def interview_start():
    payload, error_response = _get_json_payload()
    if error_response:
        return error_response
    if not payload:
        payload = {key: request.form.get(key) for key in request.form.keys()}
    consent_response = _ai_consent_response(payload)
    if consent_response:
        return consent_response

    if request.files.get("resume"):
        resume_file = request.files.get("resume")
        filename = secure_filename(resume_file.filename or "")
        if not filename:
            return json_error(400, "UPLOAD_ERROR", "Resume file is missing.")
        extension = Path(filename).suffix.lower().lstrip(".")
        if extension not in app.config["ALLOWED_EXTENSIONS"]:
            return json_error(400, "UPLOAD_ERROR", "Unsupported resume file type. Please upload PDF, DOCX, or TXT.")
        if len(filename) > 255:
            return json_error(400, "UPLOAD_ERROR", "The uploaded file name is invalid.")
        temp_path = None
        try:
            unique_name = f"{uuid.uuid4().hex}_{filename}"
            temp_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
            resume_file.save(temp_path)
            payload["resume_text"] = extract_text_from_resume(temp_path)
        except ResumeFileError:
            return json_error(400, "INVALID_FILE", "The uploaded file could not be processed safely.")
        except Exception:
            return json_error(400, "INVALID_FILE", "The uploaded file could not be processed safely.")
        finally:
            _remove_temporary_upload(temp_path)

    resume_text = payload.get("resume_text") or ""
    job_description = payload.get("job_description") or ""
    if not isinstance(resume_text, str) or not isinstance(job_description, str):
        return json_error(400, "VALIDATION_ERROR", "Resume and job description content must be text.")
    if (
        len(resume_text) > app.config["MAX_EXTRACTED_TEXT_CHARS"]
        or len(job_description) > app.config["MAX_JOB_DESCRIPTION_CHARS"]
    ):
        return json_error(400, "INVALID_FILE", "The submitted document could not be processed safely.")

    try:
        service = InterviewService()
        config = service.validate_setup({
            "target_role": payload.get("target_role") or payload.get("role"),
            "custom_role": payload.get("custom_role"),
            "experience_level": payload.get("experience_level"),
            "interview_type": payload.get("interview_type"),
            "difficulty": payload.get("difficulty"),
            "question_count": payload.get("question_count"),
        })
        rate_limit_response = _ai_rate_limit_response()
        if rate_limit_response:
            return rate_limit_response
        questions = service.generate_questions(config, resume_text=resume_text, job_description=job_description)
        return jsonify({"success": True, "config": config, "questions": questions, "total_questions": len(questions)})
    except ValueError as exc:
        if str(exc) == "Malformed AI JSON.":
            return json_error(502, "AI_INVALID_RESPONSE", "AI service returned an unexpected response. Please try again.")
        return json_error(400, "VALIDATION_ERROR", str(exc))
    except AIServiceError as exc:
        return _ai_error_response(exc)


@app.route("/api/interview/evaluate", methods=["POST"])
def interview_evaluate():
    payload, error_response = _get_json_payload(require_json=True)
    if error_response:
        return error_response
    consent_response = _ai_consent_response(payload)
    if consent_response:
        return consent_response
    question = payload.get("question") or ""
    answer = payload.get("answer") or ""
    target_role = (payload.get("target_role") or "Python Developer").strip() or "Python Developer"
    experience_level = (payload.get("experience_level") or "Fresher").strip() or "Fresher"
    interview_type = (payload.get("interview_type") or "Technical").strip() or "Technical"
    difficulty = (payload.get("difficulty") or "Beginner").strip() or "Beginner"

    try:
        service = InterviewService()
        cleaned_answer = service.validate_answer(answer)
        rate_limit_response = _ai_rate_limit_response()
        if rate_limit_response:
            return rate_limit_response
        context = {key: value for key, value in payload.items() if key != "ai_consent"}
        evaluation = service.evaluate_answer(
            question,
            cleaned_answer,
            target_role,
            experience_level,
            interview_type,
            difficulty,
            context,
        )
        return jsonify({"success": True, "evaluation": evaluation})
    except ValueError as exc:
        return json_error(400, "VALIDATION_ERROR", str(exc))
    except AIServiceError as exc:
        return _ai_error_response(exc)


@app.route("/api/interview/next", methods=["POST"])
def interview_next():
    payload, error_response = _get_json_payload(require_json=True)
    if error_response:
        return error_response
    questions = payload.get("questions") or []
    current_index = int(payload.get("current_index") or 0)
    next_index = current_index + 1
    if next_index >= len(questions):
        return jsonify({"success": True, "question": None, "next_index": next_index, "is_last": True})
    return jsonify({"success": True, "question": questions[next_index], "next_index": next_index, "is_last": False})


@app.route("/api/interview/final-report", methods=["POST"])
def interview_final_report():
    payload, error_response = _get_json_payload(require_json=True)
    if error_response:
        return error_response
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return json_error(400, "VALIDATION_ERROR", "Interview results are required to generate the final report.")
    if len(results) > 15:
        return json_error(400, "VALIDATION_ERROR", "Interview results must contain no more than 15 evaluated answers.")
    for result in results:
        if not isinstance(result, dict):
            return json_error(400, "VALIDATION_ERROR", "Interview results contain an invalid evaluated answer.")
        evaluation = result.get("evaluation")
        score = evaluation.get("overall_score") if isinstance(evaluation, dict) else None
        result_score = result.get("score", score)
        if (
            not isinstance(result.get("question"), str)
            or not result["question"].strip()
            or isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not 0 <= score <= 100
            or not math.isfinite(score)
            or isinstance(result_score, bool)
            or not isinstance(result_score, (int, float))
            or not 0 <= result_score <= 100
            or not math.isfinite(result_score)
        ):
            return json_error(400, "VALIDATION_ERROR", "Interview results contain an invalid evaluated answer.")

    score_fields = ("overall_score", "technical", "communication", "problem_solving", "project_knowledge", "hr_readiness")
    for field in score_fields:
        score = payload.get(field)
        if score is not None and (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not 0 <= score <= 100
            or not math.isfinite(score)
        ):
            return json_error(400, "VALIDATION_ERROR", "Interview report contains an invalid score.")
    for field in ("strengths", "weaknesses"):
        value = payload.get(field)
        if value is not None and (
            not isinstance(value, list)
            or any(not isinstance(item, str) for item in value)
        ):
            return json_error(400, "VALIDATION_ERROR", "Interview report contains invalid feedback.")
    for field in ("weak_questions", "study_plan"):
        value = payload.get(field)
        if value is not None and (
            not isinstance(value, list)
            or any(not isinstance(item, dict) for item in value)
        ):
            return json_error(400, "VALIDATION_ERROR", "Interview report contains invalid recommendations.")

    service = InterviewService()
    base_report = {
        'overall_score': payload.get('overall_score'),
        'technical': payload.get('technical', 0),
        'communication': payload.get('communication', 0),
        'problem_solving': payload.get('problem_solving', 0),
        'project_knowledge': payload.get('project_knowledge', 0),
        'hr_readiness': payload.get('hr_readiness', 0),
        'strengths': payload.get('strengths') or [],
        'weaknesses': payload.get('weaknesses') or [],
        'weak_questions': payload.get('weak_questions') or [],
        'study_plan': payload.get('study_plan') or [],
    }
    report = service.build_final_report(base_report)
    return jsonify({"success": True, "report": report})


@app.route("/api/interview/retry", methods=["POST"])
def interview_retry():
    payload, error_response = _get_json_payload(require_json=True)
    if error_response:
        return error_response
    weak_questions = payload.get("weak_questions") or []
    try:
        questions = InterviewService().retry_weak_questions(weak_questions)
        return jsonify({"success": True, "questions": questions})
    except ValueError as exc:
        return json_error(400, "VALIDATION_ERROR", str(exc))


@app.errorhandler(404)
def page_not_found(error):
    if _is_api_request():
        return _api_http_error(error)
    return render_template("error.html", message="The page you requested does not exist."), 404


@app.errorhandler(HTTPException)
def handle_http_exception(error):
    if _is_api_request():
        return _api_http_error(error)
    return render_template("error.html", message=error.description), error.code


@app.errorhandler(Exception)
def handle_exception(error):
    if _is_api_request():
        return json_error(500, "INTERNAL_SERVER_ERROR", "Something went wrong while processing your request. Please try again.")
    logging.exception("Unhandled app error: %s", error)
    return render_template("error.html", message="Something went wrong on the server. Please try again."), 500


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
