from pathlib import Path

from app import app


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_landing_page_describes_capabilities_without_personal_demo_scores():
    response = app.test_client().get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Platform capabilities" in html
    assert "68/100" not in html
    assert "78/100" not in html
    assert "Career Readiness" not in html
    assert "ATS Estimate" not in html


def test_dashboard_renders_empty_state_shell_and_data_driven_script():
    response = app.test_client().get("/dashboard")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'id="dashboard-summary"' in html
    assert "js/dashboard.js" in html
    assert "Choose a next step" in html


def test_dashboard_metrics_use_valid_saved_values_or_explicit_empty_states():
    script = (PROJECT_ROOT / "static" / "js" / "dashboard.js").read_text(encoding="utf-8")

    assert "getStoredObject('careerGuideResults')" in script
    assert "getStoredObject('resumeAnalysisResults')" in script
    assert "getStoredObject('jobDescriptionResults')" in script
    assert "getStoredObject('interviewReport')" in script
    assert "career?.success === true ? getScore(career.readiness_score) : null" in script
    assert "resume?.success === true ? getScore(resume.ats_score) : null" in script
    assert "jobMatch?.success === true ? getScore(jobMatch.match_score) : null" in script
    assert "'Not analyzed yet'" in script
    assert "'No match yet'" in script
    assert "'Start a career plan'" in script
    assert "'Complete an interview'" in script
    assert "'Not recorded'" in script


def test_dashboard_has_no_fabricated_metric_fallbacks_and_clears_live_view():
    script = (PROJECT_ROOT / "static" / "js" / "dashboard.js").read_text(encoding="utf-8")

    for fabricated_value in ("68", "78", "82", "40", "'Today'", '"Today"'):
        assert fabricated_value not in script
    assert "renderDashboard();" in script
    assert "window.appStorage.removeKeys(keys)" in script
    assert "Number.isFinite(value)" in script
    assert "value >= 0 && value <= 100" in script


def test_interview_summary_records_an_actual_practice_timestamp():
    script = (PROJECT_ROOT / "static" / "js" / "interview.js").read_text(encoding="utf-8")

    assert "last_practice: new Date().toISOString()" in script
    assert "last_practice: 'Today'" not in script
