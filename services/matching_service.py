"""Deterministic, explainable matching of structured resume and JD profiles."""

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from services.jd_parser import SKILL_ALIASES
from services.profile_contracts import (
    MatchingResult,
    validate_job_description_profile,
    validate_matching_result,
    validate_resume_profile,
)


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OVERALL_WEIGHTS = {
    "skill_match": 0.50,
    "experience_match": 0.20,
    "education_match": 0.15,
    "keyword_match": 0.15,
}
REQUIRED_SKILL_WEIGHT = 0.80
PREFERRED_SKILL_WEIGHT = 0.20
MIN_MEANINGFUL_KEYWORDS = 2
GENERIC_KEYWORDS = {
    "developer", "engineer", "analyst", "manager", "candidate", "job",
    "role", "team", "company", "experience", "skills", "responsibility",
    "responsibilities", "work", "working", "required", "preferred", "good",
    "strong", "ability", "knowledge", "year", "years", "degree",
}
SOFT_SKILL_TERMS = {
    "communication", "leadership", "teamwork", "problem solving",
    "critical thinking", "collaboration", "adaptability", "time management",
}
DEGREE_LEVELS = {
    "bachelor": ("bachelor", "b.tech", "btech", "b.e.", "b.sc", "bsc", "b.com", "bcom", "bca"),
    "master": ("master", "m.tech", "mtech", "m.e.", "m.sc", "msc", "m.com", "mcom", "mca", "mba"),
    "doctorate": ("ph.d", "phd", "doctorate"),
}


def _unique(values: Iterable[str]) -> List[str]:
    output = []
    seen = set()
    for value in values:
        cleaned = str(value).strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            output.append(cleaned)
    return output


def _canonical_skill(value: str, known_names: Dict[str, str]) -> str:
    cleaned = re.sub(r"\s+", " ", str(value).strip())
    key = cleaned.casefold()
    canonical_alias = {alias.casefold(): target for alias, target in SKILL_ALIASES.items()}
    canonical = canonical_alias.get(key, cleaned)
    return known_names.get(canonical.casefold(), canonical)


def _load_skill_names() -> Dict[str, str]:
    with open(DATA_DIR / "skills.json", encoding="utf-8") as file:
        catalog = json.load(file)
    names = {}
    for group in catalog:
        for value in group.get("skills", []):
            if isinstance(value, str) and value.strip():
                names[value.casefold()] = value.strip()
    names.update({alias.casefold(): canonical for alias, canonical in SKILL_ALIASES.items()})
    return names


def _resume_skill_names(resume: Dict[str, Any], known_names: Dict[str, str]) -> Set[str]:
    raw_skills = []
    skills = resume.get("skills", {})
    for values in skills.values():
        raw_skills.extend(values)
    raw_skills.extend(resume.get("keywords", []))
    for project in resume.get("projects", []):
        raw_skills.extend(project.get("technologies", []))
    return {_canonical_skill(skill, known_names).casefold() for skill in raw_skills}


def _jd_skill_names(jd: Dict[str, Any], field: str, known_names: Dict[str, str]) -> List[str]:
    return _unique(_canonical_skill(skill, known_names) for skill in jd.get(field, []))


def _score_skill_match(required: List[str], preferred: List[str], resume_skills: Set[str]) -> Optional[float]:
    required_score = (
        sum(skill.casefold() in resume_skills for skill in required) / len(required) * 100
        if required else None
    )
    preferred_score = (
        sum(skill.casefold() in resume_skills for skill in preferred) / len(preferred) * 100
        if preferred else None
    )
    if required_score is not None and preferred_score is not None:
        return round(required_score * REQUIRED_SKILL_WEIGHT + preferred_score * PREFERRED_SKILL_WEIGHT, 2)
    if required_score is not None:
        return round(required_score, 2)
    if preferred_score is not None:
        return round(preferred_score, 2)
    return None


def _work_experience_years(resume: Dict[str, Any]) -> Optional[float]:
    durations = [
        entry["duration_months"]
        for entry in resume.get("experience", [])
        if entry.get("kind") == "work" and entry.get("duration_months") is not None
    ]
    if not durations:
        return None
    return sum(durations) / 12


def _experience_score(resume: Dict[str, Any], jd: Dict[str, Any]) -> Optional[float]:
    requirement = jd["experience"]
    minimum = requirement.get("minimum_years")
    maximum = requirement.get("maximum_years")
    if minimum is None and maximum is None:
        return None

    years = _work_experience_years(resume)
    if years is None:
        return None
    if minimum is not None and minimum > 0 and years < minimum:
        return round(max(0.0, years / minimum * 100), 2)
    return 100.0


def _degree_level(text: str) -> Optional[str]:
    lowered = text.casefold()
    for level, markers in DEGREE_LEVELS.items():
        if any(
            re.search(
                rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])",
                lowered,
            )
            for marker in markers
        ):
            return level
    if re.search(r"\bbachelor(?:'s)?\b", lowered):
        return "bachelor"
    if re.search(r"\bmaster(?:'s)?\b", lowered):
        return "master"
    return None


def _education_score(resume: Dict[str, Any], jd: Dict[str, Any]) -> Optional[float]:
    requirements = jd.get("education", [])
    entries = resume.get("education", [])
    if not requirements or not entries:
        return None

    requirement_scores = []
    for requirement in requirements:
        req = str(requirement).casefold()
        level = _degree_level(req)
        field_match = re.search(r"\bin\s+(.+?)(?:,|$)", req)
        field = field_match.group(1).strip(" .") if field_match else None
        best = 0.0
        for entry in entries:
            candidate = " ".join(
                str(entry.get(key) or "")
                for key in ("degree", "field_of_study", "institution")
            ).casefold()
            candidate_level = _degree_level(candidate)
            level_satisfied = level is None or candidate_level == level
            if level is None and field is None:
                if req in candidate:
                    best = 100.0
                continue
            if level_satisfied and field:
                candidate_field = str(entry.get("field_of_study") or "").casefold()
                if field in candidate_field or candidate_field in field:
                    best = 100.0
                elif level_satisfied:
                    best = max(best, 50.0)
            elif level_satisfied:
                best = 100.0
        requirement_scores.append(best)
    return round(sum(requirement_scores) / len(requirement_scores), 2)


def _meaningful_keyword_set(jd: Dict[str, Any], known_names: Dict[str, str]) -> Set[str]:
    raw = list(jd.get("keywords", []))
    raw.extend(jd.get("required_skills", []))
    raw.extend(jd.get("preferred_skills", []))
    raw.extend(jd.get("soft_skills", []))
    normalized = {
        _canonical_skill(value, known_names).casefold()
        for value in raw
    }
    catalog_names = {name.casefold() for name in known_names.values()}
    allowed = catalog_names | SOFT_SKILL_TERMS
    return {
        keyword for keyword in normalized
        if keyword in allowed and keyword not in GENERIC_KEYWORDS
    }


def _keyword_score(jd: Dict[str, Any], resume_skills: Set[str], known_names: Dict[str, str]) -> Optional[float]:
    keywords = _meaningful_keyword_set(jd, known_names)
    if len(keywords) < MIN_MEANINGFUL_KEYWORDS:
        return None
    return round(sum(keyword in resume_skills for keyword in keywords) / len(keywords) * 100, 2)


def _overall_score(scores: Dict[str, Optional[float]]) -> tuple[Optional[float], Dict[str, float], List[str]]:
    available = [name for name, score in scores.items() if score is not None]
    if not available:
        return None, {}, []
    total_weight = sum(OVERALL_WEIGHTS[name] for name in available)
    normalized_weights = {
        name: round(OVERALL_WEIGHTS[name] / total_weight, 6)
        for name in available
    }
    score = sum(scores[name] * normalized_weights[name] for name in available)
    return round(score, 2), normalized_weights, available


def _build_explanations(
    result: MatchingResult,
    required: List[str],
    preferred: List[str],
    resume_skills: Set[str],
    resume: Dict[str, Any],
    jd: Dict[str, Any],
) -> None:
    matched_required = [skill for skill in required if skill.casefold() in resume_skills]
    matched_preferred = [skill for skill in preferred if skill.casefold() in resume_skills]
    result.matched_skills = _unique(matched_required + matched_preferred)
    result.missing_required_skills = [
        skill for skill in required if skill.casefold() not in resume_skills
    ]
    result.missing_preferred_skills = [
        skill for skill in preferred if skill.casefold() not in resume_skills
    ]

    if required and not result.missing_required_skills:
        result.strengths.append("All identified required skills are present in the resume profile.")
    elif matched_required:
        result.strengths.append(f"Matches {len(matched_required)} identified required skill(s).")
    if matched_preferred:
        result.strengths.append(f"Matches {len(matched_preferred)} identified preferred skill(s).")

    result.gaps.extend(
        f"Missing required skill: {skill}" for skill in result.missing_required_skills
    )
    result.gaps.extend(
        f"Missing preferred skill: {skill}" for skill in result.missing_preferred_skills
    )

    if jd.get("experience", {}).get("minimum_years") is not None or jd.get("experience", {}).get("maximum_years") is not None:
        years = _work_experience_years(resume)
        if years is None:
            result.gaps.append("Work experience duration could not be verified from the resume profile.")
        elif result.experience_match == 100:
            result.strengths.append("Explicit work experience meets the stated minimum.")
        else:
            result.gaps.append("Explicit work experience is below the stated minimum.")

    if jd.get("education"):
        if not resume.get("education"):
            result.gaps.append("Education could not be verified from the resume profile.")
        elif result.education_match == 100:
            result.strengths.append("The stated education requirement appears to be satisfied.")
        elif result.education_match is not None:
            result.gaps.append("The stated education requirement is only partially evidenced.")

    for skill in result.missing_required_skills:
        result.recommendations.append(
            f"If you have experience with {skill}, highlight it in the relevant resume section."
        )
    for skill in result.missing_preferred_skills:
        result.recommendations.append(
            f"If relevant, consider highlighting any experience with preferred skill {skill}."
        )
    if resume.get("projects") and required:
        result.recommendations.append(
            "Highlight projects that demonstrate your matched required skills."
        )
    result.recommendations = _unique(result.recommendations)


def match_resume_to_job(resume_profile: Any, jd_profile: Any) -> Dict[str, Any]:
    """Return a validated deterministic match result from structured profiles.

    Required skills count for 80% of the skill score when preferred skills
    also exist; preferred skills count for the remaining 20%. The overall
    score uses skill/experience/education/keyword weights of 50/20/15/15.
    Unavailable dimensions are excluded and the remaining weights are
    renormalized before calculating the overall score.
    """
    resume = validate_resume_profile(resume_profile)
    jd = validate_job_description_profile(jd_profile)
    known_names = _load_skill_names()
    resume_skills = _resume_skill_names(resume, known_names)
    required = _jd_skill_names(jd, "required_skills", known_names)
    preferred = _jd_skill_names(jd, "preferred_skills", known_names)

    result = MatchingResult()
    result.skill_match = _score_skill_match(required, preferred, resume_skills)
    result.experience_match = _experience_score(resume, jd)
    result.education_match = _education_score(resume, jd)
    result.keyword_match = _keyword_score(jd, resume_skills, known_names)

    scores = {
        "skill_match": result.skill_match,
        "experience_match": result.experience_match,
        "education_match": result.education_match,
        "keyword_match": result.keyword_match,
    }
    result.overall_match, weights, available = _overall_score(scores)
    result.score_method.available_dimensions = available
    result.score_method.weights = weights
    _build_explanations(result, required, preferred, resume_skills, resume, jd)

    payload = result.to_dict()
    validate_matching_result(payload)
    return payload
