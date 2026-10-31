import pytest

from core.config import Settings
from services.app_preferences import build_session_config


def test_session_provider_does_not_reuse_local_secret():
    base = Settings(model_api_key="local-secret")
    with pytest.raises(ValueError):
        build_session_config(base, {"base_url": "https://models.example", "model": "other"})
    updated = build_session_config(base, {
        "base_url": "https://models.example/v1", "model": "other", "api_key": "session-key",
    })
    assert updated.model_api_key == "session-key"
    assert base.model_api_key == "local-secret"
    assert updated.model_json_object


@pytest.mark.parametrize("url", ["http://models.example", "https://key@models.example",
                                  "https://models.example?key=private"])
def test_rejects_unsafe_service_addresses(url):
    with pytest.raises(ValueError):
        build_session_config(Settings(), {"base_url": url, "model": "a", "api_key": "b"})
