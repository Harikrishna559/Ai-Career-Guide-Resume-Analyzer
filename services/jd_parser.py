"""Deterministic extraction of structured job-description profiles."""

import json
import re
from pathlib import Path

from services.profile_contracts import (
    create_empty_job_description_profile,
    validate_job_description_profile,
)


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SKILL_ALIASES = {
    "js": "JavaScript",
    "reactjs": "React",
    "react.js": "React",
    "postgres": "PostgreSQL",
    "ml": "Machine Learning",
}
SOFT_SKILLS = (
    "communication",
    "leadership",
    "teamwork",
    "problem solving",
    "critical thinking",
    "collaboration",
    "adaptability",
    "time management",
)
SECTION_TYPES = {
    "requirements": "required",
    "requirements and qualifications": "required",
    "required skills": "required",
    "must have": "required",
    "minimum requirements": "required",
    "qualifications": "unclassified",
    "preferred": "preferred",
    "preferred skills": "preferred",
    "nice to have": "preferred",
    "what you will do": "responsibilities",
    "what you'll do": "responsibilities",
    "responsibilities": "responsibilities",
    "role responsibilities": "responsibilities",
    "key responsibilities": "responsibilities",
    "job duties": "responsibilities",
    "education": "education",
    "education requirements": "education",
    "certifications": "certifications",
    "licenses and certifications": "certifications",
}
BULLET_RE = re.compile(r"^\s*(?:[-*•▪◦]|\d+[.)])\s+")

TITLE_LABEL_RE = re.compile(r"^\s*(?:job\s+title|position|role)\s*[:\-]\s*(.+)$", re.I)
COMPANY_LABEL_RE = re.compile(r"^\s*(?:company|employer|organization|organisation)\s*[:\-]\s*(.+)$", re.I)
LOCATION_LABEL_RE = re.compile(r"^\s*(?:job\s+)?location\s*[:\-]\s*(.+)$", re.I)
WORK_MODE_LABEL_RE = re.compile(r"^\s*(?:work\s+mode|work\s+arrangement)\s*[:\-]\s*(.+)$", re.I)
EMPLOYMENT_LABEL_RE = re.compile(r"^\s*(?:employment\s+type|job\s+type)\s*[:\-]\s*(.+)$", re.I)

EXPERIENCE_RANGE_RE = re.compile(
    r"\b(?P<minimum>\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*"
    r"(?P<maximum>\d+(?:\.\d+)?)\s*\+?\s*years?\b",
    re.I,
)
EXPERIENCE_PLUS_RE = re.compile(r"\b(?P<minimum>\d+(?:\.\d+)?)\s*\+\s*years?\b", re.I)
EXPERIENCE_SINGLE_RE = re.compile(
    r"\b(?P<minimum>\d+(?:\.\d+)?)\s+years?\s+(?:of\s+)?(?:relevant\s+)?experience\b",
    re.I,
)
SALARY_RE = re.compile(
    r"(?P<currency>₹|INR\b|Rs\.?\b|\$|USD\b)?\s*"
    r"(?P<minimum>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?:(?:-|–|—|to)\s*(?:₹|INR\b|Rs\.?\b|\$|USD\b)?\s*"
    r"(?P<maximum>\d[\d,]*(?:\.\d+)?)\s*)?"
    r"(?P<unit>LPA|L\.P\.A\.|LPM|L\.P\.M\.|lakhs?\s+per\s+(?:annum|year|month)|"
    r"per\s+month|monthly|per\s+year|annually|yearly|/month|/year|/mo|/yr|"
    r"k\s*(?:per\s+year|/year|/yr)?)",
    re.I,
)
DEGREE_RE = re.compile(
    r"\b(?:bachelor(?:'s)?(?:\s+degree)?|master(?:'s)?(?:\s+degree)?|"
    r"b\.?\s?tech|m\.?\s?tech|b\.?\s?e\.?|m\.?\s?e\.?|b\.?\s?sc|m\.?\s?sc|"
    r"bca|mca|mba|ph\.?d\.?)\b",
    re.I,
)
EDUCATION_WORDS_RE = re.compile(r"\b(?:degree|bachelor|master|B\.Tech|B\.E\.|M\.Tech|M\.E\.|BCA|MCA|MBA|Ph\.D\.)\b", re.I)
CERTIFICATION_RE = re.compile(r"\b(certified|certification|certificate|PMP)\b", re.I)
CERTIFICATE_NAME_RE = re.compile(
    r"\b(?:AWS Certified[^,;.\n]*|Azure Certified[^,;.\n]*|Google Cloud Certified[^,;.\n]*|PMP)\b",
    re.I,
)
EXPLICIT_SKILL_LIST_RE = re.compile(
    r"^\s*(?:skills?|technologies|tech stack|tools)\s*:\s*(.+)$", re.I
)
REQUIRED_CUE_RE = re.compile(
    r"\b(required|must\s+have|mandatory|essential|should\s+have|need(?:ed)?|minimum\s+requirement)\b",
    re.I,
)
PREFERRED_CUE_RE = re.compile(
    r"\b(preferred|nice\s+to\s+have|bonus|good\s+to\s+have|plus|desirable)\b",
    re.I,
)


def _load_catalog():
    with open(DATA_DIR / "skills.json", encoding="utf-8") as file:
        catalog = json.load(file)
    with open(DATA_DIR / "roles.json", encoding="utf-8") as file:
        roles = json.load(file)

    skills = []
    for item in catalog:
        for skill in item.get("skills", []):
            if isinstance(skill, str) and skill.strip():
                skills.append(skill.strip())
    if isinstance(roles, dict):
        titles = [str(title).strip() for title in roles]
    elif isinstance(roles, list):
        titles = [
            str(item["role"]).strip()
            for item in roles
            if isinstance(item, dict) and item.get("role")
        ]
    else:
        titles = []
    return _unique(skills), _unique(titles)


def _unique(values):
    result = []
    seen = set()
    for value in values:
        cleaned = str(value).strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def _term_pattern(term):
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", re.I)


def _skill_mentions(text, skills):
    canonical_by_alias = {skill.casefold(): skill for skill in skills}
    for alias, canonical in SKILL_ALIASES.items():
        if canonical.casefold() in canonical_by_alias:
            canonical_by_alias[alias.casefold()] = canonical_by_alias[canonical.casefold()]

    found = []
    patterns = []
    for alias, canonical in canonical_by_alias.items():
        # React.js is punctuation-sensitive; the boundary pattern still prevents
        # matches inside longer alphanumeric words such as JavaScript/Java.
        patterns.append((alias, canonical, _term_pattern(alias)))
    for alias, canonical, pattern in patterns:
        match = pattern.search(text)
        if match:
            found.append((match.start(), canonical))
    found.sort(key=lambda item: (item[0], item[1].casefold()))
    return _unique([skill for _, skill in found])


def _metadata(profile, field_name, source, confidence):
    profile.extraction.field_sources[field_name] = source
    profile.extraction.confidence[field_name] = confidence


def _clean_line(line):
    return BULLET_RE.sub("", line).strip()


def _normalized_heading(line):
    cleaned = line.strip().strip("#*_ ").rstrip(":").strip()
    return re.sub(r"\s+", " ", cleaned).casefold()


def _lines_and_sections(text):
    sections = []
    active_type = "unclassified"
    active_heading = None
    lines = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = _normalized_heading(line)
        section_type = SECTION_TYPES.get(heading)
        if section_type:
            if lines:
                sections.append((active_type, active_heading, lines))
            active_type = section_type
            active_heading = heading
            lines = []
            continue
        lines.append(line)
    if lines:
        sections.append((active_type, active_heading, lines))
    return sections


def _detect_work_mode(text):
    normalized = text.casefold()
    if re.search(r"\b(remote|work\s+from\s+home|work\s+remotely)\b", normalized):
        return "remote"
    if re.search(r"\bhybrid\b", normalized):
        return "hybrid"
    if re.search(r"\b(on[\s-]?site|onsite|in[\s-]office)\b", normalized):
        return "onsite"
    return None


def _detect_employment_type(text):
    normalized = text.casefold()
    for phrase, value in (
        (r"\bfull[\s-]?time\b", "full-time"),
        (r"\bpart[\s-]?time\b", "part-time"),
        (r"\bcontract(?:or)?\b", "contract"),
        (r"\bintern(?:ship)?\b", "internship"),
        (r"\btemporary\b", "temporary"),
    ):
        if re.search(phrase, normalized):
            return value
    return None


def _extract_title(lines, role_titles):
    for line in lines[:8]:
        match = TITLE_LABEL_RE.match(line)
        if match and match.group(1).strip():
            return match.group(1).strip().strip(" -|")

    for line in lines[:6]:
        for title in sorted(role_titles, key=len, reverse=True):
            if line.casefold().strip(" -*_") == title.casefold():
                return title

    common_titles = (
        "Software Engineer", "Python Developer", "Frontend Developer",
        "Full Stack Developer", "Data Analyst", "Machine Learning Engineer",
    )
    for line in lines[:6]:
        for title in common_titles:
            if re.search(rf"(?<!\w){re.escape(title)}(?!\w)", line, re.I):
                return title
    return None


def _extract_company(lines):
    for line in lines[:10]:
        match = COMPANY_LABEL_RE.match(line)
        if match and match.group(1).strip():
            return match.group(1).strip().strip(" -|")
    for line in lines[:5]:
        match = re.match(r"^\s*(.+?)\s+is\s+hiring\b", line, re.I)
        if match:
            candidate = match.group(1).strip(" -*|")
            if candidate and len(candidate) <= 100:
                return candidate
    return None


def _extract_location(lines):
    for line in lines[:20]:
        match = LOCATION_LABEL_RE.match(line)
        if match and match.group(1).strip():
            return match.group(1).strip().strip(" -|")
    return None


def _extract_compensation(text, profile):
    match = SALARY_RE.search(text)
    if not match:
        return
    currency_token = (match.group("currency") or "").casefold()
    if currency_token in {"₹", "inr"} or currency_token.startswith("rs"):
        currency = "INR"
    elif currency_token in {"$", "usd"}:
        currency = "USD"
    else:
        currency = "INR" if re.search(r"\b(?:lpa|lpm|lakhs?)\b", match.group("unit"), re.I) else None

    minimum = float(match.group("minimum").replace(",", ""))
    maximum = float(match.group("maximum").replace(",", "")) if match.group("maximum") else None
    unit = re.sub(r"\s+", " ", match.group("unit").casefold())

    if re.search(r"\b(?:lpa|l\.p\.a\.|lakhs?\s+per\s+(?:annum|year))\b", unit):
        multiplier, period = 100000, "year"
    elif re.search(r"\b(?:lpm|l\.p\.m\.|lakhs?\s+per\s+month)\b", unit):
        multiplier, period = 100000, "month"
    elif re.search(r"\b(?:per\s+month|monthly|/month|/mo)\b", unit):
        multiplier, period = 1, "month"
    elif re.search(r"\b(?:per\s+year|annually|yearly|/year|/yr|k)\b", unit):
        multiplier, period = (1000 if re.search(r"\bk\b", unit) else 1), "year"
    else:
        return

    profile.compensation.minimum = minimum * multiplier
    profile.compensation.maximum = maximum * multiplier if maximum is not None else None
    profile.compensation.currency = currency
    profile.compensation.period = period
    _metadata(profile, "compensation", "explicit_salary_text", 0.9)


def _extract_experience(text, profile):
    range_match = EXPERIENCE_RANGE_RE.search(text)
    if range_match:
        profile.experience.minimum_years = float(range_match.group("minimum"))
        profile.experience.maximum_years = float(range_match.group("maximum"))
        _metadata(profile, "experience.minimum_years", "explicit_year_range", 0.95)
        _metadata(profile, "experience.maximum_years", "explicit_year_range", 0.95)
    else:
        plus_match = EXPERIENCE_PLUS_RE.search(text)
        single_match = EXPERIENCE_SINGLE_RE.search(text)
        match = plus_match or single_match
        if match:
            profile.experience.minimum_years = float(match.group("minimum"))
            _metadata(profile, "experience.minimum_years", "explicit_year_requirement", 0.9)

    lowered = text.casefold()
    if re.search(r"\b(fresh\s+graduate|recent\s+graduate|entry[\s-]?level|graduate\s+role)\b", lowered):
        profile.experience.level = "entry"
        _metadata(profile, "experience.level", "explicit_level_wording", 0.9)
    elif re.search(r"\bmid[\s-]?level\b", lowered):
        profile.experience.level = "mid"
        _metadata(profile, "experience.level", "explicit_level_wording", 0.9)
    elif re.search(r"\bsenior\b", lowered):
        profile.experience.level = "senior"
        _metadata(profile, "experience.level", "explicit_level_wording", 0.9)


def _extract_skills(sections, full_text, profile, catalog):
    required = []
    preferred = []
    keywords = _skill_mentions(full_text, catalog)
    soft_skills = _skill_mentions(full_text, SOFT_SKILLS)

    for section_type, _, lines in sections:
        for line in lines:
            mentions = _skill_mentions(line, catalog)
            required_cue = REQUIRED_CUE_RE.search(line)
            preferred_cue = PREFERRED_CUE_RE.search(line)
            if preferred_cue and not required_cue:
                preferred.extend(mentions)
            elif required_cue or section_type == "required":
                required.extend(mentions)
            elif section_type == "preferred":
                preferred.extend(mentions)

            explicit_list = EXPLICIT_SKILL_LIST_RE.match(line)
            if explicit_list:
                # Preserve explicitly listed but uncatalogued skill terms as
                # keywords, without assigning required/preferred status.
                alias_map = {alias.casefold(): canonical for alias, canonical in SKILL_ALIASES.items()}
                keywords.extend(
                    alias_map.get(item.casefold(), item)
                    for item in _split_skill_list(explicit_list.group(1))
                )

    profile.required_skills = _unique(required)
    required_names = {skill.casefold() for skill in profile.required_skills}
    profile.preferred_skills = [
        skill for skill in _unique(preferred) if skill.casefold() not in required_names
    ]
    profile.soft_skills = soft_skills
    profile.keywords = _unique(keywords + soft_skills)
    if profile.required_skills:
        _metadata(profile, "required_skills", "explicit_requirement_wording", 0.9)
    if profile.preferred_skills:
        _metadata(profile, "preferred_skills", "explicit_preference_wording", 0.9)
    if profile.soft_skills:
        _metadata(profile, "soft_skills", "explicit_catalog_mentions", 0.85)
    if profile.keywords:
        _metadata(profile, "keywords", "catalog_and_explicit_skill_mentions", 0.85)


def _split_skill_list(value):
    parts = re.split(r"[,;|]", value)
    result = []
    for part in parts:
        item = re.sub(r"^(?:and|or)\s+", "", part.strip(), flags=re.I)
        item = re.sub(r"\s+(?:and|or)$", "", item, flags=re.I).strip()
        if item and len(item) <= 60:
            result.append(item)
    return result


def _extract_responsibilities(sections, profile):
    for section_type, _, lines in sections:
        if section_type != "responsibilities":
            continue
        profile.responsibilities.extend(
            _clean_line(line)
            for line in lines
            if BULLET_RE.match(line) and _clean_line(line)
        )
    profile.responsibilities = _unique(profile.responsibilities)
    if profile.responsibilities:
        _metadata(profile, "responsibilities", "responsibilities_section", 0.95)


def _extract_education_and_certifications(sections, profile):
    education = []
    certifications = []
    for section_type, _, lines in sections:
        for line in lines:
            cleaned = _clean_line(line)
            if not cleaned:
                continue
            if section_type == "education" or EDUCATION_WORDS_RE.search(cleaned):
                if DEGREE_RE.search(cleaned) and cleaned not in education:
                    education.append(cleaned)
            if section_type == "certifications":
                certifications.append(cleaned)
            elif CERTIFICATION_RE.search(cleaned):
                certifications.extend(
                    match.group(0).strip()
                    for match in CERTIFICATE_NAME_RE.finditer(cleaned)
                )

    profile.education = _unique(education)
    profile.certifications = _unique(certifications)
    if profile.education:
        _metadata(profile, "education", "explicit_education_requirement", 0.9)
    if profile.certifications:
        _metadata(profile, "certifications", "explicit_certification_wording", 0.9)


def parse_job_description(text):
    """Parse a JD into a validated version-1.0 profile without AI calls."""
    content = text or ""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    profile = create_empty_job_description_profile()
    catalog, role_titles = _load_catalog()

    title = _extract_title(lines, role_titles)
    if title:
        profile.job_title = title
        _metadata(profile, "job_title", "jd_header", 0.9)

    company = _extract_company(lines)
    if company:
        profile.company = company
        _metadata(profile, "company", "explicit_company_header", 0.9)

    location = _extract_location(lines)
    if location:
        profile.location = location
        _metadata(profile, "location", "explicit_location_header", 0.95)

    mode_line = next((line for line in lines if WORK_MODE_LABEL_RE.match(line)), "")
    profile.work_mode = _detect_work_mode(mode_line or content)
    if profile.work_mode:
        _metadata(profile, "work_mode", "explicit_work_arrangement", 0.9)

    employment_line = next((line for line in lines if EMPLOYMENT_LABEL_RE.match(line)), "")
    profile.employment_type = _detect_employment_type(employment_line or content)
    if profile.employment_type:
        _metadata(profile, "employment_type", "explicit_employment_wording", 0.9)

    sections = _lines_and_sections(content)
    _extract_compensation(content, profile)
    _extract_experience(content, profile)
    _extract_skills(sections, content, profile, catalog)
    _extract_responsibilities(sections, profile)
    _extract_education_and_certifications(sections, profile)

    payload = profile.to_dict()
    validate_job_description_profile(payload)
    return payload
