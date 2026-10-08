"""Compatibility wrapper for callers of the former GeminiService."""

from services.ai import AIServiceError, create_ai_service

GeminiAPIError = AIServiceError


class GeminiService:
    """Delegate legacy service calls to the provider-independent AI service."""

    def __init__(self, ai_service=None):
        self._ai_service = ai_service or create_ai_service()

    def is_configured(self):
        return self._ai_service.is_configured()

    def generate_career_plan(self, profile):
        return self._ai_service.generate_career_plan(profile)

    def analyze_resume(self, target_role, resume_text):
        return self._ai_service.analyze_resume(target_role, resume_text)

    def generate_summary(self, resume_text, target_role, parsed_details=None):
        return self._ai_service.generate_summary(resume_text, target_role, parsed_details)
