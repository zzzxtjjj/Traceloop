import io
import zipfile

from services.document_parser import parse_bytes


def _zip_bytes(files: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def test_docx_preserves_headings_paragraphs_and_tables() -> None:
    raw = _zip_bytes(
        {
            "word/document.xml": (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body>"
                '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>要求</w:t></w:r></w:p>'
                '<w:p><w:r><w:t>交付 28 days</w:t></w:r></w:p>'
                "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Product</w:t></w:r></w:p></w:tc>"
                "<w:tc><w:p><w:r><w:t>Price</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
                "</w:body></w:document>"
            )
        }
    )
    parsed = parse_bytes(raw, ".docx")
    assert parsed.status == "succeeded"
    assert [block["kind"] for block in parsed.document_blocks] == [
        "heading",
        "paragraph",
        "table",
    ]
    assert parsed.extracted_tables[0]["rows"][0]["values"] == ["Product", "Price"]


def test_xlsx_preserves_sheet_cell_and_formula() -> None:
    raw = _zip_bytes(
        {
            "xl/workbook.xml": (
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Quotes" r:id="rId1"/></sheets></workbook>'
            ),
            "xl/_rels/workbook.xml.rels": (
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>'
            ),
            "xl/worksheets/sheet1.xml": (
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                "<sheetData><row r=\"1\"><c r=\"A1\"><v>Product</v></c>"
                '<c r="B1"><f>SUM(B2:B3)</f><v>3750</v></c></row></sheetData></worksheet>'
            ),
        }
    )
    parsed = parse_bytes(raw, ".xlsx")
    assert parsed.status == "succeeded"
    assert parsed.document_blocks[0]["sheet"] == "Quotes"
    assert parsed.document_blocks[1]["formula"] == "SUM(B2:B3)"
    assert parsed.document_blocks[1]["value"] == "3750"


def test_pdf_without_optional_parser_is_explicitly_not_success() -> None:
    parsed = parse_bytes(b"%PDF-invalid", ".pdf")
    assert parsed.status in {"unsupported", "failed", "needs_ocr"}
    if parsed.status == "unsupported":
        assert parsed.error_code == "UNSUPPORTED_FILE_TYPE"


def test_csv_and_txt_remain_compatible() -> None:
    assert parse_bytes(b"name,price\nA,10\n", ".csv").status == "succeeded"
    assert parse_bytes(b"one\ntwo\n", ".txt").status == "succeeded"
