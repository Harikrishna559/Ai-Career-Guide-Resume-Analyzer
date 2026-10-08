from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_project_file(*parts):
    return (PROJECT_ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def test_resume_score_is_described_as_rule_based_not_ai_generated():
    source = read_project_file("static", "js", "main.js")

    assert "Rule-based ATS compatibility estimate" in source
    assert "AI-generated ATS-style estimate" not in source
    assert "data.ats_score || 0" not in source
    assert "Keyword Match, Skills Match, and Job Role Relevance vary with role keywords" in source
    assert "fixed baseline values" in source


def test_career_readiness_and_roadmap_progress_have_no_score_fallbacks():
    source = read_project_file("static", "js", "main.js")

    assert "data.readiness_score || '68'" not in source
    assert ": 40" not in source
    assert "No readiness estimate was provided." in source
    assert "${completed} of ${total} roadmap steps completed." in source


def test_job_description_page_renders_structured_match_dimensions_and_unknowns():
    source = read_project_file("static", "js", "job-description.js")

    for field in (
        "match_result",
        "overall_match",
        "skill_match",
        "experience_match",
        "education_match",
        "keyword_match",
        "matched_skills",
        "strengths",
        "missing_required_skills",
        "missing_preferred_skills",
        "score_method.weights",
    ):
        assert field in source
    assert "Not assessed (insufficient evidence)" in source
    assert "Role Keyword Estimate" in source
    assert "not AI-generated" in source
    assert "Number(data.match_score || 0)" not in source


def test_interview_ui_distinguishes_ai_fallback_and_derived_report_values():
    source = read_project_file("templates", "interview-simulator.html")

    assert "deterministic heuristic fallback" in source
    assert "Clarity (not a confidence measure)" in source
    assert "locally derived estimates with a 50-point minimum" in source
    assert "Generic 7-Day Interview Practice Plan" in source
    assert "not tailored to your role or evaluated answers" in source
