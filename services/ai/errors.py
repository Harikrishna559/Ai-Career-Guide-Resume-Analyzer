from typing import Optional


AI_NOT_CONFIGURED = "AI_NOT_CONFIGURED"
AI_AUTHENTICATION_ERROR = "AI_AUTHENTICATION_ERROR"
AI_RATE_LIMIT = "AI_RATE_LIMIT"
AI_UNAVAILABLE = "AI_UNAVAILABLE"
AI_INVALID_RESPONSE = "AI_INVALID_RESPONSE"
AI_PROVIDER_ERROR = "AI_PROVIDER_ERROR"


class AIServiceError(Exception):
    def __init__(self, code: str, message: str, cause: Optional[BaseException] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.cause = cause
