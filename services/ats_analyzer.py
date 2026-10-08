import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


def _load_data(filename):
    with open(DATA_DIR / filename, "r", encoding="utf-8") as file:
        return json.load(file)


def _unique_preserve_order(items):
    seen = set()
    output = []
    for item in items:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
    return output


def _coerce_role_data(role_map):
    if isinstance(role_map, dict):
        normalized = {}
        for role_name, value in role_map.items():
            if isinstance(value, dict):
                normalized[str(role_name).lower()] = value
            else:
                normalized[str(role_name).lower()] = {"keywords": []}
        return normalized
    if isinstance(role_map, list):
        normalized = {}
        for entry in role_map:
            if isinstance(entry, dict):
                role_name = str(entry.get("role", "")).strip()
                if role_name:
                    normalized[role_name.lower()] = entry
        return normalized
    return {}


def get_role_keywords(target_role):
    roles = _load_data("roles.json")
    role_data = _coerce_role_data(roles)
    target = str(target_role or "").strip().lower()
    if target:
        if target in role_data:
            entry = role_data[target]
            keywords = []
            for key in ["keywords", "core_skills", "technologies"]:
                value = entry.get(key, [])
                if isinstance(value, list):
                    keywords.extend(value)
                elif isinstance(value, str):
                    keywords.append(value)
            if isinstance(entry.get("skills"), dict):
                for group in entry["skills"].values():
                    if isinstance(group, list):
                        keywords.extend(group)
            keywords = _unique_preserve_order(keywords)
            if keywords:
                return keywords
    return [
        "python", "java", "sql", "rest", "api", "problem solving", "git", "docker", "testing"
    ]


def _normalize_list(values):
    return [value.strip() for value in values if isinstance(value, str) and value.strip()]


def job_search_recommendations(target_role):
    query_templates = [
        f"{target_role} Fresher",
        f"Junior {target_role}",
        f"{target_role} Intern",
        f"{target_role} Entry Level",
        f"{target_role} Fresher Remote",
    ]
    return query_templates


def generate_summary_versions(resume_text, target_role, parsed_details=None):
    parsed_details = parsed_details or {}
    skills = _normalize_list(parsed_details.get("skills", [])) or ["problem solving", "communication", "teamwork"]
    experience = _normalize_list(parsed_details.get("experience", [])) or ["relevant project work"]
    projects = _normalize_list(parsed_details.get("projects", []))
    certifications = _normalize_list(parsed_details.get("certifications", []))
    skill_text = ", ".join(skills[:4])
    project_text = projects[0] if projects else "hands-on project work"
    certification_text = certifications[0] if certifications else "technical learning"
    experience_text = experience[0] if experience else "relevant work and project experience"

    ats_friendly = (
        f"Results-driven {target_role} candidate with a strong foundation in {skill_text}. "
        f"Experienced in building practical solutions, collaborating across teams, and contributing to {project_text}. "
        f"Focused on delivering reliable, role-relevant work and continuous learning in areas aligned to the target opportunity."
    )
    professional = (
        f"Motivated {target_role} professional with hands-on exposure in {skill_text} and experience in {experience_text}. "
        f"Brings a practical understanding of project execution, problem solving, and collaboration, with an interest in contributing to impactful work and continuing to strengthen technical depth."
    )
    fresher_friendly = (
        f"Motivated fresher aiming to grow as a {target_role} with foundational knowledge in {skill_text}. "
        f"Strong interest in learning, building projects, and improving skills through hands-on practice. "
        f"Prepared to contribute with curiosity, adaptability, and a willingness to learn from real-world work and {certification_text}."
    )

    return {
        "ats_friendly": ats_friendly,
        "professional": professional,
        "fresher_friendly": fresher_friendly,
    }


def analyze_resume_text(raw_text, target_role, parsed_details=None):
    parsed_details = parsed_details or {}
    role_keywords = get_role_keywords(target_role)
    text_lower = (raw_text or "").lower()
    existing_skills = [str(skill).lower() for skill in parsed_details.get("skills", []) if skill]
    missing_skills = [skill for skill in role_keywords if str(skill).lower() not in text_lower][:6]
    strong_keywords = [skill for skill in parsed_details.get("skills", []) if skill]
    missing_keywords = [keyword for keyword in role_keywords if keyword.lower() not in text_lower][:6]
    priority_keywords = [keyword for keyword in role_keywords[:6] if keyword.lower() not in text_lower]

    score_breakdown = {
        "Keyword Match": min(95, max(35, 82 - len(missing_keywords) * 4)),
        "Skills Match": min(95, max(30, 76 - len(missing_skills) * 5)),
        "Job Role Relevance": min(95, max(40, 72 - len(missing_keywords) * 3)),
        "Resume Structure": 80,
        "Experience Relevance": 70,
        "Projects": 85,
        "Certifications": 60,
        "Education": 75,
        "Formatting": 80,
    }
    ats_score = int(round(sum(score_breakdown.values()) / len(score_breakdown)))

    resume_strengths = []
    if existing_skills:
        resume_strengths.append("Relevant technical keywords detected in the resume.")
    if parsed_details.get("projects"):
        resume_strengths.append("Project experience is mentioned and can be showcased more clearly.")
    if parsed_details.get("education"):
        resume_strengths.append("Educational background is present and supports the target role.")
    if not resume_strengths:
        resume_strengths.append("The resume includes basic career details but would benefit from stronger keyword alignment.")

    sections_to_improve = [
        "Professional Summary",
        "Technical Skills",
        "Projects",
        "Experience",
        "Certifications",
    ]

    projects_to_add = [
        "Role-specific portfolio project",
        "API integration project",
        "Problem-solving coding challenge tracker",
        "Deployment and testing project",
    ]

    certifications = [
        "Google Cloud Associate Certificate",
        "AWS Cloud Practitioner",
        "Java or Python certification",
        "SQL and data analytics certificate",
    ]

    job_portals = _load_data("job_portals.json")

    return {
        "ats_score": ats_score,
        "score_breakdown": {str(key): int(round(value)) for key, value in score_breakdown.items()},
        "resume_strengths": resume_strengths,
        "missing_skills": missing_skills[:5],
        "missing_keywords": missing_keywords[:5],
        "strong_keywords": strong_keywords[:8],
        "priority_keywords": priority_keywords[:5],
        "certifications": certifications[:3],
        "projects_to_add": projects_to_add[:3],
        "sections_to_improve": sections_to_improve,
        "job_portals": job_portals[:5],
    }


def generate_professional_summary(resume_text, target_role, parsed_details=None):
    versions = generate_summary_versions(resume_text, target_role, parsed_details)
    return versions.get("professional", "")


def analyze_job_description(job_description, target_role, resume_details=None):
    resume_details = resume_details or {}
    role_keywords = get_role_keywords(target_role)
    jd_lower = (job_description or "").lower()
    resume_text = " ".join(str(item) for item in resume_details.get("skills", []) or [])
    resume_lower = resume_text.lower()

    matched_skills = [skill for skill in role_keywords if skill.lower() in jd_lower and skill.lower() in resume_lower]
    missing_skills = [skill for skill in role_keywords if skill.lower() not in resume_lower][:5]
    missing_keywords = [skill for skill in role_keywords if skill.lower() not in jd_lower][:5]
    match_score = max(0, min(100, 100 - (len(missing_skills) * 12) + (len(matched_skills) * 6)))

    learning_plan = [
        f"Strengthen your skills in {', '.join(missing_skills[:2]) if missing_skills else 'core role fundamentals'}.",
        "Practice a portfolio project aligned to the role's core workflow.",
        "Prepare answers for behavioral and technical interview questions connected to the job description.",
    ]

    resume_improvements = [
        "Highlight role-specific projects and measurable outcomes more clearly.",
        "Add the top missing keywords in your skills and summary sections.",
        "Tighten your resume summary to match the language used in the role description.",
    ]

    interview_topics = [
        "Core skills and tools listed in the description",
        "Problem solving and debugging scenarios",
        "Project walkthrough and business impact",
    ]

    return {
        "target_role": target_role,
        "match_score": int(match_score),
        "matched_skills": matched_skills[:5],
        "missing_skills": missing_skills[:5],
        "missing_keywords": missing_keywords[:5],
        "learning_plan": learning_plan,
        "resume_improvements": resume_improvements,
        "interview_topics": interview_topics,
        "job_summary": f"This role emphasizes {', '.join(role_keywords[:5])} and expects strong project-based understanding and practical execution.",
    }
