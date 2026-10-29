import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ValidationError

from core.config import Settings, settings
from core.errors import (
    ModelInputLimitError,
    ModelNotConfiguredError,
    ModelOutputValidationError,
)
from services.model_provider import OpenAICompatibleProvider


@dataclass(frozen=True)
class ModelReadiness:
    configured: bool
    live_verified: bool
    model_name: str
    base_url: str
    timeout_seconds: float
    max_input_chars: int
    max_reviews_per_run: int
    max_attempts: int
    missing_fields: tuple[str, ...]
    issues: tuple[str, ...]


@dataclass(frozen=True)
class ModelLiveVerification:
    configured: bool
    live_verified: bool
    model_name: str
    latency_ms: int
    schema_valid: bool


class _LiveCheckOutput(BaseModel):
    ok: bool


def _safe_base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return ""
    try:
        port_value = parsed.port
    except ValueError:
        return ""
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    port = f":{port_value}" if port_value else ""
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{host}{port}{path}"


def check_model_readiness(config: Settings = settings) -> ModelReadiness:
    missing = []
    if not config.model_api_key.strip():
        missing.append("MODEL_API_KEY")
    if not config.model_name.strip():
        missing.append("MODEL_NAME")
    if not config.model_base_url.strip():
        missing.append("MODEL_BASE_URL")

    issues = []
    safe_base_url = _safe_base_url(config.model_base_url)
    if config.model_base_url.strip() and not safe_base_url:
        issues.append("MODEL_BASE_URL must be an absolute HTTP(S) URL")
    if config.model_timeout_seconds <= 0:
        issues.append("MODEL_TIMEOUT_SECONDS must be positive")
    if config.model_max_input_chars <= 0:
        issues.append("MODEL_MAX_INPUT_CHARS must be positive")
    if config.model_max_reviews_per_run <= 0:
        issues.append("MODEL_MAX_REVIEWS_PER_RUN must be positive")
    if config.model_max_attempts not in {1, 2}:
        issues.append("MODEL_MAX_ATTEMPTS must be 1 or 2")

    return ModelReadiness(
        configured=not missing and not issues,
        live_verified=False,
        model_name=config.model_name.strip(),
        base_url=safe_base_url,
        timeout_seconds=config.model_timeout_seconds,
        max_input_chars=config.model_max_input_chars,
        max_reviews_per_run=config.model_max_reviews_per_run,
        max_attempts=config.model_max_attempts,
        missing_fields=tuple(missing),
        issues=tuple(issues),
    )


def validate_model_input_budget(
    *,
    prompt: str,
    review_count: int,
    max_input_chars: int | None = None,
    max_reviews_per_run: int | None = None,
) -> None:
    char_limit = max_input_chars or settings.model_max_input_chars
    review_limit = max_reviews_per_run or settings.model_max_reviews_per_run
    if review_count > review_limit:
        raise ModelInputLimitError(
            f"本次评价数量超过上限（{review_count}/{review_limit}），请拆分批次。"
        )
    if len(prompt) > char_limit:
        raise ModelInputLimitError(
            f"本次模型输入超过字符上限（{len(prompt)}/{char_limit}），请缩小批次。"
        )


def verify_model_live(
    config: Settings = settings,
    *,
    provider: OpenAICompatibleProvider | None = None,
) -> ModelLiveVerification:
    readiness = check_model_readiness(config)
    if not readiness.configured:
        raise ModelNotConfiguredError("模型本地配置不完整或无效，不能执行在线验证。")

    active_provider = provider or OpenAICompatibleProvider.from_settings(config)
    started = time.perf_counter()
    raw: dict[str, Any] | str = active_provider.generate(
        prompt='Return {"ok": true}. Do not include any other content.',
        schema=_LiveCheckOutput.model_json_schema(),
    )
    try:
        parsed = (
            _LiveCheckOutput.model_validate_json(raw)
            if isinstance(raw, str)
            else _LiveCheckOutput.model_validate(raw)
        )
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        raise ModelOutputValidationError("模型在线验证未返回合法结构。") from exc
    if parsed.ok is not True:
        raise ModelOutputValidationError("模型在线验证结构有效但检查结果未通过。")
    return ModelLiveVerification(
        configured=True,
        live_verified=True,
        model_name=active_provider.model_name,
        latency_ms=int((time.perf_counter() - started) * 1000),
        schema_valid=True,
    )
