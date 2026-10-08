from pathlib import Path

import pytest

from app import app


@pytest.fixture
def client():
    return app.test_client()


def valid_final_report_payload():
    return {
        "overall_score": 82,
        "technical": 84,
        "communication": 80,
        "problem_solving": 82,
        "project_knowledge": 85,
        "hr_readiness": 78,
        "strengths": ["Clear explanation"],
        "weaknesses": ["Add a practical example"],
        "weak_questions": [],
        "study_plan": [{"day": 1, "topic": "Python", "why": "Practice", "task": "Review basics"}],
        "results": [
            {
                "question": "How do you test a Flask endpoint?",
                "category": "Technical",
                "score": 82,
                "evaluation": {"overall_score": 82},
            }
        ],
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"overall_score": 82},
        {**valid_final_report_payload(), "results": []},
        {**valid_final_report_payload(), "results": ["malformed"]},
        {
            **valid_final_report_payload(),
            "results": [{"question": "", "score": 82, "evaluation": {"overall_score": 82}}],
        },
    ],
)
def test_final_report_rejects_missing_empty_or_malformed_results(client, payload):
    response = client.post("/api/interview/final-report", json=payload)

    assert response.status_code == 400
    assert response.get_json()["success"] is False
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_final_report_accepts_current_session_results_and_returns_report(client):
    response = client.post("/api/interview/final-report", json=valid_final_report_payload())

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["report"]["overall_score"] == 82
    assert body["report"]["technical"] == 84
    assert body["report"]["weak_questions"] == []
    assert body["report"]["study_plan"][0]["topic"] == "Python"


def test_final_report_pdf_download_uses_existing_export_endpoint(client):
    report_response = client.post("/api/interview/final-report", json=valid_final_report_payload())
    report = report_response.get_json()["report"]

    response = client.post(
        "/api/export-report",
        json={"title": "Interview Report", "report_type": "interview", "payload": report},
    )

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert "interview-report.pdf" in response.headers["Content-Disposition"]
    assert response.data.startswith(b"%PDF")


def test_final_report_frontend_sends_evaluations_without_raw_answers():
    script = (Path(__file__).resolve().parents[1] / "static" / "js" / "interview.js").read_text(encoding="utf-8")

    assert "results: state.results.map(item => ({" in script
    assert "evaluation: item.evaluation" in script
    assert "answer: item.answer" not in script
    assert "if (!response.ok || !data.success || !data.report)" in script
    assert "renderFinalReport(data.report)" in script
    assert "fetch('/api/export-report'" in script
    assert "downloadInterviewReportButton?.addEventListener('click', downloadInterviewReport)" in script
    assert "link.download = 'interview-report.pdf'" in script
