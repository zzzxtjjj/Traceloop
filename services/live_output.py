"""UTF-8 persistence helpers for review-only live AI outputs."""

import json
from pathlib import Path
from typing import Any


def save_live_output(
    output_dir: Path,
    *,
    stem: str,
    payload: dict[str, Any],
    markdown: str,
) -> tuple[Path, Path]:
    """Persist a JSON envelope and Markdown draft without terminal encoding dependence."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(markdown, encoding="utf-8")
    return json_path, markdown_path


def read_live_output(json_path: Path, markdown_path: Path) -> tuple[dict[str, Any], str]:
    """Read saved output using explicit UTF-8 decoding."""
    return (
        json.loads(json_path.read_text(encoding="utf-8")),
        markdown_path.read_text(encoding="utf-8"),
    )
