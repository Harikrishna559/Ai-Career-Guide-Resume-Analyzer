from concurrent.futures import ThreadPoolExecutor

from flask import Flask, request

import app as app_module
from app import app
from services.ai.rate_limit import (
    DEFAULT_MAX_REQUESTS,
    DEFAULT_WINDOW_SECONDS,
    AIRateLimiter,
)


def test_request_at_limit_is_allowed_and_request_above_limit_is_blocked():
    limiter = AIRateLimiter(window_seconds=60, max_requests=2)

    assert limiter.allow("192.0.2.10") is True
    assert limiter.allow("192.0.2.10") is True
    assert limiter.allow("192.0.2.10") is False


def test_different_clients_have_independent_limits():
    limiter = AIRateLimiter(window_seconds=60, max_requests=1)

    assert limiter.allow("192.0.2.10") is True
    assert limiter.allow("192.0.2.11") is True
    assert limiter.allow("192.0.2.10") is False


def test_expired_window_allows_requests_again():
    now = [100.0]
    limiter = AIRateLimiter(window_seconds=60, max_requests=1, clock=lambda: now[0])

    assert limiter.allow("192.0.2.10") is True
    assert limiter.allow("192.0.2.10") is False
    now[0] = 160.0
    assert limiter.allow("192.0.2.10") is True


def test_cleanup_removes_expired_client_state():
    now = [0.0]
    limiter = AIRateLimiter(window_seconds=10, max_requests=1, clock=lambda: now[0])
    assert limiter.allow("192.0.2.10") is True
    assert limiter.allow("192.0.2.11") is True
    assert limiter.tracked_clients == 2

    now[0] = 10.0
    assert limiter.cleanup() == 2
    assert limiter.tracked_clients == 0


def test_configuration_uses_defaults_for_invalid_values():
    limiter = AIRateLimiter.from_env({
        "AI_RATE_LIMIT_WINDOW_SECONDS": "not-a-number",
        "AI_RATE_LIMIT_MAX_REQUESTS": "0",
    })

    assert limiter.window_seconds == DEFAULT_WINDOW_SECONDS
    assert limiter.max_requests == DEFAULT_MAX_REQUESTS


def test_configuration_uses_defaults_for_values_outside_safe_bounds():
    limiter = AIRateLimiter.from_env({
        "AI_RATE_LIMIT_WINDOW_SECONDS": "999999999",
        "AI_RATE_LIMIT_MAX_REQUESTS": "-10",
    })

    assert limiter.window_seconds == DEFAULT_WINDOW_SECONDS
    assert limiter.max_requests == DEFAULT_MAX_REQUESTS


def test_direct_constructor_uses_safe_defaults_for_invalid_values():
    limiter = AIRateLimiter(window_seconds=0, max_requests=0, max_clients=0)

    assert limiter.window_seconds == DEFAULT_WINDOW_SECONDS
    assert limiter.max_requests == DEFAULT_MAX_REQUESTS
    assert limiter.max_clients > 0


def test_state_is_bounded_when_client_capacity_is_reached():
    now = [0.0]
    limiter = AIRateLimiter(
        window_seconds=10,
        max_requests=1,
        max_clients=1,
        clock=lambda: now[0],
    )

    assert limiter.allow("192.0.2.10") is True
    assert limiter.allow("192.0.2.11") is False
    assert limiter.tracked_clients == 1
    now[0] = 10.0
    assert limiter.allow("192.0.2.11") is True


def test_state_is_thread_safe_under_concurrent_requests():
    limiter = AIRateLimiter(window_seconds=60, max_requests=5)

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(limiter.allow, ["192.0.2.10"] * 40))

    assert sum(results) == 5
    assert limiter.tracked_clients == 1


def test_limiter_stores_only_hashed_client_identifier_and_counter_metadata():
    client_address = "192.0.2.10"
    limiter = AIRateLimiter(window_seconds=60, max_requests=2)

    assert limiter.allow(client_address) is True
    state = repr(limiter._windows)

    assert client_address not in state
    assert all(
        isinstance(window.started_at, float) and isinstance(window.request_count, int)
        for window in limiter._windows.values()
    )


def test_limiter_state_does_not_store_request_content(monkeypatch):
    sensitive_content = "resume prompt JD interview private-content-9fc1"
    limiter = AIRateLimiter(window_seconds=60, max_requests=1)
    monkeypatch.setattr(app_module, "ai_rate_limiter", limiter)

    class FakeAIService:
        def generate_career_plan(self, _profile):
            return {"career_summary": "A plan"}

    monkeypatch.setattr(app_module, "create_ai_service", lambda: FakeAIService())
    response = app.test_client().post(
        "/api/career-plan",
        json={
            "name": "Candidate",
            "target_role": "Developer",
            "current_skills": sensitive_content,
            "experience_level": "Fresher",
            "hours_per_day": 2,
            "ai_consent": True,
        },
    )

    assert response.status_code == 200
    assert sensitive_content not in repr(limiter._windows)
    assert "Candidate" not in repr(limiter._windows)


def test_trusted_proxy_count_is_disabled_for_missing_invalid_or_unsafe_values():
    assert app_module._configure_trusted_proxy(Flask(__name__), None) == 0
    assert app_module._configure_trusted_proxy(Flask(__name__), "") == 0
    assert app_module._configure_trusted_proxy(Flask(__name__), "invalid") == 0
    assert app_module._configure_trusted_proxy(Flask(__name__), "-1") == 0
    assert app_module._configure_trusted_proxy(Flask(__name__), "6") == 0


def test_proxy_headers_are_ignored_when_no_trusted_hops_are_configured():
    flask_app = Flask(__name__)

    @flask_app.get("/client-ip")
    def get_client_ip():
        return flask_app.response_class(request.remote_addr)

    response = flask_app.test_client().get(
        "/client-ip",
        environ_overrides={"REMOTE_ADDR": "192.0.2.10"},
        headers={"X-Forwarded-For": "198.51.100.99"},
    )

    assert response.get_data(as_text=True) == "192.0.2.10"


def test_proxy_fix_trusts_only_the_configured_rightmost_forwarded_hop():
    flask_app = Flask(__name__)
    assert app_module._configure_trusted_proxy(flask_app, "1") == 1

    @flask_app.get("/client-ip")
    def get_client_ip():
        return flask_app.response_class(request.remote_addr)

    response = flask_app.test_client().get(
        "/client-ip",
        environ_overrides={"REMOTE_ADDR": "10.0.0.1"},
        headers={"X-Forwarded-For": "198.51.100.99, 203.0.113.5"},
    )

    assert response.get_data(as_text=True) == "203.0.113.5"


def test_exceeded_limit_uses_safe_429_json_error(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "ai_rate_limiter",
        AIRateLimiter(window_seconds=60, max_requests=1),
    )

    class FakeAIService:
        def generate_career_plan(self, _profile):
            assert _profile["target_role"] == "Developer"
            return {"career_summary": "A plan"}

    monkeypatch.setattr(app_module, "create_ai_service", lambda: FakeAIService())
    client = app.test_client()
    payload = {
        "name": "Candidate",
        "target_role": "Developer",
        "current_skills": "Python",
        "experience_level": "Fresher",
        "hours_per_day": 2,
        "ai_consent": True,
    }

    assert client.post("/api/career-plan", json=payload).status_code == 200
    blocked = client.post("/api/career-plan", json=payload)

    assert blocked.status_code == 429
    assert blocked.is_json
    assert blocked.get_json() == {
        "success": False,
        "error": {
            "code": "AI_RATE_LIMIT",
            "message": "Too many AI requests. Please try again later.",
        },
    }
    assert "192.0.2" not in blocked.get_data(as_text=True)
    assert "counter" not in blocked.get_data(as_text=True)


def test_blocked_career_request_does_not_call_ai_service(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "ai_rate_limiter",
        AIRateLimiter(window_seconds=60, max_requests=1),
    )
    calls = []

    class FakeAIService:
        def generate_career_plan(self, _profile):
            calls.append(_profile["target_role"])
            return {"career_summary": "A plan"}

    monkeypatch.setattr(app_module, "create_ai_service", lambda: FakeAIService())
    client = app.test_client()
    payload = {
        "name": "Candidate",
        "target_role": "Developer",
        "current_skills": "Python",
        "experience_level": "Fresher",
        "hours_per_day": 2,
        "ai_consent": True,
    }

    client.post("/api/career-plan", json=payload)
    response = client.post("/api/career-plan", json=payload)

    assert response.status_code == 429
    assert calls == ["Developer"]


def test_blocked_interview_evaluation_does_not_call_ai_service(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "ai_rate_limiter",
        AIRateLimiter(window_seconds=60, max_requests=1),
    )
    calls = []

    class FakeInterviewService:
        def __init__(self):
            pass

        def validate_answer(self, answer):
            if not answer:
                raise ValueError("Answer cannot be empty.")
            return answer

        def evaluate_answer(self, *_args):
            calls.append(_args[0])
            return {"overall_score": 80}

    monkeypatch.setattr(app_module, "InterviewService", FakeInterviewService)
    client = app.test_client()
    payload = {"question": "Explain Python.", "answer": "I use Python.", "ai_consent": True}

    assert client.post("/api/interview/evaluate", json=payload).status_code == 200
    blocked = client.post("/api/interview/evaluate", json=payload)

    assert blocked.status_code == 429
    assert blocked.get_json()["error"]["code"] == "AI_RATE_LIMIT"
    assert calls == ["Explain Python."]


def test_blocked_interview_start_does_not_generate_questions(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "ai_rate_limiter",
        AIRateLimiter(window_seconds=60, max_requests=1),
    )
    calls = []

    class FakeInterviewService:
        def __init__(self):
            self.ai_service = object()

        def validate_setup(self, payload):
            return {"target_role": payload["target_role"]}

        def generate_questions(self, _config, **_kwargs):
            calls.append(_config["target_role"] + str(_kwargs))
            return [{"question": "Question"}]

    monkeypatch.setattr(app_module, "InterviewService", FakeInterviewService)
    client = app.test_client()
    payload = {"target_role": "Python Developer", "ai_consent": True}

    assert client.post("/api/interview/start", json=payload).status_code == 200
    blocked = client.post("/api/interview/start", json=payload)

    assert blocked.status_code == 429
    assert len(calls) == 1
    assert calls[0].startswith("Python Developer")


def test_interview_start_fallback_still_runs_when_within_limit(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "ai_rate_limiter",
        AIRateLimiter(window_seconds=60, max_requests=1),
    )

    class FakeInterviewService:
        def __init__(self):
            self.ai_service = object()

        def validate_setup(self, payload):
            return {"target_role": payload["target_role"]}

        def generate_questions(self, _config, resume_text="", job_description=""):
            return [{
                "question": "Local fallback question.",
                "role": _config["target_role"],
                "resume_text": resume_text,
                "job_description": job_description,
            }]

    monkeypatch.setattr(app_module, "InterviewService", FakeInterviewService)
    response = app.test_client().post(
        "/api/interview/start",
        json={"target_role": "Python Developer", "ai_consent": True},
    )

    assert response.status_code == 200
    assert response.get_json()["questions"][0]["question"] == "Local fallback question."


def test_deterministic_roles_endpoint_is_not_rate_limited(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "ai_rate_limiter",
        AIRateLimiter(window_seconds=60, max_requests=1),
    )
    limiter = app_module.ai_rate_limiter
    assert limiter.allow("127.0.0.1") is True

    response = app.test_client().get("/api/roles")

    assert response.status_code == 200
