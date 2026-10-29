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
) -> OutputT:
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

        invalid_payload: str | None = None
        for attempt in range(2):
            try:
                raw = provider.generate(
                    prompt=prompt,
                    schema=output_model.model_json_schema(),
                    repair_from=invalid_payload,
                )
            except TimeoutError as exc:
                run.status = "failed"
                run.error_code = ModelTimeoutError.code
                run.latency_ms = int((time.perf_counter() - started) * 1000)
                db.flush()
                raise ModelTimeoutError("模型调用超时，请稍后重试。") from exc
            except TradeLoopError as exc:
                run.status = "failed"
                run.error_code = exc.code
                run.latency_ms = int((time.perf_counter() - started) * 1000)
                db.flush()
                raise

            try:
                parsed = (
                    output_model.model_validate_json(raw)
                    if isinstance(raw, str)
                    else output_model.model_validate(raw)
                )
                run.status = "success"
                run.error_code = None
                run.latency_ms = int((time.perf_counter() - started) * 1000)
                db.flush()
                return parsed
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                invalid_payload = str(raw)
                if attempt == 1:
                    run.status = "failed"
                    run.error_code = "MODEL_BAD_JSON"
                    run.latency_ms = int((time.perf_counter() - started) * 1000)
                    db.flush()
                    raise ModelOutputValidationError(
                        "模型返回格式不合法，已停止写入关键业务状态。"
                    ) from exc

    raise ModelOutputValidationError("模型调用未返回有效结果。")

