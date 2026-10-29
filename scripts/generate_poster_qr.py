import argparse
from pathlib import Path
from urllib.parse import urlsplit

import qrcode
import qrcode.image.svg

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REPOSITORY_URL = "https://github.com/zzzxtjjj/Traceloop"
DEFAULT_OUTPUT = ROOT_DIR / "deliverables" / "poster" / "repository_qr.svg"


def validate_public_url(value: str) -> str:
    url = value.strip()
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("二维码地址必须是有效的 HTTPS URL。")
    if parsed.username or parsed.password:
        raise ValueError("二维码地址不能包含用户名或密码。")
    return url


def generate_qr_svg(url: str, output: Path) -> None:
    safe_url = validate_public_url(url)
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_Q,
        box_size=10,
        border=4,
    )
    qr.add_data(safe_url, optimize=0)
    qr.make(fit=True)
    image = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the repository QR SVG used by the TradeLoop poster."
    )
    parser.add_argument("--url", default=DEFAULT_REPOSITORY_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        generate_qr_svg(args.url, args.output)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"QR SVG generated for {validate_public_url(args.url)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
