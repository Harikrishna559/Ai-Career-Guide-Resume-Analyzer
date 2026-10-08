import json
from datetime import datetime

import pytest

from services.profile_contracts import (
    SCHEMA_VERSION,
    EducationEntry,
    EducationGrade,
    ExperienceEntry,
    JobDescriptionProfile,
    MatchingResult,
    ProjectEntry,
    ResumeProfile,
    create_empty_job_description_profile,
    create_empty_matching_result,
    create_empty_resume_profile,
    validate_job_description_profile,
    validate_matching_result,
    validate_resume_profile,
)


def test_empty_profiles_have_versioned_unknown_values_and_empty_collections():
    resume = create_empty_resume_profile().to_dict()
    jd = create_empty_job_description_profile().to_dict()
    matching = create_empty_matching_result().to_dict()

    assert resume["schema_version"] == SCHEMA_VERSION
    assert resume["personal"]["name"] is None
    assert resume["summary"] is None
    assert resume["education"] == []
    assert resume["experience"] == []
    assert jd["schema_version"] == SCHEMA_VERSION
    assert jd["job_title"] is None
    assert jd["required_skills"] == []
    assert matching["schema_version"] == SCHEMA_VERSION
    assert matching["overall_match"] is None
    assert matching["skill_match"] is None


def test_all_contracts_serialize_as_json_without_datetime_values():
    contracts = (
        create_empty_resume_profile(),
        create_empty_job_description_profile(),
        create_empty_matching_result(),
    )
    for contract in contracts:
        serialized = json.dumps(contract.to_dict())
        assert isinstance(json.loads(serialized), dict)

    resume = create_empty_resume_profile()
    resume.experience.append(ExperienceEntry(start_date="2024-01"))
    assert json.loads(json.dumps(resume.to_dict()))["experience"][0]["start_date"] == "2024-01"


@pytest.mark.parametrize(
    ("value", "validator", "field"),
    [
        (create_empty_resume_profile().to_dict(), validate_resume_profile, "personal"),
        (create_empty_job_description_profile().to_dict(), validate_job_description_profile, "compensation"),
        (create_empty_matching_result().to_dict(), validate_matching_result, "score_method"),
    ],
)
def test_validators_require_top_level_fields(value, validator, field):
    del value[field]
    with pytest.raises(ValueError, match="missing required"):
        validator(value)


def test_schema_versions_are_validated():
    resume = create_empty_resume_profile().to_dict()
    resume["schema_version"] = "2.0"
    with pytest.raises(ValueError, match="schema_version"):
        validate_resume_profile(resume)


def test_nested_education_experience_and_project_structures_validate():
    profile = create_empty_resume_profile()
    profile.education.append(
        EducationEntry(
            degree="B.Sc.",
            field_of_study="Computer Science",
            institution="Example University",
            graduation_year=2025,
            grade=EducationGrade(value=3.8, scale="4.0"),
        )
    )
    profile.experience.append(
        ExperienceEntry(
            kind="internship",
            job_title="Developer Intern",
            responsibilities=["Built an API"],
            achievements=["Reduced processing time"],
        )
    )
    profile.projects.append(
        ProjectEntry(
            name="Portfolio",
            description="Personal site",
            technologies=["HTML", "JavaScript"],
            achievements=["Published portfolio"],
        )
    )
    validated = validate_resume_profile(profile)
    assert validated["education"][0]["grade"]["value"] == 3.8
    assert validated["experience"][0]["kind"] == "internship"
    assert validated["projects"][0]["technologies"] == ["HTML", "JavaScript"]


def test_resume_skills_categories_validate():
    profile = create_empty_resume_profile()
    profile.skills.programming_languages.append("Python")
    profile.skills.frameworks.append("Flask")
    validated = validate_resume_profile(profile)
    assert validated["skills"]["programming_languages"] == ["Python"]
    assert validated["skills"]["frameworks"] == ["Flask"]
    assert set(validated["skills"]) == {
        "programming_languages", "frameworks", "databases", "cloud",
        "tools", "soft_skills", "other",
    }


@pytest.mark.parametrize("kind", ["work", "internship"])
def test_experience_kind_accepts_supported_values(kind):
    profile = create_empty_resume_profile()
    profile.experience.append(ExperienceEntry(kind=kind))
    assert validate_resume_profile(profile)["experience"][0]["kind"] == kind


def test_invalid_experience_kind_is_rejected():
    profile = create_empty_resume_profile().to_dict()
    profile["experience"].append(ExperienceEntry(kind="contractor").__dict__)
    with pytest.raises(ValueError, match="kind"):
        validate_resume_profile(profile)


@pytest.mark.parametrize("score", [-0.1, 100.1, float("nan"), float("inf")])
def test_matching_scores_must_be_finite_and_between_zero_and_100(score):
    result = create_empty_matching_result().to_dict()
    result["overall_match"] = score
    with pytest.raises(ValueError):
        validate_matching_result(result)


def test_null_scores_remain_unassessed():
    result = validate_matching_result(create_empty_matching_result())
    assert result["overall_match"] is None
    assert result["experience_match"] is None
    assert result["education_match"] is None


@pytest.mark.parametrize(
    ("validator", "value", "path", "invalid"),
    [
        (validate_resume_profile, create_empty_resume_profile().to_dict(), "education", {}),
        (validate_resume_profile, create_empty_resume_profile().to_dict(), "skills", []),
        (validate_job_description_profile, create_empty_job_description_profile().to_dict(), "required_skills", {}),
        (validate_matching_result, create_empty_matching_result().to_dict(), "strengths", {}),
    ],
)
def test_invalid_list_and_dictionary_structures_are_rejected(validator, value, path, invalid):
    value[path] = invalid
    with pytest.raises(ValueError):
        validator(value)


def test_extraction_metadata_must_use_dictionary_structures():
    profile = create_empty_resume_profile().to_dict()
    profile["extraction"]["field_sources"] = []
    with pytest.raises(ValueError, match="dictionary"):
        validate_resume_profile(profile)


def test_serialization_rejects_non_json_values():
    profile = create_empty_resume_profile()
    profile.extraction.field_sources["unsupported"] = object()
    with pytest.raises(ValueError, match="JSON serializable"):
        profile.to_dict()


def test_serialization_rejects_datetime_values():
    profile = create_empty_resume_profile()
    profile.experience.append(ExperienceEntry(start_date=datetime(2024, 1, 1)))
    with pytest.raises(ValueError, match="JSON serializable"):
        profile.to_dict()


def test_job_description_nested_compensation_and_experience_validate():
    jd = create_empty_job_description_profile()
    jd.compensation.minimum = 70000
    jd.experience.minimum_years = 2
    result = validate_job_description_profile(jd)
    assert result["compensation"]["minimum"] == 70000
    assert result["experience"]["minimum_years"] == 2


def test_matching_result_requires_dictionary_weights_and_valid_lists():
    result = create_empty_matching_result().to_dict()
    result["score_method"]["weights"] = []
    with pytest.raises(ValueError, match="dictionary"):
        validate_matching_result(result)


def test_profile_validators_accept_serialized_dictionaries():
    assert validate_resume_profile(ResumeProfile().to_dict())["schema_version"] == SCHEMA_VERSION
    assert validate_job_description_profile(JobDescriptionProfile().to_dict())["schema_version"] == SCHEMA_VERSION
    assert validate_matching_result(MatchingResult().to_dict())["schema_version"] == SCHEMA_VERSION
