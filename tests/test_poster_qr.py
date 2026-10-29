import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from scripts.generate_poster_qr import (
    DEFAULT_REPOSITORY_URL,
    generate_qr_svg,
    validate_public_url,
)

ROOT_DIR = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/zzzxtjjj/Traceloop",
        "not-a-url",
        "https://user:secret@example.com/repository",
    ],
)
def test_qr_generator_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(ValueError):
        validate_public_url(url)


def test_qr_generator_creates_parseable_svg(tmp_path: Path) -> None:
    output = tmp_path / "repository_qr.svg"

    generate_qr_svg(DEFAULT_REPOSITORY_URL, output)

    root = ET.parse(output).getroot()
    assert root.tag.endswith("svg")
    assert any(element.tag.endswith("path") for element in root.iter())
    assert output.stat().st_size > 500


def test_poster_embeds_repository_qr_and_preserves_print_size() -> None:
    poster_path = ROOT_DIR / "deliverables" / "poster" / "tradeloop_poster.svg"
    poster_text = poster_path.read_text(encoding="utf-8")
    root = ET.fromstring(poster_text)

    assert root.get("width") == "800mm"
    assert root.get("height") == "1800mm"
    assert "二维码占位" not in poster_text
    assert "repository_qr.svg" in poster_text
    assert DEFAULT_REPOSITORY_URL in poster_text


def test_committed_repository_qr_is_parseable() -> None:
    qr_path = ROOT_DIR / "deliverables" / "poster" / "repository_qr.svg"

    root = ET.parse(qr_path).getroot()

    assert root.tag.endswith("svg")
    assert any(element.tag.endswith("path") for element in root.iter())
