import json

import pytest
from sqlalchemy import select

from core.errors import ModelOutputValidationError, ProjectAccessDeniedError
from core.models import AiRun, Evidence, Generation, Project, ProjectMember, User
from services.localization_ai_service import generate_localized_copy
from services.localization_workflow import (
    check_generation,
    get_generation_chain,
    review_generation,
)


class Provider:
    model_name = "offline-localization"

    def __init__(self, evidence_id):
        self.evidence_id = evidence_id
        self.prompts = []

    def generate(self, *, prompt, schema, repair_from=None):
        self.prompts.append(prompt)
        claim = {
            "text": f"Bottle 750 ml revision {len(self.prompts)}",
            "evidence_ids": [self.evidence_id],
        }
        return {
            "title": claim,
            "bullets": [claim],
            "description": claim,
            "missing_information": [],
            "review_notes": ["请人工核对语言与事实"],
        }


def setup(db):
    project = Project(
        name="Localization",
        product_name="Bottle",
        access_code_hash="test",
        markets_json='["US", "DE"]',
    )
    user = User(display_name="Owner", email="owner@test.local")
    db.add_all([project, user])
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))
    evidence = Evidence(
        project_id=project.id,
        evidence_type="product_spec",
        source_entity_type="project",
        source_entity_id=project.id,
        excerpt="商品：水杯；容量750毫升",
        content_hash="a",
        dedupe_key="a",
    )
    db.add(evidence)
    db.flush()
    return dict(
        project_id=project.id,
        user_id=user.id,
        evidence_ids=[evidence.id],
        facts_confirmed=True,
        session=db,
    ), evidence


@pytest.mark.parametrize("market", ["US", "DE"])
def test_two_feedback_rounds_preserve_versions_and_history(db_session, market):
    args, evidence = setup(db_session)
    provider = Provider(evidence.id)
    v1 = generate_localized_copy(**args, market=market, provider=provider)
    v2 = generate_localized_copy(
        **args, market=market, provider=provider, parent_id=v1.id, feedback="突出容量"
    )
    v3 = generate_localized_copy(
        **args, market=market, provider=provider, parent_id=v2.id, feedback="精简标题"
    )
    assert [v1.version, v2.version, v3.version] == [1, 2, 3]
    assert v3.parent_id == v2.id and v2.parent_id == v1.id
    assert v2.feedback == "突出容量" and v3.feedback == "精简标题"
    assert "突出容量" in provider.prompts[-1] and "精简标题" in provider.prompts[-1]
    envelope = json.loads(v3.content)
    assert db_session.get(AiRun, envelope["ai_run_id"]).status == "success"
    with pytest.raises(ValueError, match="已有后续版本"):
        generate_localized_copy(
            **args, market=market, provider=provider, parent_id=v1.id, feedback="重复"
        )
    assert len(provider.prompts) == 3


def test_invalid_reference_saves_failure_without_version(db_session):
    args, evidence = setup(db_session)
    with pytest.raises(ModelOutputValidationError):
        generate_localized_copy(**args, market="US", provider=Provider(evidence.id + 999))
    assert db_session.scalar(select(Generation)) is None
    assert db_session.scalar(select(AiRun)).error_code == "MODEL_EVIDENCE_INVALID"


def test_nonmember_and_unconfirmed_facts_do_not_call_model(db_session):
    args, evidence = setup(db_session)
    provider = Provider(evidence.id)
    args["facts_confirmed"] = False
    with pytest.raises(ValueError):
        generate_localized_copy(**args, market="US", provider=provider)
    args["user_id"] = 999
    with pytest.raises(ProjectAccessDeniedError):
        generate_localized_copy(**args, market="US", provider=provider)
    assert not provider.prompts


def test_revision_that_only_changes_notes_is_rejected(db_session):
    args, evidence = setup(db_session)
    provider = Provider(evidence.id)
    v1 = generate_localized_copy(**args, market="US", provider=provider)
    provider.prompts.clear()
    with pytest.raises(ModelOutputValidationError, match="正文没有"):
        generate_localized_copy(
            **args, market="US", provider=provider, parent_id=v1.id, feedback="请修改"
        )
    assert len(list(db_session.scalars(select(Generation)))) == 1
    assert db_session.scalars(select(AiRun).order_by(AiRun.id.desc())).first().status == "failed"


def test_generated_versions_have_rule_snapshots_and_two_check_types(db_session):
    args, evidence = setup(db_session)
    provider = Provider(evidence.id)
    v1 = generate_localized_copy(**args, market="US", provider=provider)
    contract = check_generation(
        project_id=args["project_id"],
        user_id=args["user_id"],
        generation_id=v1.id,
        scenario="procurement",
        text="FOB Ningbo; payment 30/70; quote valid until 2026-11-30.",
        session=db_session,
    )
    assert contract["results"][0]["rule_type"] == "internal_standard"
    assert contract["target"] == "attached_terms"
    assert contract["text"].startswith("FOB")
    v2 = generate_localized_copy(
        **args, market="US", provider=provider, parent_id=v1.id, feedback="修改标题"
    )
    chain = get_generation_chain(
        project_id=args["project_id"],
        user_id=args["user_id"],
        generation_id=v2.id,
        session=db_session,
    )
    assert [item["version"] for item in chain] == [1, 2]
    assert chain[0]["checks"][0]["text"] == "Bottle 750 ml revision 1"
    assert chain[1]["checks"][0]["text"] == "Bottle 750 ml revision 2"
    assert chain[1]["diff"]
    assert "previous_rule_checks" in provider.prompts[-1]
    assert "internal_standard" in provider.prompts[-1]


def test_review_is_version_specific_and_not_inherited(db_session):
    args, evidence = setup(db_session)
    provider = Provider(evidence.id)
    v1 = generate_localized_copy(**args, market="US", provider=provider)
    query = dict(project_id=args["project_id"], user_id=args["user_id"], session=db_session)
    review_generation(**query, generation_id=v1.id, decision="accepted", note="已核对规格")
    v2 = generate_localized_copy(
        **args, market="US", provider=provider, parent_id=v1.id, feedback="修改"
    )
    chain = get_generation_chain(**query, generation_id=v2.id)
    assert chain[0]["review_status"] == "accepted"
    assert chain[1]["review_status"] == "pending_review"


def test_unavailable_rules_keep_version_but_block_acceptance(db_session, monkeypatch):
    import services.localization_workflow as workflow
    from core.errors import RuleSourceError

    def unavailable(**kwargs):
        raise RuleSourceError("private path must not be exposed")

    monkeypatch.setattr(workflow, "run_rule_checks", unavailable)
    args, evidence = setup(db_session)
    v1 = generate_localized_copy(**args, market="US", provider=Provider(evidence.id))
    query = dict(project_id=args["project_id"], user_id=args["user_id"], session=db_session)
    chain = get_generation_chain(**query, generation_id=v1.id)
    assert "private path" not in str(chain[0]["checks"])
    assert chain[0]["checks"][0]["error"]
    with pytest.raises(ValueError, match="规则检查不可用"):
        review_generation(**query, generation_id=v1.id, decision="accepted", note="核对")


def test_query_and_checks_reject_nonmember_before_reading_content(db_session):
    args, evidence = setup(db_session)
    v1 = generate_localized_copy(**args, market="US", provider=Provider(evidence.id))
    for function in [get_generation_chain, check_generation]:
        with pytest.raises(ProjectAccessDeniedError):
            function(
                project_id=args["project_id"], user_id=999, generation_id=v1.id, session=db_session
            )


def test_promotion_risk_blocks_acceptance(db_session):
    args, evidence = setup(db_session)
    v1 = generate_localized_copy(**args, market="US", provider=Provider(evidence.id))
    envelope = json.loads(v1.content)
    envelope["output"]["title"]["text"] = "Free shipping bottle"
    v1.content = json.dumps(envelope)
    with pytest.raises(ValueError, match="未解决风险"):
        review_generation(
            project_id=args["project_id"],
            user_id=args["user_id"],
            generation_id=v1.id,
            decision="accepted",
            note="已检查",
            session=db_session,
        )


@pytest.mark.parametrize("failure_kind", ["timeout", "json"])
def test_model_failure_keeps_failed_run_and_no_success_version(db_session, failure_kind):
    from core.errors import TradeLoopError

    class BrokenProvider:
        model_name = "offline-broken"

        def generate(self, **kwargs):
            if failure_kind == "timeout":
                raise TimeoutError()
            return "not JSON"

    args, _ = setup(db_session)
    with pytest.raises(TradeLoopError):
        generate_localized_copy(**args, market="US", provider=BrokenProvider())
    db_session.commit()
    assert db_session.scalar(select(Generation)) is None
    assert db_session.scalar(select(AiRun)).status == "failed"


def test_listing_is_project_scoped(db_session):
    from services.localization_workflow import list_project_localizations

    args, evidence = setup(db_session)
    version = generate_localized_copy(**args, market="DE", provider=Provider(evidence.id))
    result = list_project_localizations(
        project_id=args["project_id"], user_id=args["user_id"], session=db_session
    )
    assert [item["id"] for item in result] == [version.id]
    with pytest.raises(ProjectAccessDeniedError):
        list_project_localizations(project_id=args["project_id"], user_id=999, session=db_session)
