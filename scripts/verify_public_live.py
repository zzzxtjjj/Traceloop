"""Single-request public-document verification; never changes business records."""

import json
from pathlib import Path

from core.db import session_scope
from services.document_ai_schemas import DocumentSegment, DocumentSnapshot, SourceLocation
from services.document_ai_service import analyze_document
from services.document_fact_service import source_blocks
from services.document_parser import parse_bytes
from services.live_output import read_live_output, save_live_output
from services.model_provider import OpenAICompatibleProvider


def main():
    # Audit public on-disk files, not private project artifacts.
    # Member existence below is not an authenticated browser session.
    from sqlalchemy import select

    from core.models import ProjectMember, User

    root = Path(__file__).resolve().parents[1]
    provider = OpenAICompatibleProvider.from_settings()
    provider.max_attempts = 1
    provider.max_output_tokens = 4096
    output = root / "docs/competition/live_outputs/philips_pre_real_data"
    if (output / "single_request.json").exists():
        raise RuntimeError("Existing verification record: refusing another paid request")
    record = {"request_limit": 1, "business_records_changed": False}
    if not provider.api_key:
        record.update(status="NOT TESTED", reason="Provider key absent")
    else:
        # Public source files can be analyzed without private project data.
        # Select a verified active project member, never impersonate an owner.
        with session_scope() as db:
            from core.models import Project

            project = db.scalar(
                select(Project).where(Project.name == "Philips NA120 Public Benchmark")
            )
            member = db.scalar(
                select(ProjectMember)
                .join(User)
                .where(
                    ProjectMember.project_id == project.id,
                    User.active.is_(True),
                    User.email_verified.is_(True),
                )
            )
            if not member:
                raise RuntimeError("No verified project member; live request refused")
            project_id = project.id
        source = root / (
            "data/acceptance/public_benchmark/philips_na120/"
            "06_upload_ready/Philips_NA120_Public_Product_Brief.docx"
        )
        parsed = parse_bytes(source.read_bytes(), ".docx")
        if parsed.status != "succeeded":
            raise RuntimeError("Public source did not parse")
        segments = []
        for index, block in enumerate(
            source_blocks({"document_blocks": list(parsed.document_blocks)}), 1
        ):
            text = str(block.get("text", "")).strip()
            if not text:
                continue
            locator = {
                key: block[key]
                for key in ("paragraph_index", "table_index", "row_index", "column_index")
                if key in block
            }
            segments.append(
                DocumentSegment(
                    evidence_id=index,
                    file_id=1,
                    file_version=parsed.content_hash,
                    content_kind="text",
                    locator=SourceLocation(kind="document", **locator),
                    content=text,
                )
            )
        snapshot = DocumentSnapshot(
            project_id=project_id,
            file_id=1,
            file_version=parsed.content_hash,
            filename=source.name,
            file_type="docx",
            parser_status="parsed",
            segments=segments,
            project_context="Public document verification only. Local snapshot IDs, "
            "not persisted business Evidence. Needs human review; do not publish.",
        )
        record.update(
            source=str(source.relative_to(root)),
            source_hash=parsed.content_hash,
            segment_count=len(segments),
        )
        try:
            result = analyze_document(snapshot, provider=provider)
            record.update(status="PASS", output=result.model_dump(mode="json"))
        except Exception as exc:
            record.update(
                status="FAIL", error_type=type(exc).__name__, error_detail=str(exc)[:4000]
            )
        record["call"] = provider.last_call
    paths = save_live_output(
        output,
        stem="single_request",
        payload=record,
        markdown="# PUBLIC DATA / LIVE AI DRAFT / NOT APPROVED\n\n"
        + json.dumps(record, ensure_ascii=False, indent=2),
    )
    restored, _ = read_live_output(*paths)
    assert restored == record
    print(
        json.dumps(
            {key: value for key, value in record.items() if key != "output"}, ensure_ascii=True
        )
    )


if __name__ == "__main__":
    main()
