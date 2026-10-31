"""Controlled project file storage and authorized download primitives."""

import hashlib
import mimetypes
import re
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import settings
from core.db import session_context
from core.errors import CrossProjectReferenceError
from core.models import Artifact
from services.auth_service import require_session_member

ALLOWED_EXTENSIONS = {".csv", ".txt", ".pdf", ".docx", ".xlsx"}
MAX_FILE_SIZE = 20 * 1024 * 1024


def _read_source(source: bytes | bytearray | BinaryIO) -> bytes:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    if not hasattr(source, "read"):
        raise TypeError("文件来源必须是 bytes 或可读文件对象。")
    raw = source.read()
    if not isinstance(raw, bytes):
        raise TypeError("文件读取结果必须是 bytes。")
    return raw


def _safe_filename(filename: str) -> str:
    name = Path(filename).name
    if not name or name in {".", ".."}:
        raise ValueError("文件名无效。")
    suffix = Path(name).suffix.casefold()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("UNSUPPORTED_FILE_TYPE")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem).strip("._") or "file"
    return f"{stem}{suffix}"


def _validate_content(filename: str, raw: bytes) -> str:
    suffix = Path(filename).suffix.casefold()
    if suffix == ".pdf":
        if not raw.startswith(b"%PDF-"):
            raise ValueError("MIME_CONTENT_MISMATCH")
    elif suffix in {".docx", ".xlsx"}:
        if not raw.startswith(b"PK\x03\x04"):
            raise ValueError("MIME_CONTENT_MISMATCH")
    else:
        if b"\x00" in raw:
            raise ValueError("MIME_CONTENT_MISMATCH")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = raw.decode("cp1252")
            except UnicodeDecodeError as exc:
                raise ValueError("INVALID_TEXT_ENCODING") from exc
        if any(ord(char) < 32 and char not in "\r\n\t\f" for char in text):
            raise ValueError("MIME_CONTENT_MISMATCH")
    guessed_mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    if suffix == ".csv":
        return "text/csv"
    if suffix == ".txt":
        return "text/plain"
    return guessed_mime


def upload_project_file(
    *,
    project_id: int,
    session_token: str,
    source: bytes | bytearray | BinaryIO,
    filename: str,
    session: Session | None = None,
    upload_root: Path | None = None,
) -> Artifact:
    safe_name = _safe_filename(filename)
    raw = _read_source(source)
    if not raw:
        raise ValueError("文件不能为空。")
    if len(raw) > MAX_FILE_SIZE:
        raise ValueError("文件超过 20 MB 限制。")
    guessed_mime = _validate_content(safe_name, raw)
    digest = hashlib.sha256(raw).hexdigest()
    root = (upload_root or settings.upload_dir).resolve()
    project_dir = (root / str(project_id)).resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    relative_location = Path(str(project_id)) / f"{digest}_{safe_name}"
    target = (root / relative_location).resolve()
    if root not in target.parents:
        raise ValueError("文件存储路径无效。")
    with session_context(session) as db:
        actor, _membership = require_session_member(session_token, project_id, session=db)
        actor_user_id = actor.id
        existing = db.scalar(
            select(Artifact).where(
                Artifact.project_id == project_id,
                Artifact.sha256 == digest,
            )
        )
        if existing:
            return existing
        artifact = Artifact(
            project_id=project_id,
            artifact_type="project_file",
            batch_name="",
            original_filename=safe_name,
            sha256=digest,
            file_hash=digest,
            uploader_id=actor_user_id,
            mime_type=guessed_mime,
            file_size=len(raw),
            parsing_status="pending",
            storage_location=relative_location.as_posix(),
            stored_path="",
        )
        db.add(artifact)
        db.flush()
        try:
            target.write_bytes(raw)
        except Exception:
            db.delete(artifact)
            db.flush()
            raise
        artifact.stored_path = str(target)
        db.flush()
        return artifact


def download_project_file(
    *,
    project_id: int,
    session_token: str,
    artifact_id: int,
    session: Session | None = None,
    upload_root: Path | None = None,
) -> tuple[str, bytes, str]:
    root = (upload_root or settings.upload_dir).resolve()
    with session_context(session) as db:
        require_session_member(session_token, project_id, session=db)
        artifact = db.get(Artifact, artifact_id)
        if not artifact or artifact.project_id != project_id:
            raise CrossProjectReferenceError("文件不属于当前项目。")
        if not artifact.storage_location:
            raise ValueError("文件尚未保存到受控文件库。")
        target = (root / artifact.storage_location).resolve()
        if root not in target.parents or not target.is_file():
            raise ValueError("文件当前不可用。")
        raw = target.read_bytes()
        if hashlib.sha256(raw).hexdigest() != (artifact.file_hash or artifact.sha256):
            raise ValueError("文件完整性校验失败。")
        return artifact.original_filename, raw, artifact.mime_type
