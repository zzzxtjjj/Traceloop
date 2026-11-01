from services.document_parser import parse_bytes
from tests.test_document_parser_formats import _zip_bytes


def test_corrupt_docx_is_failed() -> None:
    assert parse_bytes(b"not-a-zip", ".docx").status == "failed"


def test_empty_docx_is_failed() -> None:
    raw = _zip_bytes({"word/document.xml": '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>'})
    assert parse_bytes(raw, ".docx").error_code == "EMPTY_DOCUMENT"
