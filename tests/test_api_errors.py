from io import BytesIO

from app import app
from services.ai import AIServiceError


def assert_json_error(response, status_code, code):
    assert response.status_code == status_code
    assert response.is_json
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"]["code"] == code
    assert isinstance(payload["error"]["message"], str)


def test_api_rejects_malformed_and_non_object_json():
    client = app.test_client()

    malformed = client.post(
        "/api/career-plan",
        data='{"name":',
        content_type="application/json",
    )
    assert_json_error(malformed, 400, "INVALID_JSON")

    unsupported_media = client.post("/api/career-plan", data="{}")
    assert_json_error(unsupported_media, 415, "UNSUPPORTED_MEDIA_TYPE")

    non_object = client.post("/api/export-report", json=["not", "an", "object"])
    assert_json_error(non_object, 400, "INVALID_JSON")


def test_api_missing_fields_and_upload_errors_are_json():
    client = app.test_client()

    missing_fields = client.post("/api/career-plan", json={"ai_consent": True})
    assert_json_error(missing_fields, 400, "VALIDATION_ERROR")

    missing_resume = client.post("/api/analyze-resume", data={"target_role": "Developer"})
    assert_json_error(missing_resume, 400, "UPLOAD_ERROR")

    unsupported_resume = client.post(
        "/api/analyze-resume",
        data={
            "target_role": "Developer",
            "resume": (BytesIO(b"not a resume"), "resume.exe"),
        },
        content_type="multipart/form-data",
    )
    assert_json_error(unsupported_resume, 400, "UPLOAD_ERROR")


def test_api_oversized_request_returns_json():
    client = app.test_client()
    response = client.post(
        "/api/analyze-resume",
        data={
            "target_role": "Developer",
            "resume": (BytesIO(b"x" * (5 * 1024 * 1024 + 1)), "resume.txt"),
        },
        content_type="multipart/form-data",
    )

    assert_json_error(response, 413, "REQUEST_TOO_LARGE")


def test_ai_configuration_failure_is_safe_json(monkeypatch):
    class FailingAIService:
        def generate_career_plan(self, _profile):
            raise AIServiceError("AI_NOT_CONFIGURED", "provider details must not be returned")

    monkeypatch.setattr("app.create_ai_service", lambda: FailingAIService())
    response = app.test_client().post(
        "/api/career-plan",
        json={
            "name": "Candidate",
            "target_role": "Developer",
            "current_skills": "Python",
            "experience_level": "Fresher",
            "hours_per_day": 2,
            "ai_consent": True,
        },
    )

    assert_json_error(response, 503, "AI_NOT_CONFIGURED")
    assert "provider details" not in response.get_data(as_text=True)


def test_malformed_ai_response_is_reported_as_upstream_error(monkeypatch):
    def fail_generation(_self, _config, resume_text="", job_description=""):
        raise AIServiceError("AI_INVALID_RESPONSE", "provider details must not be returned")

    monkeypatch.setattr("app.InterviewService.generate_questions", fail_generation)
    response = app.test_client().post(
        "/api/interview/start",
        json={"target_role": "Python Developer", "question_count": 2, "ai_consent": True},
    )

    assert_json_error(response, 502, "AI_INVALID_RESPONSE")


def test_unexpected_api_exception_does_not_leak_details(monkeypatch):
    sensitive_detail = "C:\\private\\resume.txt provider-secret-value"

    def fail_analysis(*_args, **_kwargs):
        raise RuntimeError(sensitive_detail)

    monkeypatch.setattr("app.analyze_job_description", fail_analysis)
    response = app.test_client().post(
        "/api/analyze-job-description",
        json={"target_role": "Developer", "job_description": "Python role"},
    )

    assert_json_error(response, 500, "INTERNAL_SERVER_ERROR")
    assert sensitive_detail not in response.get_data(as_text=True)


def test_api_not_found_and_method_errors_are_json_but_page_404_is_html():
    client = app.test_client()

    api_not_found = client.get("/api/no-such-endpoint")
    assert_json_error(api_not_found, 404, "NOT_FOUND")

    api_wrong_method = client.get("/api/career-plan")
    assert_json_error(api_wrong_method, 405, "METHOD_NOT_ALLOWED")

    page_not_found = client.get("/no-such-page")
    assert page_not_found.status_code == 404
    assert not page_not_found.is_json
    assert page_not_found.mimetype == "text/html"
