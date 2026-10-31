"""Deterministic CSV/TXT extraction with source locators and safe failure states."""

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import session_context
from core.errors import CrossProjectReferenceError
from core.models import Artifact, DocumentExtraction
from services.auth_service import require_session_member
from services.file_service import ALLOWED_EXTENSIONS, download_project_file


@dataclass(frozen=True)
class ParsedDocument:
    status: str
    parser_name: str
    parser_version: str
    content_hash: str
    text_excerpt: str
    locator: dict[str, object]
    error_code: str | None = None


def _decode(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError("INVALID_TEXT_ENCODING")


def parse_bytes(raw: bytes, suffix: str) -> ParsedDocument:
    content_hash = hashlib.sha256(raw).hexdigest()
    extension = suffix.casefold()
    if extension not in {".csv", ".txt"}:
        return ParsedDocument(
            status="unsupported",
            parser_name="none",
            parser_version="1",
            content_hash=content_hash,
            text_excerpt="",
            locator={"extension": extension},
            error_code="UNSUPPORTED_FILE_TYPE",
        )
    try:
        text, encoding = _decode(raw)
        if extension == ".txt":
            lines = text.splitlines()
            excerpt = "\n".join(f"{index}: {line}" for index, line in enumerate(lines, 1))
            return ParsedDocument(
                status="succeeded",
                parser_name="txt_lines",
                parser_version="1",
                content_hash=content_hash,
                text_excerpt=excerpt[:50_000],
                locator={"encoding": encoding, "line_count": len(lines), "line_start": 1},
            )
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ValueError("EMPTY_CSV_HEADER")
        rows = []
        for row_number, row in enumerate(reader, 2):
            rows.append(
                {
                    "row_number": row_number,
                    "columns": list(reader.fieldnames),
                    "values": {key: value or "" for key, value in row.items()},
                }
            )
        excerpt = json.dumps(rows[:200], ensure_ascii=False, sort_keys=True)
        return ParsedDocument(
            status="succeeded",
            parser_name="csv_rows",
            parser_version="1",
            content_hash=content_hash,
            text_excerpt=excerpt[:50_000],
            locator={
                "encoding": encoding,
                "columns": list(reader.fieldnames),
                "row_count": len(rows),
                "row_start": 2,
            },
        )
    except (UnicodeDecodeError, csv.Error, ValueError, TypeError) as exc:
        return ParsedDocument(
            status="failed",
            parser_name="csv_rows" if extension == ".csv" else "txt_lines",
            parser_version="1",
            content_hash=content_hash,
            text_excerpt="",
            locator={"extension": extension},
            error_code=str(exc)[:80] or "PARSER_ERROR",
        )


def extract_artifact(
    *,
    project_id: int,
    session_token: str,
    artifact_id: int,
    session: Session | None = None,
    upload_root: Path | None = None,
) -> DocumentExtraction:
    with session_context(session) as db:
        actor, _membership = require_session_member(session_token, project_id, session=db)
        artifact = db.get(Artifact, artifact_id)
        if not artifact or artifact.project_id != project_id:
            raise CrossProjectReferenceError("文件不属于当前项目。")
        suffix = Path(artifact.original_filename).suffix.casefold()
        if suffix not in ALLOWED_EXTENSIONS:
            parsed = parse_bytes(b"", suffix)
        else:
            _, raw, _ = download_project_file(
                project_id=project_id,
                session_token=session_token,
                artifact_id=artifact_id,
                session=db,
                upload_root=upload_root,
            )
            parsed = parse_bytes(raw, suffix)
        existing = db.scalar(
            select(DocumentExtraction)
            .where(
                DocumentExtraction.project_id == project_id,
                DocumentExtraction.artifact_id == artifact_id,
                DocumentExtraction.content_hash == parsed.content_hash,
                DocumentExtraction.status == parsed.status,
            )
            .order_by(DocumentExtraction.id.desc())
        )
        if existing:
            return existing
        extraction = DocumentExtraction(
            project_id=project_id,
            artifact_id=artifact_id,
            parser_name=parsed.parser_name,
            parser_version=parsed.parser_version,
            status=parsed.status,
            content_hash=parsed.content_hash,
            text_excerpt=parsed.text_excerpt,
            locator_json=json.dumps(parsed.locator, ensure_ascii=False, sort_keys=True),
            error_code=parsed.error_code,
        )
        db.add(extraction)
        artifact.parsing_status = parsed.status
        artifact.parse_status = "valid" if parsed.status == "succeeded" else parsed.status
        db.flush()
        return extraction
