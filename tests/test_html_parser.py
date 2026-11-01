from services.document_parser import parse_bytes


def test_html_is_no_longer_a_supported_business_parser():
    result = parse_bytes(b"<html><body>Product</body></html>", ".html")
    assert result.status == "unsupported"
    assert result.error_code == "UNSUPPORTED_FILE_TYPE"
