"""Deterministic CSV/TXT extraction with source locators and safe failure states."""

import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

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
    document_blocks: tuple[dict[str, object], ...] = ()
    extracted_tables: tuple[dict[str, object], ...] = ()
    warnings: tuple[str, ...] = ()


def _decode(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError("INVALID_TEXT_ENCODING")


def _parse_docx(raw: bytes, content_hash: str) -> ParsedDocument:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        blocks: list[dict[str, object]] = []
        text_parts: list[str] = []
        paragraph_index = 0
        table_index = 0
        for child in root.findall(".//w:body/*", ns):
            if child.tag.endswith("}p"):
                text = "".join(node.text or "" for node in child.findall(".//w:t", ns)).strip()
                style = child.find("w:pPr/w:pStyle", ns)
                style_name = (
                    style.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val")
                    if style is not None
                    else None
                )
                if text:
                    kind = (
                        "heading"
                        if style_name and style_name.lower().startswith("heading")
                        else "paragraph"
                    )
                    blocks.append({"kind": kind, "paragraph_index": paragraph_index, "text": text})
                    text_parts.append(text)
                paragraph_index += 1
            elif child.tag.endswith("}tbl"):
                rows = []
                for row_index, row in enumerate(child.findall("w:tr", ns)):
                    values = [
                        "".join(node.text or "" for node in cell.findall(".//w:t", ns)).strip()
                        for cell in row.findall("w:tc", ns)
                    ]
                    rows.append({"row_index": row_index, "values": values})
                table = {"kind": "table", "table_index": table_index, "rows": rows}
                blocks.append(table)
                text_parts.append(json.dumps(rows, ensure_ascii=False))
                table_index += 1
        if not blocks:
            return ParsedDocument(
                "failed", "docx_xml", "1", content_hash, "", {"block_count": 0}, "EMPTY_DOCUMENT"
            )
        return ParsedDocument(
            "succeeded",
            "docx_xml",
            "1",
            content_hash,
            "\n".join(text_parts)[:50_000],
            {"block_count": len(blocks)},
            document_blocks=tuple(blocks),
            extracted_tables=tuple(item for item in blocks if item.get("kind") == "table"),
        )
    except (KeyError, ValueError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        return ParsedDocument(
            "failed", "docx_xml", "1", content_hash, "", {}, str(exc)[:80] or "INVALID_DOCX"
        )


def _parse_xlsx(raw: bytes, content_hash: str) -> ParsedDocument:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            shared = []
            if "xl/sharedStrings.xml" in archive.namelist():
                shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                shared = [
                    "".join(node.text or "" for node in item.findall(".//{*}t"))
                    for item in shared_root.findall("{*}si")
                ]
            rel_map = {rel.get("Id"): rel.get("Target") for rel in rels.findall("{*}Relationship")}
            blocks: list[dict[str, object]] = []
            tables: list[dict[str, object]] = []
            for sheet in workbook.findall("{*}sheets/{*}sheet"):
                name = sheet.get("name", "")
                sheet_state = sheet.get("state", "visible")
                target = rel_map.get(
                    sheet.get(
                        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                    ),
                    "",
                )
                path = "xl/" + target.lstrip("/").removeprefix("xl/")
                root = ElementTree.fromstring(archive.read(path))
                cells = []
                merged_ranges = [
                    item.get("ref", "") for item in root.findall(".//{*}mergeCells/{*}mergeCell")
                ]
                for cell in root.findall(".//{*}sheetData/{*}row/{*}c"):
                    ref = cell.get("r", "")
                    value = cell.find("{*}v")
                    raw_value = value.text if value is not None else ""
                    if cell.get("t") == "inlineStr":
                        raw_value = "".join(node.text or "" for node in cell.findall(".//{*}t"))
                    if (
                        cell.get("t") == "s"
                        and raw_value.isdigit()
                        and int(raw_value) < len(shared)
                    ):
                        raw_value = shared[int(raw_value)]
                    formula = cell.findtext("{*}f") or None
                    cached_value = (
                        raw_value if value is not None and raw_value != "" and formula else None
                    )
                    item = {
                        "kind": "spreadsheet_cell",
                        "sheet": name,
                        "sheet_state": sheet_state,
                        "cell": ref,
                        "value": raw_value,
                        "cached_value": cached_value,
                        "formula": formula,
                        "merged_ranges": merged_ranges,
                    }
                    cells.append(item)
                    blocks.append(item)
                tables.append(
                    {
                        "kind": "spreadsheet_sheet",
                        "sheet": name,
                        "sheet_state": sheet_state,
                        "merged_ranges": merged_ranges,
                        "cells": cells,
                    }
                )
            text = "\n".join(f"{item['sheet']}!{item['cell']}: {item['value']}" for item in blocks)
            if not blocks:
                return ParsedDocument(
                    "failed",
                    "xlsx_xml",
                    "1",
                    content_hash,
                    "",
                    {"sheet_count": len(tables)},
                    "EMPTY_WORKBOOK",
                )
            return ParsedDocument(
                "succeeded",
                "xlsx_xml",
                "1",
                content_hash,
                text[:50_000],
                {"sheet_count": len(tables)},
                document_blocks=tuple(blocks),
                extracted_tables=tuple(tables),
            )
    except (KeyError, ValueError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        return ParsedDocument(
            "failed", "xlsx_xml", "1", content_hash, "", {}, str(exc)[:80] or "INVALID_XLSX"
        )


def _parse_image(raw: bytes, content_hash: str, suffix: str) -> ParsedDocument:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            locator = {
                "extension": suffix,
                "format": image.format or suffix.lstrip("."),
                "width": image.width,
                "height": image.height,
                "mode": image.mode,
            }
            image_copy = image.copy()
    except Exception as exc:
        return ParsedDocument(
            "failed",
            "image_parser",
            "1",
            content_hash,
            "",
            {"extension": suffix},
            "INVALID_IMAGE",
            warnings=(str(exc)[:160],),
        )

    try:
        ocr = _ocr_settings()
    except RuntimeError as exc:
        return ParsedDocument(
            "needs_ocr",
            "image_parser",
            "1",
            content_hash,
            "",
            locator,
            "OCR_CONFIGURATION_INVALID",
            warnings=(str(exc),),
        )
    if not ocr:
        return ParsedDocument(
            "needs_ocr",
            "image_parser",
            "1",
            content_hash,
            "",
            locator,
            "OCR_NOT_CONFIGURED",
            warnings=("图片元数据已读取；文字识别需要配置 Tesseract。",),
        )
    try:
        blocks = _ocr_page(image_copy, command=ocr[0], languages=ocr[1])
    except Exception as exc:
        return ParsedDocument(
            "needs_ocr",
            "image_parser",
            "1",
            content_hash,
            "",
            locator,
            "OCR_FAILED",
            warnings=(str(exc)[:160],),
        )
    document_blocks = tuple(
        {"kind": "ocr_text", "block_index": index, **block} for index, block in enumerate(blocks)
    )
    text = " ".join(str(block["text"]) for block in document_blocks)
    warning = (
        ("部分图片文字 OCR 置信度较低，请人工核对。",)
        if any(float(block.get("confidence", 100)) < 70 for block in document_blocks)
        else ()
    )
    return ParsedDocument(
        "succeeded" if text else "needs_ocr",
        "image_parser+tesseract" if text else "image_parser",
        "1",
        content_hash,
        text[:50_000],
        locator,
        None if text else "OCR_EMPTY",
        document_blocks=document_blocks,
        warnings=warning,
    )


def _ocr_settings() -> tuple[str, str] | None:
    command = os.getenv("TESSERACT_CMD") or shutil.which("tesseract")
    languages = os.getenv("TRADELOOP_OCR_LANGUAGES", "eng+chi_sim")
    if not command:
        return None
    try:
        available = subprocess.run(
            [command, "--list-langs"], capture_output=True, text=True, timeout=5, check=False
        ).stdout.splitlines()
    except (OSError, subprocess.TimeoutExpired):
        return None
    missing = [item for item in languages.split("+") if item and item not in available]
    if missing:
        raise RuntimeError(f"OCR_LANGUAGES_MISSING:{','.join(missing)}")
    return command, languages


def _ocr_page(image, *, command: str, languages: str) -> list[dict[str, object]]:
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = command
    data = pytesseract.image_to_data(
        image, lang=languages, output_type=pytesseract.Output.DICT, timeout=30
    )
    blocks = []
    for index, text in enumerate(data.get("text", [])):
        value = str(text).strip()
        if not value:
            continue
        blocks.append(
            {
                "text": value,
                "confidence": float(data["conf"][index]),
                "bbox": [
                    data["left"][index],
                    data["top"][index],
                    data["width"][index],
                    data["height"][index],
                ],
            }
        )
    return blocks


def _parse_pdf(raw: bytes, content_hash: str, *, force_ocr: bool = False) -> ParsedDocument:
    if len(raw) < 20:
        return ParsedDocument(
            "unsupported",
            "none",
            "1",
            content_hash,
            "",
            {"extension": ".pdf"},
            "UNSUPPORTED_FILE_TYPE",
        )
    try:
        from pypdf import PdfReader
    except ImportError:
        return ParsedDocument(
            "unsupported",
            "none",
            "1",
            content_hash,
            "",
            {"extension": ".pdf"},
            "UNSUPPORTED_FILE_TYPE",
            warnings=("安装 pypdf 后启用 PDF 文本解析；扫描 PDF 还需要 OCR。",),
        )
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            return ParsedDocument("failed", "pypdf", "1", content_hash, "", {}, "ENCRYPTED_PDF")
        blocks = []
        tables = []
        parts = []
        for page_number, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or "").strip()
            if text:
                blocks.append({"kind": "page_text", "page": page_number, "text": text})
                parts.append(text)
                rows = [line for line in text.splitlines() if "\t" in line or "  " in line]
                if len(rows) >= 2:
                    table_rows = [re.split(r"\t+| {2,}", line.strip()) for line in rows]
                    tables.append(
                        {
                            "kind": "table",
                            "page": page_number,
                            "table_index": len(tables),
                            "rows": table_rows,
                        }
                    )
        needs_ocr_pages = [
            page_number
            for page_number in range(1, len(reader.pages) + 1)
            if force_ocr or not any(item.get("page") == page_number for item in blocks)
        ]
        if needs_ocr_pages:
            try:
                ocr = _ocr_settings()
                if not ocr:
                    return ParsedDocument(
                        "needs_ocr",
                        "pypdf",
                        "1",
                        content_hash,
                        "\n".join(parts)[:50_000],
                        {"page_count": len(reader.pages), "ocr_pages": needs_ocr_pages},
                        "OCR_NOT_CONFIGURED",
                        document_blocks=tuple(blocks),
                        extracted_tables=tuple(tables),
                        warnings=("OCR 引擎未安装或未配置 TESSERACT_CMD。",),
                    )
                import pymupdf

                document = pymupdf.open(stream=raw, filetype="pdf")
                for page_number in needs_ocr_pages:
                    page = document[page_number - 1]
                    pixmap = page.get_pixmap(dpi=300, alpha=False)
                    from PIL import Image

                    image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
                    ocr_blocks = _ocr_page(image, command=ocr[0], languages=ocr[1])
                    for block_index, item in enumerate(ocr_blocks):
                        scale_x = page.rect.width / pixmap.width
                        scale_y = page.rect.height / pixmap.height
                        item["bbox_pdf"] = [
                            round(item["bbox"][0] * scale_x, 2),
                            round(item["bbox"][1] * scale_y, 2),
                            round(item["bbox"][2] * scale_x, 2),
                            round(item["bbox"][3] * scale_y, 2),
                        ]
                        blocks.append(
                            {
                                "kind": "ocr_text",
                                "page": page_number,
                                "block_index": block_index,
                                **item,
                            }
                        )
                        parts.append(item["text"])
                status = "succeeded" if parts else "needs_ocr"
                warning = (
                    ("部分页面 OCR 置信度较低，请人工核对。",)
                    if any(
                        item.get("confidence", 100) < 70
                        for item in blocks
                        if item.get("kind") == "ocr_text"
                    )
                    else ()
                )
                return ParsedDocument(
                    status,
                    "pypdf+pymupdf+tesseract",
                    "1",
                    content_hash,
                    "\n".join(parts)[:50_000],
                    {"page_count": len(reader.pages), "ocr_pages": needs_ocr_pages},
                    document_blocks=tuple(blocks),
                    extracted_tables=tuple(tables),
                    warnings=warning,
                )
            except RuntimeError as exc:
                return ParsedDocument(
                    "needs_ocr",
                    "pypdf",
                    "1",
                    content_hash,
                    "\n".join(parts)[:50_000],
                    {"page_count": len(reader.pages), "ocr_pages": needs_ocr_pages},
                    "OCR_CONFIGURATION_INVALID",
                    document_blocks=tuple(blocks),
                    warnings=(str(exc),),
                )
            except Exception as exc:
                return ParsedDocument(
                    "needs_ocr",
                    "pypdf",
                    "1",
                    content_hash,
                    "\n".join(parts)[:50_000],
                    {"page_count": len(reader.pages), "ocr_pages": needs_ocr_pages},
                    "OCR_FAILED",
                    document_blocks=tuple(blocks),
                    warnings=(str(exc)[:160],),
                )
        return ParsedDocument(
            "succeeded",
            "pypdf",
            "1",
            content_hash,
            "\n".join(parts)[:50_000],
            {"page_count": len(reader.pages)},
            document_blocks=tuple(blocks),
            extracted_tables=tuple(tables),
        )
    except Exception as exc:
        return ParsedDocument(
            "failed", "pypdf", "1", content_hash, "", {}, str(exc)[:80] or "INVALID_PDF"
        )


def parse_bytes(raw: bytes, suffix: str, *, force_ocr: bool = False) -> ParsedDocument:
    content_hash = hashlib.sha256(raw).hexdigest()
    extension = suffix.casefold()
    if extension == ".docx":
        return _parse_docx(raw, content_hash)
    if extension == ".xlsx":
        return _parse_xlsx(raw, content_hash)
    if extension == ".pdf":
        return _parse_pdf(raw, content_hash, force_ocr=force_ocr)
    if extension in {".png", ".jpg", ".jpeg"}:
        return _parse_image(raw, content_hash, extension)
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
            locator_json=json.dumps(
                {
                    **parsed.locator,
                    "document_blocks": list(parsed.document_blocks),
                    "extracted_tables": list(parsed.extracted_tables),
                    "warnings": list(parsed.warnings),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            error_code=parsed.error_code,
        )
        db.add(extraction)
        artifact.parsing_status = parsed.status
        artifact.parse_status = "valid" if parsed.status == "succeeded" else parsed.status
        db.flush()
        return extraction
