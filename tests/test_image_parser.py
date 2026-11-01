from io import BytesIO

from PIL import Image

import services.document_parser as document_parser
from services.document_parser import parse_bytes


def _image_bytes(image_format: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 20), "white").save(output, format=image_format)
    return output.getvalue()


def test_png_and_jpg_preserve_image_metadata_without_ocr():
    for raw, suffix, image_format in (
        (_image_bytes("PNG"), ".png", "PNG"),
        (_image_bytes("JPEG"), ".jpg", "JPEG"),
    ):
        result = parse_bytes(raw, suffix)
        assert result.status in {"needs_ocr", "succeeded"}
        assert result.locator["format"] == image_format
        assert result.locator["width"] == 32
        assert result.locator["height"] == 20


def test_image_ocr_uses_existing_engine(monkeypatch):
    monkeypatch.setattr(document_parser, "_ocr_settings", lambda: ("tesseract", "eng"))
    monkeypatch.setattr(
        document_parser,
        "_ocr_page",
        lambda image, command, languages: [
            {"text": "NA120", "confidence": 94.0, "bbox": [1, 2, 20, 10]}
        ],
    )
    result = parse_bytes(_image_bytes("PNG"), ".png")
    assert result.status == "succeeded"
    assert result.text_excerpt == "NA120"
    assert result.document_blocks[0]["kind"] == "ocr_text"
