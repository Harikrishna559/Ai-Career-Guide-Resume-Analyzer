from io import BytesIO
from pathlib import Path
import zipfile

import pytest
from docx import Document
from reportlab.pdfgen import canvas

import app as app_module
from app import app
from services.resume_parser import MAX_EXTRACTED_TEXT_CHARS


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setitem(app.config, "UPLOAD_FOLDER", str(tmp_path))
    return app.test_client()


def pdf_bytes(text="Python developer with Flask and SQL"):
    output = BytesIO()
    pdf = canvas.Canvas(output)
    pdf.drawString(72, 720, text)
    pdf.save()
    return output.getvalue()


def docx_bytes(text="Python developer with Flask and SQL"):
    document = Document()
    document.add_paragraph(text)
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def upload_resume(client, content, filename="resume.txt"):
    return client.post(
        "/api/analyze-resume",
        data={"target_role": "Python Developer", "resume": (BytesIO(content), filename)},
        content_type="multipart/form-data",
    )


@pytest.mark.parametrize(
    ("content", "filename"),
    [
        (b"Python developer with Flask, SQL, and API experience.", "resume.txt"),
        (pdf_bytes(), "resume.pdf"),
        (docx_bytes(), "resume.docx"),
    ],
    ids=["txt", "pdf", "docx"],
)
def test_supported_resume_formats_are_analyzed_and_temporary_files_removed(client, content, filename):
    response = upload_resume(client, content, filename)

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert response.get_json()["ats_score"] > 0
    assert list(Path(app.config["UPLOAD_FOLDER"]).iterdir()) == []


@pytest.mark.parametrize(
    ("content", "filename"),
    [
        (b"not pdf", "resume.pdf"),
        (b"not a docx", "resume.docx"),
        (pdf_bytes(), "resume.txt"),
        (b"plain text", "resume.docx"),
        (b"\x00\x01binary", "resume.txt"),
        (b"", "resume.txt"),
        (b"x" * (MAX_EXTRACTED_TEXT_CHARS + 1), "resume.txt"),
        (b"%PDF-1.7 malformed", "resume.pdf"),
        (b"PK\x03\x04malformed archive", "resume.docx"),
    ],
    ids=["fake-pdf", "fake-docx", "pdf-as-txt", "text-as-docx", "binary-txt", "empty", "text-limit", "malformed-pdf", "malformed-docx"],
)
def test_invalid_or_excessive_uploads_return_safe_error_and_cleanup(client, content, filename):
    response = upload_resume(client, content, filename)

    assert response.status_code == 400
    assert response.get_json() == {
        "success": False,
        "error": {
            "code": "INVALID_FILE",
            "message": "The uploaded file could not be processed safely.",
        },
    }
    assert list(Path(app.config["UPLOAD_FOLDER"]).iterdir()) == []


def test_oversized_docx_document_xml_is_rejected_before_document_parser(client):
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<" + ("x" * (10 * 1024 * 1024)))

    response = upload_resume(client, output.getvalue(), "resume.docx")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_FILE"
    assert list(Path(app.config["UPLOAD_FOLDER"]).iterdir()) == []


def test_docx_extracted_text_limit_is_enforced(client):
    response = upload_resume(
        client,
        docx_bytes("x" * (MAX_EXTRACTED_TEXT_CHARS + 1)),
        "resume.docx",
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_FILE"
    assert list(Path(app.config["UPLOAD_FOLDER"]).iterdir()) == []


def test_pdf_page_limit_is_enforced(client):
    output = BytesIO()
    pdf = canvas.Canvas(output)
    for _ in range(26):
        pdf.drawString(72, 720, "Python developer")
        pdf.showPage()
    pdf.save()

    response = upload_resume(client, output.getvalue(), "resume.pdf")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_FILE"
    assert list(Path(app.config["UPLOAD_FOLDER"]).iterdir()) == []


def test_resume_parser_failure_returns_safe_error_and_cleans_temporary_file(client, monkeypatch):
    def fail_parser(_path):
        raise RuntimeError("C:\\private\\resume.txt secret details")

    monkeypatch.setattr(app_module, "extract_text_from_resume", fail_parser)
    response = upload_resume(client, b"valid text", "resume.txt")

    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "RESUME_ANALYSIS_ERROR"
    assert "private" not in response.get_data(as_text=True)
    assert "secret details" not in response.get_data(as_text=True)
    assert list(Path(app.config["UPLOAD_FOLDER"]).iterdir()) == []


def test_resume_analysis_failure_cleans_temporary_file(client, monkeypatch):
    def fail_analysis(*_args, **_kwargs):
        raise RuntimeError("private resume content")

    monkeypatch.setattr(app_module, "analyze_resume_text", fail_analysis)
    response = upload_resume(client, b"Python developer with Flask", "resume.txt")

    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "RESUME_ANALYSIS_ERROR"
    assert "private resume content" not in response.get_data(as_text=True)
    assert list(Path(app.config["UPLOAD_FOLDER"]).iterdir()) == []


def test_job_description_text_limits_and_existing_success_contract(client):
    success = client.post(
        "/api/analyze-job-description",
        json={"target_role": "Python Developer", "job_description": "Python, Flask, SQL"},
    )
    oversized = client.post(
        "/api/analyze-job-description",
        json={
            "target_role": "Python Developer",
            "job_description": "x" * (app.config["MAX_JOB_DESCRIPTION_CHARS"] + 1),
        },
    )

    assert success.status_code == 200
    assert success.get_json()["success"] is True
    assert isinstance(success.get_json()["match_score"], int)
    assert oversized.status_code == 400
    assert oversized.get_json()["error"]["code"] == "INVALID_FILE"


def test_resume_parser_output_size_is_bounded_and_upload_is_cleaned(client, monkeypatch):
    ats_result = {
        "ats_score": 50,
        "score_breakdown": {},
        "resume_strengths": [],
        "missing_skills": [],
        "missing_keywords": [],
        "strong_keywords": [],
        "priority_keywords": [],
        "certifications": [],
        "projects_to_add": [],
        "sections_to_improve": [],
        "job_portals": [],
    }
    monkeypatch.setattr(
        app_module,
        "parse_resume_details",
        lambda _text: {"skills": [], "expanded": "x" * app.config["MAX_PARSER_OUTPUT_BYTES"]},
    )
    monkeypatch.setattr(app_module, "analyze_resume_text", lambda *_args: ats_result)
    monkeypatch.setattr(app_module, "generate_summary_versions", lambda *_args: {})
    monkeypatch.setattr(app_module, "generate_professional_summary", lambda *_args: "")
    monkeypatch.setattr(app_module, "get_resume_health", lambda *_args: {})

    response = upload_resume(client, b"valid resume text", "resume.txt")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_FILE"
    assert list(Path(app.config["UPLOAD_FOLDER"]).iterdir()) == []


def test_job_description_rejects_non_text_fields(client):
    response = client.post(
        "/api/analyze-job-description",
        json={"target_role": "Python Developer", "job_description": ["not", "text"]},
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_interview_resume_upload_validation_cleans_temporary_file(client):
    response = client.post(
        "/api/interview/start",
        data={
            "target_role": "Python Developer",
            "experience_level": "Fresher",
            "interview_type": "Technical",
            "difficulty": "Beginner",
            "question_count": "2",
            "ai_consent": "true",
            "resume": (BytesIO(b"not a real PDF"), "resume.pdf"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_FILE"
    assert list(Path(app.config["UPLOAD_FOLDER"]).iterdir()) == []
