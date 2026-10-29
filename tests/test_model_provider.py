import json

import pytest

from core.config import Settings
from core.errors import (
    ModelAuthenticationError,
    ModelNotConfiguredError,
    ModelProviderError,
    ModelRateLimitError,
    ModelResponseError,
    ModelTimeoutError,
)
from services.model_provider import HttpResponse, OpenAICompatibleProvider


class RecordingTransport:
    def __init__(self, response: HttpResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict] = []

    def post(self, **kwargs) -> HttpResponse:
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def response_with_content(content: str | dict) -> HttpResponse:
    body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
    return HttpResponse(200, body)


def make_provider(transport: RecordingTransport, **overrides) -> OpenAICompatibleProvider:
    values = {
        "api_key": "secret-key",
        "model_name": "test-model",
        "base_url": "https://models.example.test/v1",
        "timeout_seconds": 12.5,
        "transport": transport,
    }
    values.update(overrides)
    return OpenAICompatibleProvider(**values)


def test_provider_builds_openai_compatible_json_schema_request() -> None:
    transport = RecordingTransport(response_with_content('{"result_type":"ok"}'))
    provider = make_provider(transport)
    schema = {"type": "object", "properties": {"result_type": {"type": "string"}}}

    result = provider.generate(prompt="Analyze review R-1.", schema=schema)

    assert result == '{"result_type":"ok"}'
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["url"] == "https://models.example.test/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer secret-key"
    assert call["timeout"] == 12.5
    assert call["payload"]["model"] == "test-model"
    assert call["payload"]["response_format"]["json_schema"]["schema"] == schema
    assert call["payload"]["messages"][1]["content"] == "Analyze review R-1."


def test_provider_uses_values_from_settings() -> None:
    transport = RecordingTransport(response_with_content({"result_type": "ok"}))
    config = Settings(
        model_api_key="configured-key",
        model_name="configured-model",
        model_base_url="https://gateway.example.test/openai/v1",
        model_timeout_seconds=7.0,
    )

    provider = OpenAICompatibleProvider.from_settings(config, transport=transport)
    provider.generate(prompt="test", schema={"type": "object"})

    assert provider.model_name == "configured-model"
    assert transport.calls[0]["url"].endswith("/openai/v1/chat/completions")
    assert transport.calls[0]["timeout"] == 7.0


def test_provider_requires_configuration_without_making_request() -> None:
    transport = RecordingTransport(response_with_content({"result_type": "ok"}))
    provider = make_provider(transport, api_key="")

    with pytest.raises(ModelNotConfiguredError, match="尚未配置"):
        provider.generate(prompt="sensitive prompt", schema={"type": "object"})
    assert transport.calls == []


@pytest.mark.parametrize(
    ("status_code", "error_type", "error_code"),
    [
        (401, ModelAuthenticationError, "MODEL_AUTH_ERROR"),
        (403, ModelAuthenticationError, "MODEL_AUTH_ERROR"),
        (429, ModelRateLimitError, "MODEL_RATE_LIMIT"),
        (500, ModelProviderError, "MODEL_PROVIDER_ERROR"),
        (503, ModelProviderError, "MODEL_PROVIDER_ERROR"),
    ],
)
def test_provider_maps_http_errors_without_leaking_response(
    status_code: int, error_type: type[Exception], error_code: str
) -> None:
    transport = RecordingTransport(
        HttpResponse(status_code, b'{"error":"secret upstream detail"}')
    )
    provider = make_provider(transport)

    with pytest.raises(error_type) as captured:
        provider.generate(prompt="private customer text", schema={"type": "object"})
    assert captured.value.code == error_code
    assert "secret-key" not in str(captured.value)
    assert "private customer text" not in str(captured.value)
    assert "secret upstream detail" not in str(captured.value)
    assert len(transport.calls) == 1


def test_provider_converts_transport_timeout() -> None:
    transport = RecordingTransport(TimeoutError("socket timed out"))
    provider = make_provider(transport)

    with pytest.raises(ModelTimeoutError):
        provider.generate(prompt="test", schema={"type": "object"})
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b'{"choices":[]}',
        b'{"choices":[{"message":{"content":""}}]}',
    ],
)
def test_provider_rejects_bad_success_response(body: bytes) -> None:
    provider = make_provider(RecordingTransport(HttpResponse(200, body)))

    with pytest.raises(ModelResponseError):
        provider.generate(prompt="test", schema={"type": "object"})


def test_repair_request_is_explicit_and_still_one_http_call() -> None:
    transport = RecordingTransport(response_with_content({"result_type": "fixed"}))
    provider = make_provider(transport)

    result = provider.generate(
        prompt="test",
        schema={"type": "object"},
        repair_from="invalid response",
    )

    assert result == {"result_type": "fixed"}
    assert len(transport.calls) == 1
    assert "failed schema validation" in transport.calls[0]["payload"]["messages"][2][
        "content"
    ]
