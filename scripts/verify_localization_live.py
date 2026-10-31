"""Opt-in six-request rehearsal using synthetic facts in an isolated database."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from core.models import AiRun, Base, Evidence, Project, ProjectMember, User  # noqa: E402
from services.localization_ai_service import generate_localized_copy  # noqa: E402
from services.model_provider import OpenAICompatibleProvider  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Allow exactly six model requests")
    args = parser.parse_args()
    if not args.live:
        print("未请求模型。添加 --live 后会执行六次模拟资料验收请求。")
        return 0
    provider = OpenAICompatibleProvider.from_settings()
    provider.max_attempts = 1
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    records = []
    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="模拟商品双语验收",
            product_name="水杯",
            access_code_hash="unused",
            markets_json='["US","DE"]',
        )
        user = User(display_name="验收负责人", email="localization@test.invalid")
        db.add_all([project, user])
        db.flush()
        db.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))
        source = Evidence(
            project_id=project.id,
            evidence_type="synthetic_product_spec",
            source_entity_type="project",
            source_entity_id=project.id,
            excerpt="模拟商品规格：不锈钢水杯，容量750毫升，银色。没有提供保温、认证或配送资料。",
            content_hash="synthetic-spec",
            dedupe_key="synthetic-spec",
        )
        db.add(source)
        db.flush()
        for market in ["US", "DE"]:
            parent_id = None
            for feedback in [
                "",
                "将标题改为以750 ml开头；卖点严格合并为两条："
                "容量与材质一条，银色一条。不要增加事实。",
                "标题删除材质词只保留750 ml、水杯和银色；卖点合并为一条完整短句。描述压缩为一句。",
            ]:
                version = generate_localized_copy(
                    project_id=project.id,
                    user_id=user.id,
                    market=market,
                    evidence_ids=[source.id],
                    facts_confirmed=True,
                    parent_id=parent_id,
                    feedback=feedback,
                    provider=provider,
                    session=db,
                )
                payload = json.loads(version.content)
                run = db.get(AiRun, payload["ai_run_id"])
                records.append(
                    {
                        "market": market,
                        "version": version.version,
                        "id": version.id,
                        "parent_id": version.parent_id,
                        "feedback": feedback,
                        "model": run.model,
                        "latency_ms": run.latency_ms,
                        "result": payload,
                    }
                )
                parent_id = version.id
                print(f"{market} V{version.version}: schema/reference valid, {run.latency_ms}ms")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    folder = ROOT / "data" / "local_acceptance"
    folder.mkdir(exist_ok=True)
    path = folder / f"localization_{stamp}.json"
    path.write_text(
        json.dumps(
            {"data_type": "synthetic", "human_review": "pending", "records": records},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"报告：{path}")
    print("六次请求完成；语义依据、语言质量和反馈落实仍需人工验收。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
