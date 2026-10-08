"""Versioned, JSON-serializable profile contracts for resume and JD analysis."""

from dataclasses import asdict, dataclass, field, is_dataclass
import json
import math
from typing import Any, Dict, List, Mapping, Optional, Union


SCHEMA_VERSION = "1.0"
EXPERIENCE_KINDS = {"work", "internship"}
GradeValue = Optional[Union[str, int, float]]


def _json_dict(value: Any) -> Dict[str, Any]:
    """Return a detached JSON-compatible dictionary, rejecting unsupported values."""
    payload = asdict(value) if is_dataclass(value) else dict(value) if isinstance(value, Mapping) else value
    if not isinstance(payload, dict):
        raise ValueError("Contract must serialize to a dictionary.")
    try:
        return json.loads(json.dumps(payload, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ValueError("Contract contains a value that is not JSON serializable.") from exc


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a dictionary.")
    return value


def _require_keys(value: Mapping[str, Any], keys: set[str], name: str) -> None:
    missing = keys.difference(value)
    if missing:
        raise ValueError(f"{name} is missing required field(s): {', '.join(sorted(missing))}.")


def _require_version(value: Mapping[str, Any], name: str) -> None:
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"{name}.schema_version must be {SCHEMA_VERSION!r}.")


def _optional_string(value: Any, name: str) -> None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{name} must be a string or null.")


def _string_list(value: Any, name: str) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a list of strings.")


def _optional_number(value: Any, name: str) -> None:
    if value is not None and (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite number or null.")


def _validate_extraction(value: Any, name: str) -> None:
    extraction = _require_mapping(value, name)
    _require_keys(extraction, {"field_sources", "confidence"}, name)

    sources = _require_mapping(extraction["field_sources"], f"{name}.field_sources")
    if any(not isinstance(key, str) or not isinstance(source, str) for key, source in sources.items()):
        raise ValueError(f"{name}.field_sources must map strings to strings.")

    confidence = _require_mapping(extraction["confidence"], f"{name}.confidence")
    for key, score in confidence.items():
        if not isinstance(key, str):
            raise ValueError(f"{name}.confidence keys must be strings.")
        _optional_number(score, f"{name}.confidence[{key!r}]")
        if score is not None and not 0 <= score <= 1:
            raise ValueError(f"{name}.confidence values must be between 0 and 1.")


def _validate_education_entry(value: Any, name: str) -> None:
    entry = _require_mapping(value, name)
    _require_keys(entry, {"degree", "field_of_study", "institution", "graduation_year", "grade"}, name)
    for key in ("degree", "field_of_study", "institution"):
        _optional_string(entry[key], f"{name}.{key}")

    year = entry["graduation_year"]
    if year is not None and (isinstance(year, bool) or not isinstance(year, int)):
        raise ValueError(f"{name}.graduation_year must be an integer or null.")

    grade = _require_mapping(entry["grade"], f"{name}.grade")
    _require_keys(grade, {"value", "scale"}, f"{name}.grade")
    grade_value = grade["value"]
    if grade_value is not None and (
        isinstance(grade_value, bool)
        or not isinstance(grade_value, (str, int, float))
        or (isinstance(grade_value, float) and not math.isfinite(grade_value))
    ):
        raise ValueError(f"{name}.grade.value must be a string, finite number, or null.")
    _optional_string(grade["scale"], f"{name}.grade.scale")


def _validate_experience_entry(value: Any, name: str) -> None:
    entry = _require_mapping(value, name)
    _require_keys(
        entry,
        {
            "kind", "job_title", "organization", "location", "start_date",
            "end_date", "duration_months", "responsibilities", "achievements",
        },
        name,
    )
    if not isinstance(entry["kind"], str) or entry["kind"] not in EXPERIENCE_KINDS:
        raise ValueError(f"{name}.kind must be one of: {', '.join(sorted(EXPERIENCE_KINDS))}.")
    for key in ("job_title", "organization", "location", "start_date", "end_date"):
        _optional_string(entry[key], f"{name}.{key}")
    duration = entry["duration_months"]
    if duration is not None and (
        isinstance(duration, bool) or not isinstance(duration, int) or duration < 0
    ):
        raise ValueError(f"{name}.duration_months must be a non-negative integer or null.")
    _string_list(entry["responsibilities"], f"{name}.responsibilities")
    _string_list(entry["achievements"], f"{name}.achievements")


def _validate_project_entry(value: Any, name: str) -> None:
    entry = _require_mapping(value, name)
    _require_keys(entry, {"name", "description", "technologies", "achievements"}, name)
    _optional_string(entry["name"], f"{name}.name")
    _optional_string(entry["description"], f"{name}.description")
    _string_list(entry["technologies"], f"{name}.technologies")
    _string_list(entry["achievements"], f"{name}.achievements")


@dataclass
class PersonalLinks:
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    other: List[str] = field(default_factory=list)


@dataclass
class PersonalProfile:
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    links: PersonalLinks = field(default_factory=PersonalLinks)


@dataclass
class EducationGrade:
    value: GradeValue = None
    scale: Optional[str] = None


@dataclass
class EducationEntry:
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    institution: Optional[str] = None
    graduation_year: Optional[int] = None
    grade: EducationGrade = field(default_factory=EducationGrade)


@dataclass
class ExperienceEntry:
    kind: str = "work"
    job_title: Optional[str] = None
    organization: Optional[str] = None
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    duration_months: Optional[int] = None
    responsibilities: List[str] = field(default_factory=list)
    achievements: List[str] = field(default_factory=list)


@dataclass
class ProjectEntry:
    name: Optional[str] = None
    description: Optional[str] = None
    technologies: List[str] = field(default_factory=list)
    achievements: List[str] = field(default_factory=list)


@dataclass
class ResumeSkills:
    programming_languages: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    databases: List[str] = field(default_factory=list)
    cloud: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    soft_skills: List[str] = field(default_factory=list)
    other: List[str] = field(default_factory=list)


@dataclass
class ExtractionMetadata:
    field_sources: Dict[str, str] = field(default_factory=dict)
    confidence: Dict[str, Optional[float]] = field(default_factory=dict)


@dataclass
class ResumeProfile:
    schema_version: str = SCHEMA_VERSION
    personal: PersonalProfile = field(default_factory=PersonalProfile)
    summary: Optional[str] = None
    education: List[EducationEntry] = field(default_factory=list)
    experience: List[ExperienceEntry] = field(default_factory=list)
    projects: List[ProjectEntry] = field(default_factory=list)
    skills: ResumeSkills = field(default_factory=ResumeSkills)
    certifications: List[str] = field(default_factory=list)
    achievements: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    extraction: ExtractionMetadata = field(default_factory=ExtractionMetadata)

    def to_dict(self) -> Dict[str, Any]:
        return _json_dict(self)


@dataclass
class Compensation:
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    currency: Optional[str] = None
    period: Optional[str] = None


@dataclass
class ExperienceRequirement:
    minimum_years: Optional[float] = None
    maximum_years: Optional[float] = None
    level: Optional[str] = None


@dataclass
class JobDescriptionProfile:
    schema_version: str = SCHEMA_VERSION
    job_title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    work_mode: Optional[str] = None
    employment_type: Optional[str] = None
    compensation: Compensation = field(default_factory=Compensation)
    required_skills: List[str] = field(default_factory=list)
    preferred_skills: List[str] = field(default_factory=list)
    responsibilities: List[str] = field(default_factory=list)
    experience: ExperienceRequirement = field(default_factory=ExperienceRequirement)
    education: List[str] = field(default_factory=list)
    certifications: List[str] = field(default_factory=list)
    soft_skills: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    extraction: ExtractionMetadata = field(default_factory=ExtractionMetadata)

    def to_dict(self) -> Dict[str, Any]:
        return _json_dict(self)


@dataclass
class ScoreMethod:
    version: str = SCHEMA_VERSION
    available_dimensions: List[str] = field(default_factory=list)
    weights: Dict[str, float] = field(default_factory=dict)


@dataclass
class MatchingResult:
    schema_version: str = SCHEMA_VERSION
    overall_match: Optional[float] = None
    skill_match: Optional[float] = None
    experience_match: Optional[float] = None
    education_match: Optional[float] = None
    keyword_match: Optional[float] = None
    matched_skills: List[str] = field(default_factory=list)
    missing_required_skills: List[str] = field(default_factory=list)
    missing_preferred_skills: List[str] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    score_method: ScoreMethod = field(default_factory=ScoreMethod)

    def to_dict(self) -> Dict[str, Any]:
        return _json_dict(self)


def _profile_dict(value: Any, expected_type: type, name: str) -> Dict[str, Any]:
    if not isinstance(value, (expected_type, Mapping)):
        raise ValueError(f"{name} must be a {expected_type.__name__} or dictionary.")
    return _json_dict(value)


def validate_resume_profile(value: Any) -> Dict[str, Any]:
    profile = _profile_dict(value, ResumeProfile, "Resume profile")
    required = {
        "schema_version", "personal", "summary", "education", "experience",
        "projects", "skills", "certifications", "achievements", "keywords", "extraction",
    }
    _require_keys(profile, required, "Resume profile")
    _require_version(profile, "Resume profile")

    personal = _require_mapping(profile["personal"], "Resume profile.personal")
    _require_keys(personal, {"name", "email", "phone", "location", "links"}, "Resume profile.personal")
    for key in ("name", "email", "phone", "location"):
        _optional_string(personal[key], f"Resume profile.personal.{key}")
    links = _require_mapping(personal["links"], "Resume profile.personal.links")
    _require_keys(links, {"linkedin", "github", "portfolio", "other"}, "Resume profile.personal.links")
    for key in ("linkedin", "github", "portfolio"):
        _optional_string(links[key], f"Resume profile.personal.links.{key}")
    _string_list(links["other"], "Resume profile.personal.links.other")

    _optional_string(profile["summary"], "Resume profile.summary")
    for collection in ("education", "experience", "projects"):
        if not isinstance(profile[collection], list):
            raise ValueError(f"Resume profile.{collection} must be a list.")
    for index, entry in enumerate(profile["education"]):
        _validate_education_entry(entry, f"Resume profile.education[{index}]")
    for index, entry in enumerate(profile["experience"]):
        _validate_experience_entry(entry, f"Resume profile.experience[{index}]")
    for index, entry in enumerate(profile["projects"]):
        _validate_project_entry(entry, f"Resume profile.projects[{index}]")

    skills = _require_mapping(profile["skills"], "Resume profile.skills")
    skill_categories = {
        "programming_languages", "frameworks", "databases", "cloud",
        "tools", "soft_skills", "other",
    }
    _require_keys(skills, skill_categories, "Resume profile.skills")
    for category in skill_categories:
        _string_list(skills[category], f"Resume profile.skills.{category}")
    for key in ("certifications", "achievements", "keywords"):
        _string_list(profile[key], f"Resume profile.{key}")
    _validate_extraction(profile["extraction"], "Resume profile.extraction")
    return profile


def validate_job_description_profile(value: Any) -> Dict[str, Any]:
    profile = _profile_dict(value, JobDescriptionProfile, "Job description profile")
    required = {
        "schema_version", "job_title", "company", "location", "work_mode",
        "employment_type", "compensation", "required_skills", "preferred_skills",
        "responsibilities", "experience", "education", "certifications",
        "soft_skills", "keywords", "extraction",
    }
    _require_keys(profile, required, "Job description profile")
    _require_version(profile, "Job description profile")
    for key in ("job_title", "company", "location", "work_mode", "employment_type"):
        _optional_string(profile[key], f"Job description profile.{key}")

    compensation = _require_mapping(profile["compensation"], "Job description profile.compensation")
    _require_keys(compensation, {"minimum", "maximum", "currency", "period"}, "Job description profile.compensation")
    for key in ("minimum", "maximum"):
        _optional_number(compensation[key], f"Job description profile.compensation.{key}")
    for key in ("currency", "period"):
        _optional_string(compensation[key], f"Job description profile.compensation.{key}")

    for key in ("required_skills", "preferred_skills", "responsibilities", "education",
                "certifications", "soft_skills", "keywords"):
        _string_list(profile[key], f"Job description profile.{key}")

    experience = _require_mapping(profile["experience"], "Job description profile.experience")
    _require_keys(experience, {"minimum_years", "maximum_years", "level"}, "Job description profile.experience")
    for key in ("minimum_years", "maximum_years"):
        _optional_number(experience[key], f"Job description profile.experience.{key}")
    _optional_string(experience["level"], "Job description profile.experience.level")
    _validate_extraction(profile["extraction"], "Job description profile.extraction")
    return profile


def validate_matching_result(value: Any) -> Dict[str, Any]:
    result = _profile_dict(value, MatchingResult, "Matching result")
    score_fields = {
        "overall_match", "skill_match", "experience_match", "education_match", "keyword_match",
    }
    required = {
        "schema_version", *score_fields, "matched_skills", "missing_required_skills",
        "missing_preferred_skills", "strengths", "gaps", "recommendations", "score_method",
    }
    _require_keys(result, required, "Matching result")
    _require_version(result, "Matching result")

    for key in score_fields:
        _optional_number(result[key], f"Matching result.{key}")
        if result[key] is not None and not 0 <= result[key] <= 100:
            raise ValueError(f"Matching result.{key} must be between 0 and 100 or null.")
    for key in (
        "matched_skills", "missing_required_skills", "missing_preferred_skills",
        "strengths", "gaps", "recommendations",
    ):
        _string_list(result[key], f"Matching result.{key}")

    score_method = _require_mapping(result["score_method"], "Matching result.score_method")
    _require_keys(score_method, {"version", "available_dimensions", "weights"}, "Matching result.score_method")
    _optional_string(score_method["version"], "Matching result.score_method.version")
    _string_list(score_method["available_dimensions"], "Matching result.score_method.available_dimensions")
    weights = _require_mapping(score_method["weights"], "Matching result.score_method.weights")
    for key, weight in weights.items():
        if not isinstance(key, str):
            raise ValueError("Matching result.score_method.weights keys must be strings.")
        _optional_number(weight, f"Matching result.score_method.weights[{key!r}]")
    return result


def create_empty_resume_profile() -> ResumeProfile:
    return ResumeProfile()


def create_empty_job_description_profile() -> JobDescriptionProfile:
    return JobDescriptionProfile()


def create_empty_matching_result() -> MatchingResult:
    return MatchingResult()
