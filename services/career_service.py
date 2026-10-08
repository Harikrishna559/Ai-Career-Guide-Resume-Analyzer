import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


def _load_json(filename):
    with open(DATA_DIR / filename, "r", encoding="utf-8") as file:
        return json.load(file)


def build_role_library():
    roles = _load_json("roles.json")
    if isinstance(roles, list):
        return roles
    if isinstance(roles, dict):
        normalized = []
        for role_name, role_data in roles.items():
            if not isinstance(role_data, dict):
                normalized.append({"role": role_name, "description": f"Career path for {role_name}.", "keywords": [], "skills": {"beginner": [], "intermediate": [], "advanced": []}})
                continue
            record = {"role": role_name}
            record.update(role_data)
            normalized.append(record)
        return normalized
    return []


def get_role_profile(target_role):
    roles = build_role_library()
    for role in roles:
        if str(role.get("role", "")).lower() == str(target_role).lower():
            return role
    return {
        "role": target_role,
        "description": f"Career path for {target_role}.",
        "skills": {"beginner": ["Fundamentals"], "intermediate": ["Practice"], "advanced": ["Portfolio projects"]},
    }


def generate_roadmap_from_profile(profile):
    role = get_role_profile(profile.get("target_role", "Software Developer"))
    skill_profile = role.get("skills", {})
    current_skills = [skill.strip() for skill in str(profile.get("current_skills", "")).split(",") if skill.strip()]
    hours = int(profile.get("hours_per_day", 2))
    roadmap = []
    days = [
        (1, "Core foundation", "Build the core concepts for the target role", "1 hour", "Beginner", "Official documentation"),
        (2, "Hands-on practice", "Apply concepts with mini exercises", "1 hour", "Beginner", "YouTube tutorial"),
        (3, "Project setup", "Create a small project using the role's primary stack", "2 hours", "Intermediate", "GitHub project"),
        (4, "Debugging and problem solving", "Practice debugging and code review", "1.5 hours", "Intermediate", "LeetCode"),
        (5, "Role-specific workflow", "Understand daily tasks and workflows of the role", "2 hours", "Intermediate", "Official docs"),
    ]
    for day, topic, learning, time_cost, difficulty, resource in days:
        roadmap.append({
            "day": day,
            "topic": topic,
            "learning": learning,
            "practical_task": f"Complete a focused assignment related to {role.get('role', 'the role')} and review your notes.",
            "time": time_cost,
            "difficulty": difficulty,
            "resource": resource,
            "project_task": "Build a small output that you can showcase in your portfolio.",
        })

    return {
        "career_summary": f"{profile.get('name', 'Candidate')} is targeting {role.get('role', 'the target role')} with {profile.get('experience_level', 'entry-level')} experience. The plan is aligned to a {hours}-hour learning schedule and focuses on the most important gaps in the current skill set.",
        "readiness_score": 68,
        "current_skills": current_skills or ["Foundational technical knowledge"],
        "skill_gaps": [
            "Role-specific tools and workflow",
            "Project execution and debugging",
            "Interview preparation and portfolio proof",
        ],
        "roadmap": roadmap,
        "resources": [
            {"type": "📚 Learn", "title": "Official documentation", "url": "https://docs.python.org/3/", "description": "Core language and framework learning"},
            {"type": "🎥 Video", "title": "FreeCodeCamp", "url": "https://www.freecodecamp.org/", "description": "Structured video lessons and exercises"},
            {"type": "💻 Practice", "title": "LeetCode", "url": "https://leetcode.com/", "description": "Coding and interview practice"},
        ],
        "projects": [
            {"name": "Portfolio project", "difficulty": "Intermediate", "technologies": role.get("role", "Relevant stack"), "description": "Build a role-aligned project that demonstrates your understanding of real-world workflows.", "skills_developed": current_skills or ["Applied learning"], "duration": "2-3 weeks"},
        ],
        "interview_topics": [
            "Core concepts for the target role",
            "Problem solving and debugging",
            "Behavioral and HR questions",
        ],
        "next_steps": [
            "Review your skill gaps weekly",
            "Keep a weekly project log",
            "Practice with mock interviews",
        ],
    }
