from io import BytesIO

from pypdf import PdfWriter

import services.document_parser as document_parser
from services.document_parser import parse_bytes


def _pdf(*, encrypted: bool = False) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    if encrypted:
        writer.encrypt("secret")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_multi_page_blank_pdf_is_needs_ocr() -> None:
    parsed = parse_bytes(_pdf(), ".pdf")
    assert parsed.status == "needs_ocr"
    assert parsed.locator["page_count"] == 2
    assert parsed.error_code in {"NO_TEXT_LAYER", "OCR_NOT_CONFIGURED"}


def test_encrypted_pdf_is_rejected() -> None:
    parsed = parse_bytes(_pdf(encrypted=True), ".pdf")
    assert parsed.status in {"failed", "unsupported"}
    assert parsed.error_code == "ENCRYPTED_PDF"


def test_corrupt_pdf_is_not_success() -> None:
    parsed = parse_bytes(b"%PDF-corrupt", ".pdf")
    assert parsed.status in {"failed", "unsupported"}


def test_force_ocr_uses_injected_engine(monkeypatch) -> None:
    monkeypatch.setattr(document_parser, "_ocr_settings", lambda: ("tesseract", "eng+chi_sim"))
    monkeypatch.setattr(
        document_parser,
        "_ocr_page",
        lambda image, command, languages: [
            {"text": "Invoice 123", "confidence": 91.0, "bbox": [10, 20, 40, 12]}
        ],
    )
    parsed = parse_bytes(_pdf(), ".pdf", force_ocr=True)
    assert parsed.status == "succeeded"
    assert parsed.document_blocks[0]["kind"] == "ocr_text"
    assert parsed.document_blocks[0]["page"] == 1
    assert parsed.document_blocks[0]["confidence"] == 91.0
    assert len(parsed.document_blocks[0]["bbox_pdf"]) == 4
