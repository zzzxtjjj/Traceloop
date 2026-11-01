import hashlib
import json
import time
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from core.db import session_context
from core.errors import ModelOutputValidationError, ModelTimeoutError, TradeLoopError
from core.models import AiRun

OutputT = TypeVar("OutputT", bound=BaseModel)


def _extract_json_object(raw: str) -> str:
    """Extract one JSON object without relaxing schema validation."""
    text = raw.strip()
    fence_start = text.find("```")
    if fence_start >= 0:
        fence_end = text.find("```", fence_start + 3)
        if fence_end > fence_start:
            fenced = text[fence_start + 3 : fence_end].lstrip()
            if fenced.lower().startswith("json"):
                fenced = fenced[4:].lstrip()
            text = fenced
    if text.startswith("{") and text.endswith("}"):
        return text
    decoder = json.JSONDecoder()
    start = text.find("{")
    if start >= 0:
        try:
            _, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            return raw
        if not text[start + end :].strip():
            return text[start : start + end]
    return raw


def _validation_detail(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors()[:5]:
        location = ".".join(str(item) for item in error.get("loc", ())) or "<root>"
        parts.append(f"{location}: {error.get('msg', 'invalid value')}")
    return "; ".join(parts)


class StructuredModelProvider(Protocol):
    model_name: str

    def generate(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
        repair_from: str | None = None,
    ) -> dict[str, Any] | str: ...


def _input_hash(prompt: str, evidence_ids: list[int]) -> str:
    payload = json.dumps(
        {"prompt": prompt, "evidence_ids": sorted(evidence_ids)},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_structured_model(
    *,
    project_id: int,
    run_type: str,
    prompt_version: str,
    prompt: str,
    evidence_ids: list[int],
    output_model: type[OutputT],
    provider: StructuredModelProvider,
    session: Session | None = None,
    record_run: bool = True,
) -> OutputT:
    if not record_run:
        return _generate_validated(
            prompt=prompt,
            output_model=output_model,
            provider=provider,
        )

    started = time.perf_counter()
    with session_context(session) as db:
        run = AiRun(
            project_id=project_id,
            run_type=run_type,
            model=provider.model_name,
            prompt_version=prompt_version,
            input_hash=_input_hash(prompt, evidence_ids),
            status="pending",
        )
        db.add(run)
        db.flush()

        try:
            parsed = _generate_validated(
                prompt=prompt,
                output_model=output_model,
                provider=provider,
            )
        except TradeLoopError as exc:
            run.status = "failed"
            run.error_code = exc.code
            run.latency_ms = int((time.perf_counter() - started) * 1000)
            db.flush()
            raise

        run.status = "success"
        run.error_code = None
        run.latency_ms = int((time.perf_counter() - started) * 1000)
        db.flush()
        return parsed


def _generate_validated(
    *,
    prompt: str,
    output_model: type[OutputT],
    provider: StructuredModelProvider,
) -> OutputT:
    invalid_payload: str | None = None
    max_attempts = getattr(provider, "max_attempts", 1)
    if max_attempts not in {1, 2}:
        max_attempts = 1
    for attempt in range(max_attempts):
        try:
            raw = provider.generate(
                prompt=prompt,
                schema=output_model.model_json_schema(),
                repair_from=invalid_payload,
            )
        except TimeoutError as exc:
            raise ModelTimeoutError("模型调用超时，请稍后重试。") from exc

        try:
            if isinstance(raw, str):
                return output_model.model_validate_json(_extract_json_object(raw))
            return output_model.model_validate(raw)
        except ValidationError as exc:
            invalid_payload = str(raw)
            if attempt == max_attempts - 1:
                raise ModelOutputValidationError(
                    "模型返回格式不合法，已停止写入关键业务状态。"
                    f" 字段校验：{_validation_detail(exc)}"
                ) from exc
        except (ValueError, json.JSONDecodeError) as exc:
            invalid_payload = str(raw)
            if attempt == max_attempts - 1:
                raise ModelOutputValidationError(
                    "模型返回不是有效 JSON，已停止写入关键业务状态。"
                ) from exc

    raise ModelOutputValidationError("模型调用未返回有效结果。")

