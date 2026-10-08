from services.profile_contracts import validate_resume_profile
from services.resume_parser import (
    get_resume_health,
    parse_resume_details,
    parse_resume_profile,
)


SYNTHETIC_RESUME = """Alex Morgan
Email: alex.morgan@example.test
Phone: +1 (415) 555-0136
Location: Oakland, CA
https://www.linkedin.com/in/alex-morgan
https://github.com/alexmorgan
https://alexmorgan.dev

SUMMARY
Software developer focused on reliable web applications.

EDUCATION
B.Tech in Computer Science
Example University
Graduated 2024 | CGPA: 8.4/10

EXPERIENCE
Software Engineer
Company: Example Labs
Location: Oakland, CA
Jan 2022 - Dec 2023
- Built a Python service used by 20 teams.
- Reduced processing time by 25%.

INTERNSHIPS
Backend Intern
Company: Sample Systems
Jun 2021 - Aug 2021
- Developed Flask API endpoints.

PROJECTS
Inventory Dashboard - Internal stock tracking
Built a dashboard for tracking inventory.
Technologies: JavaScript, React.js, PostgreSQL
Achievement: Improved lookup time by 30%.

CERTIFICATIONS
- Certified Python Developer
- AWS Cloud Practitioner

ACHIEVEMENTS
- Awarded first place in the university project showcase.

SKILLS
Python, JavaScript, Flask, ReactJS, PostgreSQL, AWS, Docker, Git,
communication, teamwork
"""


def test_parse_resume_details_extracts_keywords():
    text = "Python developer with Flask, SQL, REST API, Docker and Git experience."
    parsed = parse_resume_details(text)
    assert 'python' in parsed['skills']
    assert 'flask' in parsed['skills']
    assert parsed['resume_length'] > 0


def test_resume_health_detects_missing_sections():
    text = "Python developer with SQL, Git and API experience."
    parsed = parse_resume_details(text)
    health = get_resume_health(text, parsed)
    assert 'skills_section' in health
    assert 'contact_information' in health


def test_structured_profile_extracts_contact_header_fields():
    profile = parse_resume_profile(SYNTHETIC_RESUME)
    personal = profile["personal"]

    assert personal["name"] == "Alex Morgan"
    assert personal["email"] == "alex.morgan@example.test"
    assert personal["phone"] == "+1 (415) 555-0136"
    assert personal["location"] == "Oakland, CA"
    assert personal["links"]["linkedin"] == "https://www.linkedin.com/in/alex-morgan"
    assert personal["links"]["github"] == "https://github.com/alexmorgan"
    assert personal["links"]["portfolio"] == "https://alexmorgan.dev"


def test_structured_profile_extracts_summary_education_and_grade():
    profile = parse_resume_profile(SYNTHETIC_RESUME)

    assert profile["summary"] == "Software developer focused on reliable web applications."
    assert profile["education"] == [{
        "degree": "B.Tech",
        "field_of_study": "Computer Science",
        "institution": "Example University",
        "graduation_year": 2024,
        "grade": {"value": 8.4, "scale": "10"},
    }]


def test_structured_profile_extracts_work_and_internship_entries():
    profile = parse_resume_profile(SYNTHETIC_RESUME)

    work, internship = profile["experience"]
    assert work["kind"] == "work"
    assert work["job_title"] == "Software Engineer"
    assert work["organization"] == "Example Labs"
    assert work["location"] == "Oakland, CA"
    assert work["start_date"] == "Jan 2022"
    assert work["end_date"] == "Dec 2023"
    assert work["duration_months"] is None
    assert work["responsibilities"] == ["Built a Python service used by 20 teams."]
    assert work["achievements"] == ["Reduced processing time by 25%."]
    assert internship["kind"] == "internship"
    assert internship["job_title"] == "Backend Intern"


def test_structured_profile_extracts_project_certification_and_achievement():
    profile = parse_resume_profile(SYNTHETIC_RESUME)

    assert profile["projects"] == [{
        "name": "Inventory Dashboard",
        "description": "Built a dashboard for tracking inventory.",
        "technologies": ["JavaScript", "React", "PostgreSQL"],
        "achievements": ["Improved lookup time by 30%."],
    }]
    assert "Certified Python Developer" in profile["certifications"]
    assert "AWS Cloud Practitioner" in profile["certifications"]
    assert profile["achievements"] == ["Awarded first place in the university project showcase."]


def test_structured_skills_use_categories_and_token_boundaries():
    profile = parse_resume_profile(
        "SKILLS\nJavaScript, ReactJS, Postgres, ML, AWS, Docker, communication"
    )
    skills = profile["skills"]

    assert skills["programming_languages"] == ["JavaScript"]
    assert skills["frameworks"] == ["React"]
    assert skills["databases"] == ["PostgreSQL"]
    assert skills["other"] == ["Machine Learning"]
    assert skills["cloud"] == ["AWS"]
    assert skills["tools"] == ["Docker"]
    assert skills["soft_skills"] == ["Communication"]

    java_guard = parse_resume_profile("SKILLS\nJavaScript")
    assert "Java" not in java_guard["skills"]["programming_languages"]
    assert "JavaScript" in java_guard["skills"]["programming_languages"]


def test_structured_profile_missing_fields_stay_null_or_empty():
    profile = parse_resume_profile("")

    assert profile["personal"]["name"] is None
    assert profile["personal"]["email"] is None
    assert profile["personal"]["phone"] is None
    assert profile["personal"]["location"] is None
    assert profile["personal"]["links"]["other"] == []
    assert profile["summary"] is None
    assert profile["education"] == []
    assert profile["experience"] == []
    assert profile["projects"] == []
    assert profile["certifications"] == []


def test_name_heuristic_does_not_promote_a_job_title_to_personal_name():
    profile = parse_resume_profile("Software Engineer\nEXPERIENCE\nBuilt services.")
    assert profile["personal"]["name"] is None


def test_structured_profile_is_contract_valid_and_records_provenance():
    profile = parse_resume_profile(SYNTHETIC_RESUME)
    validated = validate_resume_profile(profile)

    assert validated["schema_version"] == "1.0"
    assert validated["extraction"]["field_sources"]["personal.email"] == "contact_header"
    assert validated["extraction"]["confidence"]["personal.email"] == 0.99


def test_legacy_parser_fields_remain_available_with_additive_profile():
    parsed = parse_resume_details("Python developer with Flask, SQL, REST API, Docker and Git experience.")

    assert {"skills", "education", "projects", "experience", "certifications", "keywords", "resume_length"} <= set(parsed)
    assert "python" in parsed["skills"]
    assert "flask" in parsed["skills"]
    assert parsed["resume_length"] > 0
    assert parsed["resume_profile"]["schema_version"] == "1.0"
