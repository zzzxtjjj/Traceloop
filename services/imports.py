import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from typing import BinaryIO
from xml.etree import ElementTree

import pandas as pd
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import settings
from core.db import session_context
from core.models import Artifact, AuditEvent, BusinessObject, SupplierQuote
from core.schemas import QuoteImportPreview, QuoteRow, RowError
from services.data_intelligence import assess_readiness, suggest_column_mapping
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


def _read_quote_table(raw: bytes, filename: str) -> pd.DataFrame:
    if Path(filename).suffix.casefold() != ".xlsx":
        return pd.read_csv(io.BytesIO(raw), dtype="string")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {
            item.get("Id"): item.get("Target") for item in relationships.findall("{*}Relationship")
        }
        sheet = next(
            (
                item
                for item in workbook.findall("{*}sheets/{*}sheet")
                if item.get("state", "visible") == "visible"
            ),
            None,
        )
        if sheet is None:
            return pd.DataFrame()
        relation_id = sheet.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )
        sheet_path = "xl/" + rel_map.get(relation_id, "").lstrip("/").removeprefix("xl/")
        sheet_root = ElementTree.fromstring(archive.read(sheet_path))
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [
                "".join(node.text or "" for node in item.findall(".//{*}t"))
                for item in strings_root.findall("{*}si")
            ]

        def column_number(reference: str) -> int:
            letters = re.match(r"[A-Z]+", reference.upper())
            result = 0
            for char in letters.group(0) if letters else "":
                result = result * 26 + ord(char) - 64
            return result - 1

        rows = {}
        for row in sheet_root.findall(".//{*}sheetData/{*}row"):
            values = rows.setdefault(int(row.get("r", "0")), {})
            for cell in row.findall("{*}c"):
                value = cell.findtext("{*}v", "")
                if cell.get("t") == "inlineStr":
                    value = "".join(node.text or "" for node in cell.findall(".//{*}t"))
                elif cell.get("t") == "s" and value.isdigit() and int(value) < len(shared):
                    value = shared[int(value)]
                values[column_number(cell.get("r", ""))] = value
        if not rows:
            return pd.DataFrame()
        header_number = min(rows)
        header = rows[header_number]
        headers = [header.get(index, "") for index in range(max(header, default=-1) + 1)]
        records = []
        for row_number in sorted(rows):
            if row_number == header_number:
                continue
            values = rows[row_number]
            records.append(
                {
                    headers[index]: values.get(index, "")
                    for index in range(len(headers))
                    if headers[index]
                }
            )
        return pd.DataFrame(records)


def preview_quote_csv(source: str | Path | bytes | BinaryIO) -> QuoteImportPreview:
    raw, filename = _read_source(source)
    digest = hashlib.sha256(raw).hexdigest()
    errors: list[RowError] = []
    rows: list[QuoteRow] = []

    try:
        frame = _read_quote_table(raw, filename).astype("string")
    except Exception as exc:
        return QuoteImportPreview(
            rows=[],
            errors=[RowError(row_number=1, field="file", message=f"无法读取 CSV：{exc}")],
            filename=filename,
            sha256=digest,
        )

    mapping_details = suggest_column_mapping(
        [str(column) for column in frame.columns], domain="supplier_quotation"
    )
    aliases = {
        "supplier": {"supplier", "supplier name", "supplier_name", "vendor", "seller"},
        "unit_price": {"unit price", "unit_price", "price", "unit price range", "listed price"},
        "currency": {"currency", "currency code", "currency_code"},
        "moq": {"moq", "minimum order quantity", "min order"},
        "lead_time_days": {"lead time", "lead_time", "lead time days", "delivery days"},
        "payment_terms": {"payment terms", "payment_terms", "payment term"},
        "quality_note": {"quality note", "quality_note", "quality", "remarks", "note"},
    }
    normalized = {re.sub(r"[^a-z0-9]+", "", str(name).casefold()): name for name in frame.columns}
    sources = {}
    for target, candidates in aliases.items():
        for candidate in candidates:
            original = normalized.get(re.sub(r"[^a-z0-9]+", "", candidate.casefold()))
            if original is not None:
                sources[target] = original
                break
    missing = [
        column for column in QUOTE_COLUMNS if column not in sources and column != "quality_note"
    ]
    mapped_rows = []
    for _, record in frame.iterrows():
        row = {}
        for original, value in record.items():
            details = mapping_details.get(str(original), {})
            key = details.get("canonical_field") or f"custom:{original}"
            row[key] = None if pd.isna(value) else str(value).strip()
        mapped_rows.append(row)
    for column in missing:
        errors.append(RowError(row_number=1, field=column, message="缺少必填列"))
    if missing:
        return QuoteImportPreview(
            rows=[],
            errors=errors,
            filename=filename,
            sha256=digest,
            column_mapping=mapping_details,
            readiness=assess_readiness(
                domain="supplier_quotation",
                mapped_fields=set(sources),
                row_count=len(frame.index),
            ),
            mapped_rows=mapped_rows,
        )

    for index, record in frame.iterrows():
        values = {
            key: (
                ""
                if key not in sources or pd.isna(record.get(sources[key]))
                else record.get(sources[key])
            )
            for key in QUOTE_COLUMNS
        }
        price_text = str(values["unit_price"]).strip()
        if "not disclosed" in price_text.casefold() or "listed price" in price_text.casefold():
            values["unit_price"] = ""
        else:
            match = re.fullmatch(r"\s*(?:[A-Z]{3}\s*)?([0-9]+(?:\.[0-9]+)?)\s*", price_text, re.I)
            values["unit_price"] = match.group(1) if match else ""
        for field in ("moq", "lead_time_days"):
            if str(values[field]).casefold().strip() in {
                "not disclosed",
                "not disclosed in page snapshot",
                "n/a",
                "-",
            }:
                values[field] = ""
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

    return QuoteImportPreview(
        rows=rows,
        errors=errors,
        filename=filename,
        sha256=digest,
        column_mapping=mapping_details,
        readiness=assess_readiness(
            domain="supplier_quotation",
            mapped_fields=set(sources),
            row_count=len(frame.index),
        ),
        mapped_rows=mapped_rows,
    )


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


def list_quote_artifacts(project_id: int, session: Session | None = None) -> list[Artifact]:
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
