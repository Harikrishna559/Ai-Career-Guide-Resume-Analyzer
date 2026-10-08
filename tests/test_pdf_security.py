from io import BytesIO
from pathlib import Path

import pytest
from PyPDF2 import PdfReader

from app import app


def valid_resume_payload():
    return {
        "title": "Resume Report",
        "report_type": "resume",
        "payload": {
            "target_role": "Python Developer",
            "ats_score": 82,
            "score_breakdown": {
                "Keyword Match": 80,
                "Skills Match": 75,
                "Resume Structure": 80,
            },
            "professional_summary": "Python developer with Flask experience.",
        },
    }


def export(client, payload, route="/api/export-report"):
    return client.post(route, json=payload)


def assert_json_error(response, status, code):
    assert response.status_code == status
    assert response.is_json
    body = response.get_json()
    assert body["success"] is False
    assert body["error"]["code"] == code
    return body


@pytest.mark.parametrize("route", ["/api/export-report", "/api/generate-pdf"])
def test_both_pdf_routes_generate_valid_pdf_and_keep_download_filename(route):
    response = export(app.test_client(), valid_resume_payload(), route)

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert "resume-report.pdf" in response.headers["Content-Disposition"]
    assert response.data.startswith(b"%PDF")
    assert len(PdfReader(BytesIO(response.data)).pages) >= 1


@pytest.mark.parametrize("route", ["/api/export-report", "/api/generate-pdf"])
def test_pdf_routes_reject_malformed_and_non_object_json(route):
    client = app.test_client()
    malformed = client.post(route, data='{"title":', content_type="application/json")
    assert_json_error(malformed, 400, "INVALID_JSON")

    for payload in (["array"], "string", 42, True):
        assert_json_error(client.post(route, json=payload), 400, "INVALID_JSON")


def test_pdf_validation_rejects_missing_and_unexpected_top_level_fields():
    client = app.test_client()
    assert_json_error(export(client, {"title": "Missing payload"}), 400, "VALIDATION_ERROR")
    assert_json_error(
        export(client, {"title": "Empty report", "payload": {}}),
        400,
        "VALIDATION_ERROR",
    )
    assert_json_error(
        export(client, {**valid_resume_payload(), "unexpected": True}),
        400,
        "VALIDATION_ERROR",
    )


def test_pdf_validation_rejects_oversized_text_lists_and_payloads():
    client = app.test_client()
    payload = valid_resume_payload()
    payload["payload"]["professional_summary"] = "x" * 100_001
    assert_json_error(export(client, payload), 400, "VALIDATION_ERROR")

    payload = valid_resume_payload()
    payload["payload"]["resume_strengths"] = ["strength"] * 201
    assert_json_error(export(client, payload), 400, "VALIDATION_ERROR")

    oversized = {
        "title": "Large report",
        "report_type": "resume",
        "payload": {"resume_text": "x" * (1024 * 1024)},
    }
    assert_json_error(export(client, oversized), 413, "REQUEST_TOO_LARGE")


def test_pdf_validation_rejects_deeply_nested_report_data():
    nested = "deep"
    for _ in range(10):
        nested = {"nested": nested}
    response = export(
        app.test_client(),
        {"title": "Deep report", "report_type": "resume", "payload": {"data": nested}},
    )

    assert_json_error(response, 400, "VALIDATION_ERROR")


@pytest.mark.parametrize(
    "payload",
    [
        {"score_breakdown": []},
        {"score_breakdown": {"Keyword Match": "high"}},
        {"job_portals": ["not an object"]},
        {"study_plan": [{}]},
        {"match_result": {"score_method": {"weights": [], "available_dimensions": []}}},
        {"readiness_score": True},
        {"ats_score": 101},
    ],
)
def test_pdf_validation_rejects_malformed_nested_report_data(payload):
    request_payload = valid_resume_payload()
    request_payload["payload"].update(payload)
    response = export(app.test_client(), request_payload)

    assert_json_error(response, 400, "VALIDATION_ERROR")


def test_pdf_uses_product_truth_methodology_and_preserves_unassessed_scores():
    response = export(
        app.test_client(),
        {
            "title": "Job Match Report",
            "report_type": "job-description",
            "payload": {
                "match_score": 77,
                "match_result": {
                    "overall_match": None,
                    "skill_match": 75,
                    "experience_match": None,
                    "education_match": None,
                    "keyword_match": 60,
                    "matched_skills": ["Python"],
                    "missing_required_skills": ["Docker"],
                    "missing_preferred_skills": [],
                    "strengths": ["Matches one required skill"],
                    "gaps": ["Work experience duration could not be verified."],
                    "recommendations": ["Highlight relevant project work."],
                    "score_method": {
                        "available_dimensions": ["skill_match", "keyword_match"],
                        "weights": {"skill_match": 0.769231, "keyword_match": 0.230769},
                    },
                },
            },
        },
    )

    assert response.status_code == 200
    extracted = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(response.data)).pages)
    assert "Methodology / Score Type" in extracted
    assert "Role Keyword Estimate is a rule-based estimate" in extracted
    assert "Overall Resume" in extracted
    assert "Not assessed" in extracted
    assert "Matched Skills" in extracted
    assert "Missing Required Skills" in extracted
    assert "Highlight relevant project work." in extracted


@pytest.mark.parametrize(
    ("exception", "status", "code"),
    [
        (ValueError("private input detail"), 500, "REPORT_EXPORT_ERROR"),
        (RuntimeError("private dependency detail"), 503, "REPORT_EXPORT_UNAVAILABLE"),
    ],
)
def test_pdf_generation_errors_never_expose_internal_details(monkeypatch, exception, status, code):
    def fail_generation(*_args, **_kwargs):
        raise exception

    monkeypatch.setattr("app._build_report_pdf", fail_generation)
    response = export(app.test_client(), valid_resume_payload())

    body = assert_json_error(response, status, code)
    assert "private" not in response.get_data(as_text=True)
    assert "Traceback" not in body["error"]["message"]


def test_pdf_rejects_unsupported_content_type_with_json_error():
    response = app.test_client().post("/api/export-report", data="{}")

    assert_json_error(response, 415, "UNSUPPORTED_MEDIA_TYPE")


def test_pdf_interview_methodology_discloses_ai_and_derived_scores():
    response = export(
        app.test_client(),
        {
            "title": "Interview Report",
            "report_type": "interview",
            "payload": {
                "overall_score": 80,
                "technical": 84,
                "communication": 78,
                "problem_solving": 80,
                "project_knowledge": 79,
                "hr_readiness": 78,
                "strengths": ["Clear explanation"],
                "weaknesses": ["Add an example"],
                "weak_questions": [],
                "study_plan": [],
            },
        },
    )

    assert response.status_code == 200
    extracted = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(response.data)).pages)
    assert "Methodology / Score Type" in extracted
    assert "deterministic heuristic fallback" in extracted
    assert "locally derived estimates with a 50-point minimum" in extracted
    assert "Problem-Solving Estimate" in extracted


def test_pdf_safely_renders_xml_sensitive_unicode_and_control_characters():
    payload = valid_resume_payload()
    payload["title"] = "Report <draft> & review"
    payload["payload"]["professional_summary"] = "Python & Flask\u0000 developer 😀"
    response = export(app.test_client(), payload)

    assert response.status_code == 200
    assert response.data.startswith(b"%PDF")
    assert len(PdfReader(BytesIO(response.data)).pages) >= 1


def test_pdf_frontend_checks_http_status_and_pdf_content_type():
    source_root = Path(__file__).resolve().parents[1]
    main_script = (source_root / "static" / "js" / "main.js").read_text(encoding="utf-8")
    jd_script = (source_root / "static" / "js" / "job-description.js").read_text(encoding="utf-8")
    interview_script = (source_root / "static" / "js" / "interview.js").read_text(encoding="utf-8")

    assert "if (!response.ok)" in main_script
    assert "contentType !== 'application/pdf'" in main_script
    assert "window.readPdfResponse(response" in main_script
    assert "window.readPdfResponse(response" in jd_script
    assert "window.readPdfResponse(response" in interview_script


def test_security_headers_are_present_and_hsts_requires_production_https(monkeypatch):
    client = app.test_client()
    page = client.get("/")
    assert page.status_code == 200
    assert page.headers["X-Content-Type-Options"] == "nosniff"
    assert page.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    csp = page.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "script-src 'self' 'unsafe-inline'" not in csp
    assert "frame-ancestors 'none'" in csp
    assert page.headers["X-Frame-Options"] == "DENY"
    assert "Strict-Transport-Security" not in page.headers

    api_error = client.post("/api/export-report", json={"payload": []})
    assert api_error.status_code == 400
    assert api_error.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in api_error.headers

    monkeypatch.setitem(app.config, "APP_ENV", "production")
    secure_page = client.get("/", environ_overrides={"wsgi.url_scheme": "https"})
    assert secure_page.headers["Strict-Transport-Security"] == "max-age=31536000"
    insecure_page = client.get("/", environ_overrides={"wsgi.url_scheme": "http"})
    assert "Strict-Transport-Security" not in insecure_page.headers
