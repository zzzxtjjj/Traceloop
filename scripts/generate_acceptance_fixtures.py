"""Generate deterministic multi-format fixtures for manual and automated acceptance."""

import csv
import io
import json
import zipfile
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1] / "data" / "acceptance"


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def zip_bytes(files: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def make_docx(product: str, market: str) -> bytes:
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = (
        f'<w:p xmlns:w="{ns}"><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        f"<w:r><w:t>{product} 出口要求</w:t></w:r></w:p>"
        f'<w:p xmlns:w="{ns}"><w:r><w:t>目标市场：{market}。交付周期：28 天。</w:t></w:r></w:p>'
        f'<w:p xmlns:w="{ns}"><w:pPr><w:pStyle w:val="Heading2"/></w:pPr>'
        "<w:r><w:t>Packaging and testing</w:t></w:r></w:p>"
        f'<w:tbl xmlns:w="{ns}"><w:tr><w:tc><w:p><w:r><w:t>Requirement</w:t></w:r></w:p></w:tc>'
        "<w:tc><w:p><w:r><w:t>Evidence</w:t></w:r></w:p></w:tc></w:tr>"
        "<w:tr><w:tc><w:p><w:r><w:t>EU plug and safety report</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>Test report pending</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
    )
    document = f'<w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>'
    return zip_bytes(
        {
            "word/document.xml": document,
            "[Content_Types].xml": "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'/>",
        }
    )


def make_xlsx(product: str) -> bytes:
    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    workbook = (
        f'<workbook xmlns="{main_ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Supplier Quotes" r:id="rId1"/><sheet name="Hidden Notes" state="hidden" r:id="rId2"/></sheets></workbook>'
    )
    quotes = (
        f'<worksheet xmlns="{main_ns}"><mergeCells count="1"><mergeCell ref="A1:D1"/></mergeCells><sheetData>'
        f'<row r="1"><c r="A1" t="inlineStr"><is><t>{product} 供应商报价</t></is></c></row>'
        '<row r="2"><c r="A2" t="inlineStr"><is><t>Supplier</t></is></c><c r="B2" t="inlineStr"><is><t>Price USD</t></is></c><c r="C2" t="inlineStr"><is><t>MOQ</t></is></c><c r="D2" t="inlineStr"><is><t>Lead days</t></is></c></row>'
        '<row r="3"><c r="A3" t="inlineStr"><is><t>Ningbo Appliance Co</t></is></c><c r="B3"><v>38.5</v></c><c r="C3"><v>300</v></c><c r="D3"><f>21+7</f></c></row>'
        '</sheetData></worksheet>'
    )
    hidden = f'<worksheet xmlns="{main_ns}"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Internal note</t></is></c></row></sheetData></worksheet>'
    rels = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>'
    return zip_bytes({"xl/workbook.xml": workbook, "xl/_rels/workbook.xml.rels": rels, "xl/worksheets/sheet1.xml": quotes, "xl/worksheets/sheet2.xml": hidden})


def make_pdf(product: str, market: str) -> bytes:
    document = pymupdf.open()
    for page_number in range(1, 4):
        page = document.new_page(width=595, height=842)
        page.insert_text((60, 90), f"{product} 出口规格 - 第 {page_number} 页")
        page.insert_text((60, 130), f"目标市场：{market} | 电压：220-240V | 交付：28 天")
        page.insert_text((60, 170), "供应商依据：安全报告待补；需要包装跌落测试")
    return document.tobytes()


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    fields = ["supplier", "unit_price", "currency", "moq", "lead_time_days", "payment_terms", "quality_note"]
    quotes = [
        {"supplier": f"Supplier {index:02d}", "unit_price": f"{32 + index * 0.73:.2f}", "currency": "USD" if index % 4 else "EUR", "moq": 200 + index * 25, "lead_time_days": 18 + index % 17, "payment_terms": "30% deposit; 70% before shipment", "quality_note": "CE report available" if index % 3 else "Safety report pending"}
        for index in range(1, 31)
    ]
    demos = {
        "demo1": ("便携式空气炸锅 4L", "德国"),
        "demo2": ("桌面空气净化器", "美国"),
        "demo3": ("多功能电热水壶", "德国"),
    }
    for demo_name, (product, market) in demos.items():
        folder = ROOT / demo_name
        write_csv(folder / "supplier_quotes_30.csv", quotes, fields)
        write_csv(folder / "supplier_quotes_missing_fields.csv", [{"supplier": "Incomplete Supplier", "unit_price": "41.2", "currency": "USD"}], fields[:3])
        write_csv(folder / "supplier_quotes_conflict.csv", quotes[:5] + [{**quotes[0], "unit_price": "99.99", "lead_time_days": 60}], fields)
        reviews = [{"review_id": f"{demo_name.upper()}-R-{index:04d}", "review_text": ["涂层两周后脱落", "包装到货时破损", "说明书语言不清楚", "加热均匀且速度快"][index % 4], "rating": (index % 5) + 1, "market": "DE" if index % 2 else "US"} for index in range(1, 121)]
        write_csv(folder / "customer_reviews_120.csv", reviews, ["review_id", "review_text", "rating", "market"])
        write_csv(folder / "customer_reviews_duplicates.csv", reviews[:20] + reviews[:10], ["review_id", "review_text", "rating", "market"])
        write_csv(folder / "customer_reviews_missing_batch.csv", [{"review_id": f"{demo_name.upper()}-M-001", "review_text": "包装破损", "rating": 2}], ["review_id", "review_text", "rating"])
        (folder / "specification.pdf").write_bytes(make_pdf(product, market))
        (folder / "specification.docx").write_bytes(make_docx(product, market))
        (folder / "supplier_quotes.xlsx").write_bytes(make_xlsx(product))
        (folder / "README.md").write_text(f"# {demo_name} 验收数据\n\n产品：{product}\n样本：30 条供应商报价、120 条客户评价、PDF/DOCX/XLSX 多格式文件，并包含缺字段、冲突、重复记录异常样本。\n", encoding="utf-8")
    print(json.dumps({"directory": str(ROOT), "demos": list(demos), "quote_count": 30, "review_count": 120}, ensure_ascii=False))


if __name__ == "__main__":
    main()
