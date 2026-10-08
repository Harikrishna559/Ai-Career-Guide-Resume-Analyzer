import pytest

from services.ai.errors import (
    AI_AUTHENTICATION_ERROR,
    AI_INVALID_RESPONSE,
    AI_NOT_CONFIGURED,
    AI_PROVIDER_ERROR,
    AI_RATE_LIMIT,
    AI_UNAVAILABLE,
    AIServiceError,
)
from services.ai.gemini_provider import GeminiProvider
from services.ai.provider import AIProvider
from services.ai.service import AIService, create_ai_service


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.arguments = None

    def generate_content(self, **kwargs):
        self.arguments = kwargs
        if self.error:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, response=None, error=None):
        self.models = FakeModels(response, error)


def test_provider_contract_and_application_service_delegation():
    assert issubclass(GeminiProvider, AIProvider)

    class StubProvider(AIProvider):
        def generate_json(self, prompt, *, response_schema=None):
            return {"prompt": prompt, "schema": response_schema}

        def is_configured(self):
            return True

    schema = {"type": "object"}
    service = AIService(StubProvider())
    assert service.generate_json("prompt", response_schema=schema) == {
        "prompt": "prompt",
        "schema": schema,
    }
    assert service.is_configured() is True


def test_gemini_provider_reports_missing_key_without_client():
    provider = GeminiProvider(api_key="", client=None)
    assert provider.is_configured() is False
    with pytest.raises(AIServiceError) as error:
        provider.generate_json("prompt")
    assert error.value.code == AI_NOT_CONFIGURED
    assert "GEMINI_API_KEY" not in str(error.value)


def test_gemini_provider_uses_current_model_and_parses_json():
    client = FakeClient(FakeResponse('{"result": "ok"}'))
    provider = GeminiProvider(api_key="configured", client=client)

    assert provider.generate_json("test prompt") == {"result": "ok"}
    assert client.models.arguments == {
        "model": GeminiProvider.MODEL_NAME,
        "contents": "test prompt",
    }


def test_gemini_provider_passes_optional_response_schema():
    client = FakeClient(FakeResponse('{"result": "ok"}'))
    schema = {"type": "object", "properties": {"result": {"type": "string"}}}
    provider = GeminiProvider(api_key="configured", client=client)

    provider.generate_json("test prompt", response_schema=schema)

    assert client.models.arguments["config"] == {
        "response_mime_type": "application/json",
        "response_schema": schema,
    }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"value": 1}', {"value": 1}),
        ('```json\n{"value": 2}\n```', {"value": 2}),
        ('```json\n[{"value": 3}]\n```', [{"value": 3}]),
    ],
)
def test_gemini_provider_parses_json_formats(text, expected):
    provider = GeminiProvider(api_key="configured", client=FakeClient(FakeResponse(text)))
    assert provider.generate_json("prompt") == expected


def test_gemini_provider_rejects_malformed_json():
    provider = GeminiProvider(api_key="configured", client=FakeClient(FakeResponse("not json")))
    with pytest.raises(AIServiceError) as error:
        provider.generate_json("prompt")
    assert error.value.code == AI_INVALID_RESPONSE
    assert "not json" not in str(error.value)


@pytest.mark.parametrize(
    ("provider_message", "expected_code"),
    [
        ("invalid API key", AI_AUTHENTICATION_ERROR),
        ("429 rate limit", AI_RATE_LIMIT),
        ("network connection timeout", AI_UNAVAILABLE),
        ("unexpected provider failure", AI_PROVIDER_ERROR),
    ],
)
def test_gemini_provider_maps_errors_without_exposing_provider_details(provider_message, expected_code):
    provider = GeminiProvider(
        api_key="configured",
        client=FakeClient(error=RuntimeError(provider_message)),
    )
    with pytest.raises(AIServiceError) as error:
        provider.generate_json("sensitive prompt")
    assert error.value.code == expected_code
    assert provider_message not in str(error.value)


def test_ai_service_selects_gemini_by_default(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    service = create_ai_service()
    assert isinstance(service.provider, GeminiProvider)


def test_ai_service_selects_configured_gemini(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    service = create_ai_service()
    assert isinstance(service.provider, GeminiProvider)


def test_ai_service_rejects_unsupported_provider():
    with pytest.raises(AIServiceError) as error:
        create_ai_service("unsupported")
    assert error.value.code == AI_PROVIDER_ERROR
    assert "unsupported" in str(error.value)


def test_ai_service_validates_career_plan_shape():
    class InvalidProvider(AIProvider):
        def generate_json(self, prompt, *, response_schema=None):
            return {"career_summary": "summary"}

        def is_configured(self):
            return True

    with pytest.raises(AIServiceError) as error:
        AIService(InvalidProvider()).generate_career_plan({})
    assert error.value.code == AI_INVALID_RESPONSE
