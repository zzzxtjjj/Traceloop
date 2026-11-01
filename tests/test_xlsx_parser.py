from services.document_parser import parse_bytes
from tests.test_document_parser_formats import _zip_bytes


def test_xlsx_preserves_hidden_sheet_and_merge_metadata() -> None:
    raw = _zip_bytes({
        "xl/workbook.xml": '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Hidden" state="hidden" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><mergeCells count="1"><mergeCell ref="A1:B1"/></mergeCells><sheetData><row r="1"><c r="A1"><f>SUM(A2:A3)</f></c></row></sheetData></worksheet>',
    })
    parsed = parse_bytes(raw, ".xlsx")
    assert parsed.status == "succeeded"
    assert parsed.document_blocks[0]["sheet_state"] == "hidden"
    assert parsed.document_blocks[0]["merged_ranges"] == ["A1:B1"]
    assert parsed.document_blocks[0]["cached_value"] is None
