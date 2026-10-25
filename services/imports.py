import hashlib
import io
import json
import re
from pathlib import Path
from typing import BinaryIO

import pandas as pd
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import settings
from core.db import session_context
from core.models import Artifact, AuditEvent, BusinessObject, SupplierQuote
from core.schemas import QuoteImportPreview, QuoteRow, RowError
from services.evidence_service import create_evidence

QUOTE_COLUMNS = [
    "supplier",
    "unit_price",
    "currency",
    "moq",
    "lead_time_days",
    "payment_terms",
    "quality_note",
]


class QuoteImportValidationError(ValueError):
    def __init__(self, preview: QuoteImportPreview):
        super().__init__("报价 CSV 未通过校验。")
        self.preview = preview


def _read_source(source: str | Path | bytes | BinaryIO) -> tuple[bytes, str]:
    if isinstance(source, bytes):
        return source, "supplier_quotes.csv"
    if isinstance(source, (str, Path)):
        path = Path(source)
        return path.read_bytes(), path.name
    if hasattr(source, "getvalue"):
        filename = getattr(source, "name", "supplier_quotes.csv")
        return source.getvalue(), Path(filename).name
    filename = Path(getattr(source, "name", "supplier_quotes.csv")).name
    return source.read(), filename


def preview_quote_csv(source: str | Path | bytes | BinaryIO) -> QuoteImportPreview:
    raw, filename = _read_source(source)
    digest = hashlib.sha256(raw).hexdigest()
    errors: list[RowError] = []
    rows: list[QuoteRow] = []

    try:
        frame = pd.read_csv(io.BytesIO(raw), dtype={"currency": "string"})
    except Exception as exc:
        return QuoteImportPreview(
            rows=[],
            errors=[RowError(row_number=1, field="file", message=f"无法读取 CSV：{exc}")],
            filename=filename,
            sha256=digest,
        )

    missing = [column for column in QUOTE_COLUMNS if column not in frame.columns]
    for column in missing:
        errors.append(RowError(row_number=1, field=column, message="缺少必填列"))
    if missing:
        return QuoteImportPreview(rows=[], errors=errors, filename=filename, sha256=digest)

    for index, record in frame[QUOTE_COLUMNS].iterrows():
        values = {key: ("" if pd.isna(value) else value) for key, value in record.to_dict().items()}
        try:
            rows.append(QuoteRow.model_validate(values))
        except ValidationError as exc:
            for issue in exc.errors():
                errors.append(
                    RowError(
                        row_number=int(index) + 2,
                        field=str(issue["loc"][0]),
                        message=issue["msg"],
                    )
                )

    if not len(frame.index):
        errors.append(RowError(row_number=2, field="file", message="CSV 中没有数据行"))

    suppliers = [row.supplier.casefold() for row in rows]
    duplicates = sorted({item for item in suppliers if suppliers.count(item) > 1})
    for duplicate in duplicates:
        errors.append(RowError(row_number=1, field="supplier", message=f"供应商重复：{duplicate}"))

    currencies = sorted({row.currency for row in rows})
    if len(currencies) > 1:
        errors.append(
            RowError(
                row_number=1,
                field="currency",
                message=f"V1 不做实时换汇，请统一币种：{', '.join(currencies)}",
            )
        )

    return QuoteImportPreview(rows=rows, errors=errors, filename=filename, sha256=digest)


def import_quotes(
    project_id: int,
    source: str | Path | bytes | BinaryIO,
    batch_name: str,
    *,
    upload_root: Path | None = None,
    session: Session | None = None,
) -> Artifact:
    preview = preview_quote_csv(source)
    if not preview.is_valid:
        raise QuoteImportValidationError(preview)

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(preview.filename).name)
    raw, _ = _read_source(source)

    with session_context(session) as db:
        existing = db.scalar(
            select(Artifact).where(
                Artifact.project_id == project_id,
                Artifact.artifact_type == "supplier_quotes",
                Artifact.sha256 == preview.sha256,
            )
        )
        if existing:
            return existing

        artifact = Artifact(
            project_id=project_id,
            artifact_type="supplier_quotes",
            batch_name=batch_name.strip() or "未命名报价批次",
            original_filename=preview.filename,
            sha256=preview.sha256,
            parse_status="valid",
        )
        db.add(artifact)
        db.flush()

        project_dir = (upload_root or settings.upload_dir) / str(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        stored_path = project_dir / f"{artifact.id}_{safe_name}"
        stored_path.write_bytes(raw)
        artifact.stored_path = str(stored_path)

        for row_number, row in enumerate(preview.rows, start=2):
            quote = SupplierQuote(artifact_id=artifact.id, **row.model_dump())
            db.add(quote)
            db.flush()
            supplier = db.scalar(
                select(BusinessObject).where(
                    BusinessObject.project_id == project_id,
                    BusinessObject.object_type == "supplier",
                    BusinessObject.external_key == row.supplier,
                )
            )
            if not supplier:
                supplier = BusinessObject(
                    project_id=project_id,
                    object_type="supplier",
                    external_key=row.supplier,
                    display_name=row.supplier,
                )
                db.add(supplier)
                db.flush()
            create_evidence(
                project_id=project_id,
                evidence_type="supplier_quote_row",
                source_entity_type="supplier_quote",
                source_entity_id=quote.id,
                locator={
                    "artifact_id": artifact.id,
                    "csv_row": row_number,
                    "supplier": row.supplier,
                },
                excerpt=json.dumps(row.model_dump(), ensure_ascii=False, sort_keys=True),
                business_object_id=supplier.id,
                session=db,
            )

        db.add(
            AuditEvent(
                project_id=project_id,
                actor_role="项目负责人",
                action="supplier_quotes_imported",
                entity_type="artifact",
                entity_id=artifact.id,
                detail_json=json.dumps({"rows": len(preview.rows)}, ensure_ascii=False),
            )
        )
    return artifact


def list_quote_artifacts(
    project_id: int, session: Session | None = None
) -> list[Artifact]:
    with session_context(session) as db:
        return list(
            db.scalars(
                select(Artifact)
                .where(
                    Artifact.project_id == project_id,
                    Artifact.artifact_type == "supplier_quotes",
                )
                .order_by(Artifact.created_at.desc(), Artifact.id.desc())
            )
        )


def get_quotes(
    project_id: int, artifact_id: int, session: Session | None = None
) -> list[SupplierQuote]:
    with session_context(session) as db:
        artifact = db.get(Artifact, artifact_id)
        if not artifact or artifact.project_id != project_id:
            raise ValueError("报价批次不存在或不属于当前项目。")
        return list(
            db.scalars(
                select(SupplierQuote)
                .where(SupplierQuote.artifact_id == artifact_id)
                .order_by(SupplierQuote.id)
            )
        )

