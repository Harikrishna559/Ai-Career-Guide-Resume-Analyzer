import json
import os
from typing import Any, Optional

from services.ai.errors import AI_INVALID_RESPONSE, AI_PROVIDER_ERROR, AIServiceError
from services.ai.gemini_provider import GeminiProvider
from services.ai.provider import AIProvider


class AIService:
    def __init__(self, provider: AIProvider):
        self.provider = provider

    def generate_json(self, prompt: str, *, response_schema: Any = None):
        return self.provider.generate_json(prompt, response_schema=response_schema)

    def is_configured(self):
        return self.provider.is_configured()

    def generate_career_plan(self, profile):
        prompt = (
            "Generate a structured JSON object for a personalized career roadmap. "
            "Use the input details from the user. Return only valid JSON with keys: "
            "career_summary, readiness_score, current_skills, skill_gaps, roadmap, resources, projects, interview_topics, next_steps. "
            "The roadmap should be a list of objects with day, topic, learning, practical_task, time, difficulty, resource, project_task. "
            "Fields must be relevant to the target role and current skills. "
            f"Profile: {json.dumps(profile, ensure_ascii=False)}"
        )
        data = self.generate_json(prompt)
        required_keys = {
            "career_summary", "readiness_score", "current_skills", "skill_gaps",
            "roadmap", "resources", "projects", "interview_topics", "next_steps",
        }
        if not isinstance(data, dict) or not required_keys.issubset(data):
            raise AIServiceError(AI_INVALID_RESPONSE, "AI service returned an unexpected response. Please try again.")
        return data

    def analyze_resume(self, target_role, resume_text):
        prompt = (
            "Analyze the resume and return valid JSON with keys: "
            "ats_score, score_breakdown, resume_strengths, missing_skills, missing_keywords, strong_keywords, priority_keywords, "
            "professional_summary, certifications, projects_to_add, sections_to_improve, job_portals, recommended_searches, resume_health. "
            "The analysis should compare the resume to a target role and remain truthful by only suggesting skills and experiences that are actually supported by the resume text. "
            f"Target Role: {target_role}. Resume text: {resume_text[:8000]}"
        )
        data = self.generate_json(prompt)
        if not isinstance(data, dict):
            raise AIServiceError(AI_INVALID_RESPONSE, "AI service returned an unexpected response. Please try again.")
        return data

    def generate_summary(self, resume_text, target_role, parsed_details=None):
        prompt = (
            "Generate a concise ATS-friendly professional summary for a resume. "
            "Do not invent experience, metrics, or technologies. Use only the provided details. "
            "Return only valid JSON with a single key: summary. "
            f"Target Role: {target_role}. Resume: {resume_text[:8000]}. Parsed details: {json.dumps(parsed_details or {}, ensure_ascii=False)}"
        )
        data = self.generate_json(prompt)
        if not isinstance(data, dict):
            raise AIServiceError(AI_INVALID_RESPONSE, "AI service returned an unexpected response. Please try again.")
        if "summary" in data:
            return data["summary"]
        return str(data)


def create_ai_service(provider_name: Optional[str] = None, provider: Optional[AIProvider] = None) -> AIService:
    selected = (provider_name or os.getenv("AI_PROVIDER") or "gemini").strip().lower()
    if selected != "gemini":
        raise AIServiceError(
            AI_PROVIDER_ERROR,
            f"Unsupported AI provider '{selected}'. Configure AI_PROVIDER=gemini.",
        )
    return AIService(provider or GeminiProvider())
