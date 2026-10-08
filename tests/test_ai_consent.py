import pytest

import app as app_module
from app import app
from services.ai.rate_limit import AIRateLimiter


def assert_consent_error(response):
    assert response.status_code == 400
    assert response.get_json() == {
        "success": False,
        "error": {
            "code": "AI_CONSENT_REQUIRED",
            "message": "AI processing consent is required before using this feature.",
        },
    }


@pytest.mark.parametrize("consent", [None, False])
def test_career_plan_rejects_missing_or_false_consent_before_provider_call(monkeypatch, consent):
    provider_calls = []
    monkeypatch.setattr(
        app_module,
        "ai_rate_limiter",
        AIRateLimiter(window_seconds=60, max_requests=10),
    )

    def create_service():
        provider_calls.append("created")
        raise AssertionError("Provider must not be initialized without consent.")

    monkeypatch.setattr(app_module, "create_ai_service", create_service)
    payload = {
        "name": "Candidate",
        "target_role": "Developer",
        "current_skills": "Python",
        "experience_level": "Fresher",
        "hours_per_day": 2,
    }
    if consent is not None:
        payload["ai_consent"] = consent

    response = app.test_client().post("/api/career-plan", json=payload)

    assert_consent_error(response)
    assert provider_calls == []
    assert app_module.ai_rate_limiter.tracked_clients == 0


def test_career_plan_true_consent_allows_provider_request(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "ai_rate_limiter",
        AIRateLimiter(window_seconds=60, max_requests=10),
    )
    calls = []

    class FakeAIService:
        def generate_career_plan(self, profile):
            calls.append(profile["target_role"])
            return {"career_summary": "Plan"}

    monkeypatch.setattr(app_module, "create_ai_service", lambda: FakeAIService())
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

    assert response.status_code == 200
    assert response.get_json()["career_summary"] == "Plan"
    assert calls == ["Developer"]


@pytest.mark.parametrize("consent", [None, False])
def test_interview_start_rejects_missing_or_false_consent_before_upload_or_ai(
    monkeypatch, consent
):
    def unexpected(*_args, **_kwargs):
        raise AssertionError("Interview processing must not occur without consent.")

    monkeypatch.setattr(app_module, "InterviewService", unexpected)
    monkeypatch.setattr(app_module, "extract_text_from_resume", unexpected)
    fields = {"target_role": "Python Developer"}
    if consent is not None:
        fields["ai_consent"] = str(consent).lower()
    response = app.test_client().post("/api/interview/start", data=fields)

    assert_consent_error(response)


@pytest.mark.parametrize("consent", [None, False])
def test_interview_evaluation_rejects_missing_or_false_consent_before_ai(
    monkeypatch, consent
):
    def unexpected(*_args, **_kwargs):
        raise AssertionError("Interview evaluation must not occur without consent.")

    monkeypatch.setattr(app_module, "InterviewService", unexpected)
    payload = {"question": "Question", "answer": "Sensitive answer content"}
    if consent is not None:
        payload["ai_consent"] = consent

    response = app.test_client().post("/api/interview/evaluate", json=payload)

    assert_consent_error(response)


def test_true_consent_allows_interview_evaluation(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "ai_rate_limiter",
        AIRateLimiter(window_seconds=60, max_requests=10),
    )
    calls = []

    class FakeInterviewService:
        def validate_answer(self, answer):
            return answer.strip()

        def evaluate_answer(
            self,
            question,
            answer,
            _target_role,
            _experience_level,
            _interview_type,
            _difficulty,
            context,
        ):
            calls.append((question, answer, context))
            return {"overall_score": 80}

    monkeypatch.setattr(app_module, "InterviewService", FakeInterviewService)
    response = app.test_client().post(
        "/api/interview/evaluate",
        json={
            "question": "Explain Python.",
            "answer": "A concise answer.",
            "ai_consent": True,
        },
    )

    assert response.status_code == 200
    assert response.get_json()["evaluation"]["overall_score"] == 80
    assert calls == [
        (
            "Explain Python.",
            "A concise answer.",
            {
                "question": "Explain Python.",
                "answer": "A concise answer.",
            },
        )
    ]


def test_multipart_interview_start_accepts_explicit_true_consent(monkeypatch):
    class FakeInterviewService:
        def __init__(self):
            self.ai_service = object()

        def validate_setup(self, payload):
            return {"target_role": payload["target_role"]}

        def generate_questions(self, _config, **_kwargs):
            return [{"question": "Question"}]

    monkeypatch.setattr(app_module, "InterviewService", FakeInterviewService)
    response = app.test_client().post(
        "/api/interview/start",
        data={"target_role": "Developer", "ai_consent": "true"},
    )

    assert response.status_code == 200
    assert response.get_json()["questions"] == [{"question": "Question"}]


def test_deterministic_endpoints_do_not_require_ai_consent():
    client = app.test_client()

    jd_response = client.post(
        "/api/analyze-job-description",
        json={
            "job_description": "Python Developer",
            "target_role": "Python Developer",
        },
    )
    roles_response = client.get("/api/roles")
    health_response = client.get("/health")

    assert jd_response.status_code == 200
    assert roles_response.status_code == 200
    assert health_response.status_code == 200


def test_consent_and_submitted_content_are_not_logged_or_rate_state(caplog, monkeypatch):
    monkeypatch.setattr(
        app_module,
        "ai_rate_limiter",
        AIRateLimiter(window_seconds=60, max_requests=10),
    )
    sensitive_text = "private career detail 87241"
    response = app.test_client().post(
        "/api/career-plan",
        json={
            "name": "Candidate",
            "target_role": sensitive_text,
            "current_skills": "Python",
            "experience_level": "Fresher",
            "hours_per_day": 2,
            "ai_consent": False,
        },
    )

    assert_consent_error(response)
    assert sensitive_text not in caplog.text
    assert "ai_consent" not in caplog.text
    assert app_module.ai_rate_limiter.tracked_clients == 0


def test_frontend_disclosure_and_requests_do_not_persist_consent():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    career_js = (root / "static" / "js" / "career.js").read_text(encoding="utf-8")
    interview_js = (root / "static" / "js" / "interview.js").read_text(encoding="utf-8")
    career_template = (root / "templates" / "career-guide.html").read_text(encoding="utf-8")
    interview_template = (root / "templates" / "interview-simulator.html").read_text(encoding="utf-8")
    disclosure = (root / "templates" / "partials" / "ai_disclosure.html").read_text(encoding="utf-8")

    assert "formData.ai_consent = true" in career_js
    assert "ai_consent: true" in interview_js
    assert "render_ai_disclosure" in career_template
    assert "render_ai_disclosure" in interview_template
    assert "Google Gemini AI" in disclosure
    assert "ai_consent" not in (root / "static" / "js" / "main.js").read_text(encoding="utf-8")


def test_ai_disclosure_renders_on_career_and_interview_pages():
    client = app.test_client()

    career_page = client.get("/career-guide").get_data(as_text=True)
    interview_page = client.get("/interview-simulator").get_data(as_text=True)

    assert "Google Gemini AI" in career_page
    assert 'id="career-ai-consent"' in career_page
    assert "Google Gemini AI" in interview_page
    assert 'id="interview-start-ai-consent"' in interview_page
    assert 'id="interview-answer-ai-consent"' in interview_page
