from services.profile_contracts import validate_job_description_profile
from services.jd_parser import parse_job_description


SYNTHETIC_JD = """Software Engineer

Company: Example Technologies

Location: Hyderabad
Work Mode: Hybrid
Employment Type: Full-time

Requirements:
- Bachelor's degree in Computer Science
- 2-4 years experience
- Python
- Java
- SQL

Preferred:
- React
- AWS
- Go

Responsibilities:
- Build backend services
- Develop APIs
- Work with engineering teams

Salary:
₹6-10 LPA

Communication and teamwork are important.
Skills: Python, Go
"""


def test_extracts_header_title_company_location_and_work_details():
    profile = parse_job_description(SYNTHETIC_JD)

    assert profile["job_title"] == "Software Engineer"
    assert profile["company"] == "Example Technologies"
    assert profile["location"] == "Hyderabad"
    assert profile["work_mode"] == "hybrid"
    assert profile["employment_type"] == "full-time"
    assert profile["extraction"]["field_sources"]["job_title"] == "jd_header"


def test_work_mode_and_employment_type_variants_are_normalized():
    remote = parse_job_description(
        "Python Developer\nWork Mode: Work from home\nEmployment Type: Internship"
    )
    onsite = parse_job_description(
        "Data Analyst\nWork Mode: On-site\nEmployment Type: Part time"
    )

    assert remote["work_mode"] == "remote"
    assert remote["employment_type"] == "internship"
    assert onsite["work_mode"] == "onsite"
    assert onsite["employment_type"] == "part-time"


def test_salary_range_is_converted_to_annual_inr():
    compensation = parse_job_description(SYNTHETIC_JD)["compensation"]
    assert compensation == {
        "minimum": 600000,
        "maximum": 1000000,
        "currency": "INR",
        "period": "year",
    }


def test_salary_single_amount_and_monthly_currency_are_preserved():
    lpa = parse_job_description("Python Developer\nSalary: 6 LPA")["compensation"]
    monthly = parse_job_description("Salary: ₹50,000 per month")["compensation"]
    usd = parse_job_description("Salary: $100,000 per year")["compensation"]

    assert lpa == {"minimum": 600000, "maximum": None, "currency": "INR", "period": "year"}
    assert monthly == {"minimum": 50000, "maximum": None, "currency": "INR", "period": "month"}
    assert usd == {"minimum": 100000, "maximum": None, "currency": "USD", "period": "year"}


def test_required_and_preferred_skills_need_explicit_section_evidence():
    profile = parse_job_description(SYNTHETIC_JD)
    unclassified = parse_job_description("Skills: Python, Go")

    assert profile["required_skills"] == ["Python", "Java", "SQL"]
    assert profile["preferred_skills"] == ["React", "AWS"]
    assert "Go" not in profile["required_skills"]
    assert "Go" not in profile["preferred_skills"]
    assert "Go" in unclassified["keywords"]
    assert "Go" not in unclassified["required_skills"]
    assert "Go" not in unclassified["preferred_skills"]


def test_skill_aliases_and_java_javascript_boundaries():
    aliased = parse_job_description(
        "Required Skills:\n- JS\n- ReactJS\n- Postgres\n- ML"
    )
    javascript = parse_job_description("Requirements:\n- JavaScript")

    assert aliased["required_skills"] == ["JavaScript", "React", "PostgreSQL", "Machine Learning"]
    assert "Java" not in javascript["required_skills"]
    assert "JavaScript" in javascript["required_skills"]


def test_responsibilities_are_extracted_without_rewriting():
    profile = parse_job_description(
        "What You'll Do:\n- Build backend services.\n- Develop APIs for customers."
    )
    assert profile["responsibilities"] == [
        "Build backend services.",
        "Develop APIs for customers.",
    ]


def test_experience_range_plus_and_explicit_levels():
    ranged = parse_job_description("Requirements:\n2-4 years of experience")
    plus = parse_job_description("At least 3+ years experience. Senior role.")
    entry = parse_job_description("Fresh graduate candidates are welcome.")

    assert ranged["experience"]["minimum_years"] == 2
    assert ranged["experience"]["maximum_years"] == 4
    assert plus["experience"]["minimum_years"] == 3
    assert plus["experience"]["maximum_years"] is None
    assert plus["experience"]["level"] == "senior"
    assert entry["experience"]["level"] == "entry"


def test_explicit_education_and_certification_requirements():
    profile = parse_job_description(
        "Requirements:\nBachelor's degree in Computer Science\n"
        "Certifications:\nAWS Certified Solutions Architect"
    )
    assert profile["education"] == ["Bachelor's degree in Computer Science"]
    assert profile["certifications"] == ["AWS Certified Solutions Architect"]


def test_soft_skills_and_keywords_are_deterministic():
    profile = parse_job_description(
        "Requirements:\nPython required\n"
        "The candidate should demonstrate communication, leadership, and teamwork."
    )
    assert profile["soft_skills"] == ["communication", "leadership", "teamwork"]
    assert {"Python", "communication", "leadership", "teamwork"} <= set(profile["keywords"])


def test_missing_fields_remain_null_or_empty_and_profile_validates():
    profile = parse_job_description("")

    assert profile["job_title"] is None
    assert profile["company"] is None
    assert profile["location"] is None
    assert profile["work_mode"] is None
    assert profile["employment_type"] is None
    assert profile["compensation"]["minimum"] is None
    assert profile["required_skills"] == []
    assert profile["preferred_skills"] == []
    assert profile["responsibilities"] == []
    assert profile["education"] == []
    assert validate_job_description_profile(profile) == profile


def test_company_can_be_extracted_from_clear_hiring_header():
    profile = parse_job_description("Example Technologies is hiring a Software Engineer.")
    assert profile["company"] == "Example Technologies"
