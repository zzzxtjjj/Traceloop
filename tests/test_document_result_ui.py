from core.document_result_ui import format_source_location


def test_formats_document_paragraph_location_in_chinese():
    assert format_source_location({"paragraph_index": 1}) == "第 2 段"


def test_formats_pdf_page_location_in_chinese():
    assert format_source_location({"page": 3}) == "第 3 页"


def test_formats_spreadsheet_cell_location_in_chinese():
    assert (
        format_source_location({"sheet": "Quotes", "cell_range": "B4"})
        == "工作表“Quotes”，单元格 B4"
    )


def test_formats_table_coordinates_in_chinese():
    assert (
        format_source_location({"table_index": 0, "row_index": 1, "column_index": 2})
        == "第 1 个表格，第 2 行第 3 列"
    )
