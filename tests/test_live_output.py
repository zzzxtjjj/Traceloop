from pathlib import Path

from services.live_output import read_live_output, save_live_output


def test_live_output_round_trips_german_text(tmp_path: Path) -> None:
    payload = {"title": "Heißluftfritteuse für köstliche Äpfel", "status": "待审核"}
    markdown = "# Produktentwurf\n\nÜberprüfung: Größe 4 L · Äpfel\n"
    json_path, markdown_path = save_live_output(
        tmp_path,
        stem="demo1_de_draft",
        payload=payload,
        markdown=markdown,
    )

    loaded_payload, loaded_markdown = read_live_output(json_path, markdown_path)
    assert loaded_payload == payload
    assert loaded_markdown == markdown
