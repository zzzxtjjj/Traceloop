from dataclasses import asdict

import pytest

from core.config import Settings, _float_env, _positive_int_env
from core.errors import (
    ModelAuthenticationError,
    ModelInputLimitError,
    ModelOutputValidationError,
    ModelRateLimitError,
    ModelTimeoutError,
)
from scripts.check_model_api import main
from services.model_readiness import (
    check_model_readiness,
    validate_model_input_budget,
    verify_model_live,
)


class FakeLiveProvider:
    model_name = "fake-live-model"

    def __init__(self, response=None) -> None:
        self.response = response if response is not None else {"ok": True}
        self.calls: list[dict] = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_invalid_budget_environment_values_remain_detectable(monkeypatch) -> None:
    monkeypatch.setenv("TEST_MODEL_TIMEOUT", "not-a-number")
    monkeypatch.setenv("TEST_MODEL_LIMIT", "not-an-integer")

    assert _float_env("TEST_MODEL_TIMEOUT", 30.0) == 0.0
    assert _positive_int_env("TEST_MODEL_LIMIT", 200) == 0


def configured_settings(**overrides) -> Settings:
    values = {
        "model_api_key": "top-secret-key",
        "model_name": "configured-model",
        "model_base_url": "https://user:pass@gateway.example.test/v1?token=secret",
        "model_timeout_seconds": 9.0,
        "model_max_input_chars": 12_000,
        "model_max_reviews_per_run": 25,
        "model_max_attempts": 1,
    }
    values.update(overrides)
    return Settings(**values)


def test_local_readiness_is_safe_and_never_claims_live_verification() -> None:
    readiness = check_model_readiness(configured_settings())

    assert readiness.configured is True
    assert readiness.live_verified is False
    assert readiness.base_url == "https://gateway.example.test/v1"
    assert readiness.max_input_chars == 12_000
    assert readiness.max_reviews_per_run == 25
    assert readiness.max_attempts == 1
    assert "top-secret-key" not in repr(readiness)
    assert "top-secret-key" not in str(asdict(readiness))


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"model_api_key": ""}, "MODEL_API_KEY"),
        ({"model_name": ""}, "MODEL_NAME"),
        ({"model_base_url": "not-a-url"}, "MODEL_BASE_URL"),
        ({"model_base_url": "http://models.example.test/v1"}, "MODEL_BASE_URL"),
        ({"model_base_url": "https://models.example.test:bad/v1"}, "MODEL_BASE_URL"),
        ({"model_timeout_seconds": 0}, "MODEL_TIMEOUT_SECONDS"),
        ({"model_max_input_chars": 0}, "MODEL_MAX_INPUT_CHARS"),
        ({"model_max_reviews_per_run": 0}, "MODEL_MAX_REVIEWS_PER_RUN"),
        ({"model_max_attempts": 3}, "MODEL_MAX_ATTEMPTS"),
    ],
)
def test_readiness_rejects_missing_or_invalid_configuration(
    overrides: dict, expected: str
) -> None:
    readiness = check_model_readiness(configured_settings(**overrides))

    assert readiness.configured is False
    assert expected in " ".join(readiness.missing_fields + readiness.issues)
    assert readiness.live_verified is False


def test_readiness_allows_plain_http_only_for_local_compatible_service() -> None:
    readiness = check_model_readiness(
        configured_settings(model_base_url="http://127.0.0.1:8000/v1")
    )

    assert readiness.configured is True
    assert readiness.base_url == "http://127.0.0.1:8000/v1"


def test_default_cli_only_checks_local_configuration(capsys) -> None:
    provider = FakeLiveProvider(AssertionError("must not make a request"))

    exit_code = main([], config=configured_settings(), provider=provider)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert provider.calls == []
    assert "configured=true" in output
    assert "live_verified=false" in output
    assert "max_attempts=1" in output
    assert "top-secret-key" not in output
    assert "user:pass" not in output
    assert "token=secret" not in output


def test_live_cli_refuses_unconfigured_model_without_request(capsys) -> None:
    provider = FakeLiveProvider(AssertionError("must not make a request"))

    exit_code = main(
        ["--live"],
        config=configured_settings(model_api_key=""),
        provider=provider,
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert provider.calls == []
    assert "configured=false" in output
    assert "live_verified=false" in output


def test_explicit_live_check_makes_exactly_one_minimal_request(capsys) -> None:
    provider = FakeLiveProvider({"ok": True})

    result = verify_model_live(configured_settings(), provider=provider)
    exit_code = main(
        ["--live"], config=configured_settings(), provider=FakeLiveProvider({"ok": True})
    )

    output = capsys.readouterr().out
    assert result.live_verified is True
    assert result.schema_valid is True
    assert len(provider.calls) == 1
    assert exit_code == 0
    assert "structured_schema_valid=true" in output
    assert "live_verified=true" in output
    assert "top-secret-key" not in output
    assert '{"ok"' not in output


def test_live_check_never_repairs_even_when_two_attempts_are_configured() -> None:
    provider = FakeLiveProvider({"ok": "not-a-boolean"})

    with pytest.raises(ModelOutputValidationError):
        verify_model_live(
            configured_settings(model_max_attempts=2), provider=provider
        )

    assert len(provider.calls) == 1


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ModelTimeoutError("secret upstream detail"), "MODEL_TIMEOUT"),
        (ModelAuthenticationError("secret upstream detail"), "MODEL_AUTH_ERROR"),
        (ModelRateLimitError("secret upstream detail"), "MODEL_RATE_LIMIT"),
    ],
)
def test_live_cli_maps_errors_without_leaking_details(error, code, capsys) -> None:
    provider = FakeLiveProvider(error)

    exit_code = main(["--live"], config=configured_settings(), provider=provider)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert len(provider.calls) == 1
    assert code in captured.err
    assert "secret upstream detail" not in captured.err
    assert "top-secret-key" not in captured.err


def test_input_budget_rejects_reviews_and_characters_deterministically() -> None:
    with pytest.raises(ModelInputLimitError, match="评价数量超过上限"):
        validate_model_input_budget(
            prompt="small",
            review_count=3,
            max_input_chars=10,
            max_reviews_per_run=2,
        )
    with pytest.raises(ModelInputLimitError, match="字符上限"):
        validate_model_input_budget(
            prompt="too long",
            review_count=1,
            max_input_chars=3,
            max_reviews_per_run=2,
        )
