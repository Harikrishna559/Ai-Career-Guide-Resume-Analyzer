import json
import os
import re
import zipfile
from pathlib import Path

from services.profile_contracts import (
    EducationEntry,
    EducationGrade,
    ExperienceEntry,
    ProjectEntry,
    create_empty_resume_profile,
    validate_resume_profile,
)

try:
    from PyPDF2 import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

try:
    from docx import Document
except Exception:  # pragma: no cover
    Document = None


SKILL_KEYWORDS = [
    "python", "java", "javascript", "html", "css", "sql", "rest", "api", "git",
    "docker", "aws", "azure", "linux", "flask", "django", "spring", "react",
    "node", "mongodb", "mysql", "postgresql", "excel", "power bi", "tableau",
    "machine learning", "deep learning", "data analysis", "testing", "pytest", "c++",
    "c#", "problem solving", "data structures", "algorithms", "cloud", "kubernetes"
]

SOFT_SKILL_KEYWORDS = [
    "communication", "teamwork", "leadership", "collaboration",
    "problem solving", "adaptability", "time management",
]

SKILL_ALIASES = {
    "js": "JavaScript",
    "reactjs": "React",
    "react.js": "React",
    "postgres": "PostgreSQL",
    "ml": "Machine Learning",
}

SKILL_CATEGORY_BY_DATA_CATEGORY = {
    "programming languages": "programming_languages",
    "web development": "other",
    "databases": "databases",
    "frameworks": "frameworks",
    "cloud & devops": "tools",
    "data & ai": "other",
}

SECTION_NAMES = {
    "summary": {"summary", "professional summary", "profile", "professional profile", "about", "about me"},
    "education": {"education", "academic background", "academic qualifications", "educational background"},
    "experience": {"experience", "work experience", "professional experience", "employment history", "work history"},
    "internship": {"internship", "internships"},
    "projects": {"project", "projects", "personal projects", "academic projects"},
    "certifications": {"certification", "certifications", "certificates", "licenses and certifications"},
    "achievements": {"achievement", "achievements", "accomplishments", "awards and achievements", "awards"},
    "skills": {"skills", "technical skills", "technology", "technologies", "technical expertise"},
}

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_EXTRACTED_TEXT_CHARS = 100_000
MAX_PDF_PAGES = 25
MAX_DOCX_MEMBERS = 2_000
MAX_DOCX_EXPANDED_BYTES = 20 * 1024 * 1024
MAX_DOCX_DOCUMENT_XML_BYTES = 10 * 1024 * 1024
MAX_TEXT_FILE_BYTES = MAX_EXTRACTED_TEXT_CHARS * 4


class ResumeFileError(ValueError):
    """The uploaded resume is invalid or exceeds safe processing limits."""


def _validate_upload_file(path):
    suffix = path.suffix.lower()
    try:
        file_size = path.stat().st_size
        if file_size == 0 or file_size > MAX_UPLOAD_BYTES:
            raise ResumeFileError

        with path.open("rb") as file:
            signature = file.read(1024)

        if suffix == ".pdf":
            if b"%PDF-" not in signature:
                raise ResumeFileError
        elif suffix == ".docx":
            if not signature.startswith(b"PK"):
                raise ResumeFileError
            with zipfile.ZipFile(path) as archive:
                members = archive.infolist()
                if (
                    len(members) > MAX_DOCX_MEMBERS
                    or sum(member.file_size for member in members) > MAX_DOCX_EXPANDED_BYTES
                    or any(
                        member.filename.startswith("/")
                        or ".." in Path(member.filename).parts
                        for member in members
                    )
                ):
                    raise ResumeFileError
                member_sizes = {member.filename: member.file_size for member in members}
                if (
                    "[Content_Types].xml" not in member_sizes
                    or "word/document.xml" not in member_sizes
                    or member_sizes["word/document.xml"] > MAX_DOCX_DOCUMENT_XML_BYTES
                ):
                    raise ResumeFileError
        elif suffix == ".txt":
            if file_size > MAX_TEXT_FILE_BYTES:
                raise ResumeFileError
            content = path.read_bytes()
            if (
                content.startswith((b"%PDF-", b"PK"))
                or any(byte < 32 and byte not in {9, 10, 12, 13} for byte in content)
            ):
                raise ResumeFileError
        else:
            raise ResumeFileError
    except ResumeFileError:
        raise
    except (OSError, zipfile.BadZipFile, ValueError):
        raise ResumeFileError from None

ALL_SECTION_HEADINGS = {
    heading: section
    for section, headings in SECTION_NAMES.items()
    for heading in headings
}

EMAIL_PATTERN = re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.IGNORECASE)
URL_PATTERN = re.compile(
    r"(?:(?:https?://|www\.)[^\s<>()]+|(?:[A-Z0-9-]+\.)+(?:com|org|net|io|dev|me|co|in)(?:/[^\s<>()]*)?)",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(
    r"\b(?:(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+)?"
    r"(?:19|20)\d{2}\b|\bPresent\b|\bCurrent\b",
    re.IGNORECASE,
)
DEGREE_PATTERN = re.compile(
    r"\b(?:B\.?\s?Tech|M\.?\s?Tech|B\.?\s?E\.?|M\.?\s?E\.?|B\.?\s?Sc|M\.?\s?Sc|"
    r"B\.?\s?Com|M\.?\s?Com|BCA|MCA|MBA|Ph\.?D\.?|Bachelor(?:'s)?|Master(?:'s)?)\b",
    re.IGNORECASE,
)
EDUCATION_FIELD_PATTERN = re.compile(
    r"\bin\s+(.+?)(?=,|\s+-\s+|\s+\(|$)", re.IGNORECASE
)
GRADE_PATTERN = re.compile(
    r"\b(?:CGPA|GPA|percentage|percent|score)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(%|/[\d.]+)?",
    re.IGNORECASE,
)
EXPERIENCE_HEADING_RE = re.compile(
    r"^(?:work\s+)?(?:professional\s+)?experience(?:\s+.*)?$|^employment\s+history$|^work\s+history$",
    re.IGNORECASE,
)
BULLET_RE = re.compile(r"^\s*(?:[-*•▪◦]|\d+[.)])\s+")
EXPLICIT_LABEL_RE = re.compile(r"^\s*(?:location|based in|city)\s*[:\-]\s*(.+)$", re.IGNORECASE)
ORGANIZATION_LABEL_RE = re.compile(
    r"^\s*(?:company|organization|organisation|employer)\s*[:\-]\s*(.+)$",
    re.IGNORECASE,
)


def _read_pdf_text(path):
    if PdfReader is None:
        raise ResumeFileError
    text_chunks = []
    try:
        reader = PdfReader(path)
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ResumeFileError
        extracted_chars = 0
        for page in reader.pages:
            text = page.extract_text() or ""
            text_chunks.append(text)
            extracted_chars += len(text)
            if extracted_chars > MAX_EXTRACTED_TEXT_CHARS:
                raise ResumeFileError
        return "\n".join(text_chunks)
    except ResumeFileError:
        raise
    except Exception:
        raise ResumeFileError from None


def _read_docx_text(path):
    if Document is None:
        raise ResumeFileError
    try:
        doc = Document(path)
        paragraphs = []
        extracted_chars = 0
        for paragraph in doc.paragraphs:
            text = paragraph.text
            if text.strip():
                extracted_chars += len(text) + (1 if paragraphs else 0)
                if extracted_chars > MAX_EXTRACTED_TEXT_CHARS:
                    raise ResumeFileError
                paragraphs.append(text)
        return "\n".join(paragraphs)
    except ResumeFileError:
        raise
    except Exception:
        raise ResumeFileError from None


def _read_txt_text(path):
    try:
        raw = Path(path).read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        if len(text) > MAX_EXTRACTED_TEXT_CHARS:
            raise ResumeFileError
        return text
    except ResumeFileError:
        raise
    except OSError:
        raise ResumeFileError from None


def extract_text_from_resume(file_path):
    path = Path(file_path)
    suffix = path.suffix.lower()
    _validate_upload_file(path)
    if suffix == ".pdf":
        text = _read_pdf_text(str(path))
    elif suffix == ".docx":
        text = _read_docx_text(str(path))
    else:
        text = _read_txt_text(str(path))
    if not text.strip():
        raise ResumeFileError
    return text


def _heading_kind(line):
    heading = re.sub(r"[\s:|—–-]+$", "", line.strip()).lower()
    heading = re.sub(r"\s+", " ", heading)
    if heading in ALL_SECTION_HEADINGS:
        return ALL_SECTION_HEADINGS[heading]
    if EXPERIENCE_HEADING_RE.fullmatch(heading):
        return "experience"
    return None


def _split_sections(text):
    sections = {}
    current = None
    preamble = []
    for line in (text or "").splitlines():
        kind = _heading_kind(line)
        if kind:
            current = kind
            sections.setdefault(current, []).append([])
            continue
        if current is None:
            preamble.append(line)
        else:
            if not sections[current]:
                sections[current].append([])
            if not line.strip():
                if sections[current][-1]:
                    sections[current].append([])
                continue
            sections[current][-1].append(line)
    sections["header"] = [preamble]
    return sections


def _section_text(sections, kind):
    return "\n".join(
        line
        for block in sections.get(kind, [])
        for line in block
    ).strip()


def _field_source(profile, path, source, confidence):
    profile.extraction.field_sources[path] = source
    profile.extraction.confidence[path] = confidence


def _header_lines(text):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if _heading_kind(line):
            return lines[:index]
    return lines[:8]


def _extract_email(header, full_text, profile):
    match = EMAIL_PATTERN.search(header) or EMAIL_PATTERN.search(full_text)
    if match:
        profile.personal.email = match.group(0).rstrip(".,;")
        _field_source(profile, "personal.email", "contact_header", 0.99)


def _extract_phone(header, full_text, profile):
    candidates = re.findall(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)", header)
    if not candidates:
        candidates = re.findall(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)", full_text[:1200])
    for candidate in candidates:
        digits = re.sub(r"\D", "", candidate)
        if 10 <= len(digits) <= 15:
            profile.personal.phone = re.sub(r"\s+", " ", candidate.strip())
            _field_source(profile, "personal.phone", "contact_header", 0.85)
            return


def _extract_links(header, profile):
    found = []
    for match in URL_PATTERN.finditer(header):
        value = match.group(0).rstrip(".,;)")
        if value not in found:
            found.append(value)

    other = []
    for value in found:
        normalized = value.lower()
        if "linkedin.com" in normalized:
            profile.personal.links.linkedin = value
            _field_source(profile, "personal.links.linkedin", "contact_header", 0.99)
        elif "github.com" in normalized:
            profile.personal.links.github = value
            _field_source(profile, "personal.links.github", "contact_header", 0.99)
        elif profile.personal.links.portfolio is None:
            profile.personal.links.portfolio = value
            _field_source(profile, "personal.links.portfolio", "contact_header", 0.7)
        else:
            other.append(value)
    profile.personal.links.other = other


def _extract_location(header, profile):
    for line in header:
        match = EXPLICIT_LABEL_RE.match(line)
        if match:
            location = match.group(1).strip().strip(",;")
            if location and len(location) <= 100:
                profile.personal.location = location
                _field_source(profile, "personal.location", "explicit_header_label", 0.95)
                return


def _extract_name(header, profile):
    for line in header[:5]:
        candidate = line.strip()
        if (
            len(candidate) > 60
            or "@" in candidate
            or URL_PATTERN.search(candidate)
            or re.search(r"\d", candidate)
            or re.search(r"\b(resume|curriculum vitae|cv|linkedin|github|phone|email)\b", candidate, re.I)
            or re.search(r"\b(developer|engineer|analyst|designer|manager|consultant|intern|student)\b", candidate, re.I)
        ):
            continue
        words = candidate.split()
        if 2 <= len(words) <= 4 and all(re.fullmatch(r"[A-Z][A-Za-z'’-]*", word) for word in words):
            profile.personal.name = candidate
            _field_source(profile, "personal.name", "resume_header", 0.75)
            return


def _extract_summary(sections, profile):
    value = _section_text(sections, "summary")
    if value:
        profile.summary = value
        _field_source(profile, "summary", "summary_section", 0.95)


def _education_entries(sections, profile):
    entries = []
    for block in sections.get("education", []):
        lines = [line.strip() for line in block if line.strip()]
        if not lines:
            continue

        entry = EducationEntry()
        evidence = False
        degree_line = next((line for line in lines if DEGREE_PATTERN.search(line)), None)
        if degree_line:
            degree_match = DEGREE_PATTERN.search(degree_line)
            entry.degree = degree_match.group(0).strip()
            remainder = degree_line[degree_match.end():]
            field_match = EDUCATION_FIELD_PATTERN.search(remainder)
            if not field_match:
                field_match = EDUCATION_FIELD_PATTERN.search(degree_line)
            if field_match:
                entry.field_of_study = field_match.group(1).strip(" ,.-")
            evidence = True

        institution = next(
            (
                line for line in lines
                if re.search(r"\b(university|college|institute|school)\b", line, re.IGNORECASE)
            ),
            None,
        )
        if institution:
            entry.institution = institution
            evidence = True

        for line in lines:
            year_match = re.search(r"\b(?:19|20)\d{2}\b", line)
            if year_match and entry.graduation_year is None:
                entry.graduation_year = int(year_match.group(0))
                evidence = True
            grade_match = GRADE_PATTERN.search(line)
            if grade_match and entry.grade.value is None:
                entry.grade.value = float(grade_match.group(1))
                scale = grade_match.group(2)
                entry.grade.scale = "%" if scale == "%" else scale.lstrip("/") if scale else None
                evidence = True

        if evidence:
            index = len(entries)
            entries.append(entry)
            for field_name, value in (
                ("degree", entry.degree),
                ("field_of_study", entry.field_of_study),
                ("institution", entry.institution),
                ("graduation_year", entry.graduation_year),
                ("grade", entry.grade.value),
            ):
                if value is not None:
                    _field_source(profile, f"education.{index}.{field_name}", "education_section", 0.85)
    return entries


def _entry_blocks(sections, kinds):
    blocks = []
    for kind in kinds:
        blocks.extend((kind, block) for block in sections.get(kind, []))
    return blocks


def _extract_experience(sections, profile):
    entries = []
    for section_kind, block in _entry_blocks(sections, ("experience", "internship")):
        lines = [line.strip() for line in block if line.strip()]
        if not lines:
            continue
        body_lines = [BULLET_RE.sub("", line).strip() for line in lines]
        title_line = next((line for line in body_lines if not DATE_PATTERN.search(line)), None)
        if title_line is None:
            continue

        explicit_org = re.search(r"\b(?:at|@)\s+([A-Z][A-Za-z0-9&.,' -]{1,60})", title_line)
        title = title_line
        organization = None
        if explicit_org:
            title = title_line[:explicit_org.start()].strip(" ,-")
            organization = explicit_org.group(1).strip(" ,-")
        if organization is None:
            for line in lines:
                organization_match = ORGANIZATION_LABEL_RE.match(line)
                if organization_match:
                    organization = organization_match.group(1).strip()
                    break
        kind = "internship" if section_kind == "internship" or re.search(r"\bintern\b", title, re.I) else "work"

        date_lines = [line for line in lines if DATE_PATTERN.search(line)]
        dates = DATE_PATTERN.findall("\n".join(date_lines))
        normalized_dates = [re.sub(r"\s+", " ", date).strip() for date in dates]
        location = None
        for line in lines:
            location_match = EXPLICIT_LABEL_RE.match(line)
            if location_match:
                location = location_match.group(1).strip().strip(",;")
                break
        responsibilities = []
        achievements = []
        for line in lines:
            if not BULLET_RE.match(line):
                continue
            content = BULLET_RE.sub("", line).strip()
            if re.search(r"\b(achieved|increased|reduced|improved|saved|delivered|awarded)\b|\b\d+(?:\.\d+)?%", content, re.I):
                achievements.append(content)
            else:
                responsibilities.append(content)

        entry = ExperienceEntry(
            kind=kind,
            job_title=title or None,
            organization=organization,
            location=location,
            start_date=normalized_dates[0] if normalized_dates else None,
            end_date=normalized_dates[1] if len(normalized_dates) > 1 else None,
            responsibilities=responsibilities,
            achievements=achievements,
        )
        index = len(entries)
        entries.append(entry)
        _field_source(profile, f"experience.{index}.job_title", "experience_section", 0.7)
        _field_source(profile, f"experience.{index}.kind", "experience_section", 0.9)
        if organization:
            _field_source(profile, f"experience.{index}.organization", "experience_section", 0.75)
        if location:
            _field_source(profile, f"experience.{index}.location", "explicit_experience_label", 0.95)
        if normalized_dates:
            _field_source(profile, f"experience.{index}.dates", "experience_section", 0.8)
    return entries


def _extract_projects(sections, profile):
    entries = []
    for block in sections.get("projects", []):
        lines = [line.strip() for line in block if line.strip()]
        if not lines:
            continue
        name_line = BULLET_RE.sub("", lines[0]).strip()
        name = re.split(r"\s+[|—–-]\s+|\s*:\s*", name_line, maxsplit=1)[0].strip()
        description_parts = []
        technologies = []
        achievements = []
        for line in lines[1:]:
            content = BULLET_RE.sub("", line).strip()
            tech_match = re.match(r"^(?:technologies|tech stack|tools used)\s*:\s*(.+)$", content, re.I)
            if tech_match:
                technologies.extend(_split_delimited(tech_match.group(1)))
            elif re.match(r"^(?:achievement|result|impact)\s*:\s*", content, re.I):
                achievements.append(re.sub(r"^(?:achievement|result|impact)\s*:\s*", "", content, flags=re.I))
            elif content:
                description_parts.append(content)
        entry = ProjectEntry(
            name=name or None,
            description=" ".join(description_parts) or None,
            technologies=_normalized_skill_values(technologies),
            achievements=achievements,
        )
        index = len(entries)
        entries.append(entry)
        _field_source(profile, f"projects.{index}.name", "projects_section", 0.8)
        if entry.description:
            _field_source(profile, f"projects.{index}.description", "projects_section", 0.75)
        if entry.technologies:
            _field_source(profile, f"projects.{index}.technologies", "explicit_project_label", 0.95)
    return entries


def _split_delimited(value):
    return [item.strip() for item in re.split(r"[,;|]", value) if item.strip()]


def _unique_values(values):
    seen = set()
    output = []
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            output.append(value)
    return output


def _load_skill_catalog():
    catalog_path = Path(__file__).resolve().parent.parent / "data" / "skills.json"
    with open(catalog_path, "r", encoding="utf-8") as file:
        catalog = json.load(file)
    return catalog


def _skill_patterns(canonical):
    alias = SKILL_ALIASES.get(canonical.casefold())
    aliases = {canonical}
    if alias:
        aliases.add(alias)
    if canonical.casefold() == "javascript":
        aliases.add("JS")
    if canonical.casefold() == "react":
        aliases.update({"ReactJS", "React.js"})
    if canonical.casefold() == "postgresql":
        aliases.add("Postgres")
    if canonical.casefold() == "machine learning":
        aliases.add("ML")
    return [
        re.compile(rf"(?<![A-Za-z0-9]){re.escape(item)}(?![A-Za-z0-9])", re.IGNORECASE)
        for item in aliases
    ]


def _normalized_skill_values(values, canonical_names=None):
    if canonical_names is None:
        canonical_names = {
            skill.casefold(): skill
            for item in _load_skill_catalog()
            for skill in item.get("skills", [])
        }
    aliases = {alias.casefold(): name for alias, name in SKILL_ALIASES.items()}
    normalized = []
    for value in values:
        canonical = aliases.get(value.casefold(), value)
        canonical = canonical_names.get(canonical.casefold(), canonical)
        normalized.append(canonical)
    return _unique_values(normalized)


def _extract_skills(text, profile):
    categories = profile.skills
    category_values = {name: getattr(categories, name) for name in (
        "programming_languages", "frameworks", "databases", "cloud", "tools", "soft_skills", "other"
    )}
    found = set()
    catalog = _load_skill_catalog()
    canonical_names = {
        skill.casefold(): skill
        for item in catalog
        for skill in item.get("skills", [])
    }
    for item in catalog:
        data_category = str(item.get("category", "")).casefold()
        for skill in item.get("skills", []):
            known_category = _category_for_skill(skill)
            if known_category != "other":
                category = known_category
            elif data_category == "cloud & devops":
                category = "cloud" if skill.casefold() in {"aws", "azure", "gcp", "cloud"} else "tools"
            else:
                category = SKILL_CATEGORY_BY_DATA_CATEGORY.get(data_category, "other")
            if any(pattern.search(text) for pattern in _skill_patterns(skill)):
                found.add((skill, category))

    for skill in SKILL_KEYWORDS:
        canonical = SKILL_ALIASES.get(skill.casefold(), skill)
        if any(pattern.search(text) for pattern in _skill_patterns(canonical)):
            display_name = canonical_names.get(canonical.casefold(), canonical)
            found.add((display_name, _category_for_skill(display_name)))

    for skill in SOFT_SKILL_KEYWORDS:
        if any(pattern.search(text) for pattern in _skill_patterns(skill)):
            found.add((skill.title(), "soft_skills"))

    for skill, category in sorted(found, key=lambda item: (item[1], item[0].casefold())):
        if skill not in category_values[category]:
            category_values[category].append(skill)
    for category, values in category_values.items():
        if values:
            _field_source(profile, f"skills.{category}", "skills_catalog_and_explicit_mentions", 0.9)


def _category_for_skill(skill):
    normalized = skill.casefold()
    categories = {
        "programming_languages": {"python", "java", "javascript", "c++", "c#"},
        "frameworks": {"flask", "django", "spring", "spring boot", "react", "node"},
        "databases": {"sql", "mongodb", "mysql", "postgresql"},
        "cloud": {"aws", "azure", "cloud"},
        "tools": {"git", "docker", "linux", "pytest", "kubernetes", "excel", "power bi", "tableau"},
    }
    for category, values in categories.items():
        if normalized in values:
            return category
    return "other"


def _extract_certifications(sections, profile):
    values = []
    for block in sections.get("certifications", []):
        for line in block:
            cleaned = BULLET_RE.sub("", line).strip()
            if cleaned:
                values.append(cleaned)
    if not values:
        values = [
            value.strip()
            for value in re.findall(
                r"(?:certification|certified|certificate)[:\-]?\s*([^\n]+)",
                _section_text(sections, "header") + "\n" + "\n".join(
                    line for blocks in sections.values() for block in blocks for line in block
                ),
                flags=re.IGNORECASE,
            )
            if value.strip()
        ]
    profile.certifications = _unique_values(values)
    if profile.certifications:
        _field_source(profile, "certifications", "certification_section_or_label", 0.85)


def _extract_achievements(sections, profile):
    values = []
    for block in sections.get("achievements", []):
        values.extend(BULLET_RE.sub("", line).strip() for line in block if line.strip())
    profile.achievements = _unique_values(values)
    if profile.achievements:
        _field_source(profile, "achievements", "achievements_section", 0.9)


def parse_resume_profile(resume_text):
    """Extract a deterministic, validated Resume Profile from resume text."""
    text = resume_text or ""
    sections = _split_sections(text)
    profile = create_empty_resume_profile()
    header = "\n".join(_header_lines(text))

    _extract_name(_header_lines(text), profile)
    _extract_email(header, text[:1600], profile)
    _extract_phone(header, text[:1600], profile)
    _extract_links(header, profile)
    _extract_location(_header_lines(text), profile)
    _extract_summary(sections, profile)

    profile.education = _education_entries(sections, profile)
    profile.experience = _extract_experience(sections, profile)
    profile.projects = _extract_projects(sections, profile)
    _extract_skills(text, profile)
    _extract_certifications(sections, profile)
    _extract_achievements(sections, profile)

    all_skills = [
        skill
        for category in (
            profile.skills.programming_languages,
            profile.skills.frameworks,
            profile.skills.databases,
            profile.skills.cloud,
            profile.skills.tools,
            profile.skills.soft_skills,
            profile.skills.other,
        )
        for skill in category
    ]
    profile.keywords = _unique_values(all_skills)
    if profile.keywords:
        _field_source(profile, "keywords", "normalized_detected_skills", 0.9)

    payload = profile.to_dict()
    validate_resume_profile(payload)
    return payload


def parse_resume_details(resume_text):
    text = resume_text or ""
    text_lower = text.lower()
    deduped = []
    for skill in SKILL_KEYWORDS:
        if skill.lower() in text_lower and skill not in deduped:
            deduped.append(skill)

    education = []
    for pattern in [r"b\.tech[^\n]*", r"b\.e\.[^\n]*", r"m\.tech[^\n]*", r"b\.sc[^\n]*", r"m\.sc[^\n]*", r"b\.com[^\n]*", r"bca[^\n]*"]:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        education.extend(matches)
    education = [e.strip() for e in education if e.strip()][:5]

    projects = []
    for match in re.findall(r"project[s]?[:\-]?\s*([^\n]+)", text, flags=re.IGNORECASE):
        projects.append(match.strip())
    projects = projects[:5]

    experience = []
    for match in re.findall(r"(?:internship|experience|worked|developed|engineer|developer)[^\n]{0,120}", text, flags=re.IGNORECASE):
        experience.append(match.strip())
    experience = experience[:5]

    certifications = []
    for match in re.findall(r"(?:certification|certified|certificate)[:\-]?\s*([^\n]+)", text, flags=re.IGNORECASE):
        certifications.append(match.strip())
    certifications = certifications[:5]

    return {
        "skills": deduped,
        "education": education,
        "projects": projects,
        "experience": experience,
        "certifications": certifications,
        "keywords": deduped,
        "resume_length": len(text.split()),
        "resume_profile": parse_resume_profile(text),
    }


def get_resume_health(resume_text, parsed):
    text = resume_text or ""
    summary = {
        "resume_length": "🟢 Good" if len(text.split()) >= 150 else "🟡 Needs Improvement",
        "contact_information": "🟢 Good" if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text) else "🔴 Missing",
        "skills_section": "🟢 Good" if parsed.get("skills") else "🔴 Missing",
        "projects": "🟢 Good" if parsed.get("projects") else "🟡 Needs Improvement",
        "education": "🟢 Good" if parsed.get("education") else "🟡 Needs Improvement",
        "certifications": "🟢 Good" if parsed.get("certifications") else "🟡 Needs Improvement",
        "action_verbs": "🟢 Good" if re.search(r"(?:developed|built|designed|managed|improved|created|led)", text, flags=re.IGNORECASE) else "🟡 Needs Improvement",
        "duplicate_content": "🟢 Good" if len(set(text.lower().split())) > 0 else "🔴 Missing",
        "grammar": "🟢 Good" if len(text) > 0 else "🔴 Missing",
        "keyword_relevance": "🟢 Good" if parsed.get("keywords") else "🟡 Needs Improvement",
        "formatting_consistency": "🟢 Good" if text.count("\n") > 2 else "🟡 Needs Improvement",
    }
    return summary
