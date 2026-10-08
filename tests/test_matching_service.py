import pytest

from app import app
from services.matching_service import match_resume_to_job
from services.profile_contracts import (
    create_empty_job_description_profile,
    create_empty_resume_profile,
    validate_matching_result,
)


def resume_profile():
    return create_empty_resume_profile().to_dict()


def jd_profile():
    return create_empty_job_description_profile().to_dict()


def test_matching_returns_validated_versioned_result():
    result = match_resume_to_job(resume_profile(), jd_profile())

    assert validate_matching_result(result) == result
    assert result["schema_version"] == "1.0"


def test_supported_skill_aliases_match_canonical_skills():
    resume = resume_profile()
    resume["skills"]["programming_languages"] = ["JavaScript"]
    resume["skills"]["frameworks"] = ["React"]
    resume["skills"]["databases"] = ["PostgreSQL"]
    resume["skills"]["other"] = ["Machine Learning"]
    jd = jd_profile()
    jd["required_skills"] = ["JS", "ReactJS", "Postgres", "ML"]

    result = match_resume_to_job(resume, jd)

    assert result["skill_match"] == 100
    assert result["matched_skills"] == [
        "JavaScript", "React", "PostgreSQL", "Machine Learning"
    ]


def test_skill_matching_does_not_use_substring_matches():
    resume = resume_profile()
    resume["skills"]["programming_languages"] = ["JavaScript"]
    jd = jd_profile()
    jd["required_skills"] = ["Java"]

    result = match_resume_to_job(resume, jd)

    assert result["skill_match"] == 0
    assert result["missing_required_skills"] == ["Java"]


def test_required_and_preferred_skill_weights_are_transparent():
    resume = resume_profile()
    resume["skills"]["programming_languages"] = ["Python"]
    jd = jd_profile()
    jd["required_skills"] = ["Python", "Java"]
    jd["preferred_skills"] = ["Docker"]

    result = match_resume_to_job(resume, jd)

    assert result["skill_match"] == 40
    assert result["missing_required_skills"] == ["Java"]
    assert result["missing_preferred_skills"] == ["Docker"]


def test_skill_score_uses_available_skill_group_when_other_group_is_empty():
    resume = resume_profile()
    resume["skills"]["tools"] = ["Docker"]
    jd = jd_profile()
    jd["preferred_skills"] = ["Docker"]

    result = match_resume_to_job(resume, jd)

    assert result["skill_match"] == 100


def test_missing_resume_skills_are_not_treated_as_a_known_zero_score():
    result = match_resume_to_job(resume_profile(), jd_profile())

    assert result["skill_match"] is None
    assert result["experience_match"] is None
    assert result["education_match"] is None
    assert result["keyword_match"] is None
    assert result["overall_match"] is None
    assert result["score_method"]["weights"] == {}
    assert result["score_method"]["available_dimensions"] == []


def test_only_explicit_work_duration_contributes_to_experience_score():
    resume = resume_profile()
    resume["experience"] = [
        {
            "kind": "work", "job_title": "Engineer", "organization": "A",
            "location": None, "start_date": None, "end_date": None,
            "duration_months": 12, "responsibilities": [], "achievements": [],
        },
        {
            "kind": "internship", "job_title": "Intern", "organization": "B",
            "location": None, "start_date": None, "end_date": None,
            "duration_months": 48, "responsibilities": [], "achievements": [],
        },
    ]
    jd = jd_profile()
    jd["experience"]["minimum_years"] = 2

    result = match_resume_to_job(resume, jd)

    assert result["experience_match"] == 50
    assert any("below the stated minimum" in gap for gap in result["gaps"])


def test_missing_explicit_experience_duration_remains_unassessed():
    resume = resume_profile()
    resume["experience"] = [
        {
            "kind": "work", "job_title": "Engineer", "organization": "A",
            "location": None, "start_date": "Jan 2021", "end_date": "Jan 2024",
            "duration_months": None, "responsibilities": [], "achievements": [],
        }
    ]
    jd = jd_profile()
    jd["experience"]["minimum_years"] = 2

    result = match_resume_to_job(resume, jd)

    assert result["experience_match"] is None
    assert "Work experience duration could not be verified from the resume profile." in result["gaps"]


def test_experience_score_is_capped_and_overqualification_is_not_penalized():
    resume = resume_profile()
    resume["experience"] = [
        {
            "kind": "work", "job_title": "Engineer", "organization": "A",
            "location": None, "start_date": None, "end_date": None,
            "duration_months": 120, "responsibilities": [], "achievements": [],
        }
    ]
    jd = jd_profile()
    jd["experience"]["minimum_years"] = 3
    jd["experience"]["maximum_years"] = 5

    result = match_resume_to_job(resume, jd)

    assert result["experience_match"] == 100


def test_education_match_uses_degree_and_field_evidence():
    resume = resume_profile()
    resume["education"] = [
        {
            "degree": "B.Tech", "field_of_study": "Computer Science",
            "institution": "Example University", "graduation_year": 2024,
            "grade": {"value": None, "scale": None},
        }
    ]
    jd = jd_profile()
    jd["education"] = ["Bachelor's degree in Computer Science"]

    result = match_resume_to_job(resume, jd)

    assert result["education_match"] == 100


def test_education_absence_is_unknown_not_a_zero_score():
    jd = jd_profile()
    jd["education"] = ["Bachelor's degree"]

    result = match_resume_to_job(resume_profile(), jd)

    assert result["education_match"] is None
    assert "Education could not be verified from the resume profile." in result["gaps"]


def test_education_level_does_not_match_on_incidental_substrings():
    resume = resume_profile()
    resume["education"] = [
        {
            "degree": "A degree can be completed online",
            "field_of_study": None, "institution": None,
            "graduation_year": None, "grade": {"value": None, "scale": None},
        }
    ]
    jd = jd_profile()
    jd["education"] = ["Bachelor's degree"]

    result = match_resume_to_job(resume, jd)

    assert result["education_match"] == 0


def test_keyword_match_ignores_generic_terms_and_requires_enough_evidence():
    resume = resume_profile()
    resume["skills"]["programming_languages"] = ["Python"]
    jd = jd_profile()
    jd["keywords"] = ["Python", "developer", "team"]

    result = match_resume_to_job(resume, jd)

    assert result["keyword_match"] is None


def test_keyword_match_is_deterministic_for_meaningful_catalog_terms():
    resume = resume_profile()
    resume["skills"]["programming_languages"] = ["Python"]
    jd = jd_profile()
    jd["keywords"] = ["Python", "Flask"]

    result = match_resume_to_job(resume, jd)

    assert result["keyword_match"] == 50


def test_overall_score_renormalizes_weights_for_available_dimensions():
    resume = resume_profile()
    resume["skills"]["programming_languages"] = ["Python"]
    jd = jd_profile()
    jd["required_skills"] = ["Python", "Java"]
    jd["education"] = ["Bachelor's degree"]
    resume["education"] = [
        {
            "degree": "Bachelor's degree", "field_of_study": None,
            "institution": None, "graduation_year": None,
            "grade": {"value": None, "scale": None},
        }
    ]

    result = match_resume_to_job(resume, jd)

    assert result["skill_match"] == 50
    assert result["education_match"] == 100
    assert result["keyword_match"] == 50
    assert result["overall_match"] == 59.38
    assert result["score_method"]["available_dimensions"] == [
        "skill_match", "education_match", "keyword_match"
    ]
    assert result["score_method"]["weights"] == {
        "skill_match": 0.625,
        "education_match": 0.1875,
        "keyword_match": 0.1875,
    }


def test_projects_can_supply_skills_but_not_employment_experience():
    resume = resume_profile()
    resume["projects"] = [
        {
            "name": "API", "description": None, "technologies": ["Python"],
            "achievements": [],
        }
    ]
    jd = jd_profile()
    jd["required_skills"] = ["Python"]
    jd["experience"]["minimum_years"] = 1

    result = match_resume_to_job(resume, jd)

    assert result["skill_match"] == 100
    assert result["experience_match"] is None
    assert result["recommendations"] == [
        "Highlight projects that demonstrate your matched required skills."
    ]


def test_invalid_profiles_are_rejected():
    resume = resume_profile()
    resume["schema_version"] = "2.0"

    with pytest.raises(ValueError, match="schema_version"):
        match_resume_to_job(resume, jd_profile())


def test_jd_api_adds_match_result_without_removing_legacy_fields():
    client = app.test_client()
    response = client.post(
        "/api/analyze-job-description",
        json={
            "job_description": "Python Developer. Required skills: Python, Flask.",
            "target_role": "Python Developer",
            "resume_text": "Skills: Python, Flask",
        },
    )

    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert {"match_score", "matched_skills", "missing_skills"} <= payload.keys()
    assert payload["match_result"]["schema_version"] == "1.0"
    assert payload["match_result"]["matched_skills"]


def test_jd_api_without_resume_preserves_legacy_response_shape():
    client = app.test_client()
    response = client.post(
        "/api/analyze-job-description",
        json={
            "job_description": "Python Developer",
            "target_role": "Python Developer",
        },
    )

    payload = response.get_json()

    assert response.status_code == 200
    assert "match_result" not in payload
