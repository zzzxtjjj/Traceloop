import json

import pytest
from sqlalchemy import select

from core.errors import ProjectAccessDeniedError
from core.models import Evidence, ExtractedRequirement, Project, ProjectMember
from core.schemas import DocumentAnalysisRequest
from services.auth_service import (
    authenticate,
    create_session,
    resolve_session,
    revoke_session,
    set_password,
)
from services.channel_service import list_messages, send_message
from services.document_analysis_service import analyze_project_documents
from services.document_parser import parse_bytes
from services.file_service import download_project_file, upload_project_file
from services.membership_service import create_user
from services.task_service import (
    create_task_from_requirement,
    get_project_review_snapshot,
    publish_task,
    review_task_submission_as_user,
    submit_daily_report_as_user,
    submit_task_delivery_as_user,
)


def _project_with_members(session):
    owner = create_user("Owner", "owner@example.com", session=session)
    member = create_user("Member", "member@example.com", session=session)
    other = create_user("Other", "other@example.com", session=session)
    project = Project(
        name="Backend foundation",
        product_name="Heater",
        access_code_hash="test",
        markets_json='["US"]',
    )
    session.add(project)
    session.flush()
    session.add_all(
        [
            ProjectMember(project_id=project.id, user_id=owner.id, role="owner"),
            ProjectMember(project_id=project.id, user_id=member.id, role="member"),
        ]
    )
    session.flush()
    return project, owner, member, other


def test_password_session_expiry_and_revoke(db_session) -> None:
    user = create_user("Login User", "login@example.com", session=db_session)
    set_password(user.id, "correct horse", session=db_session)

    assert authenticate("LOGIN@example.com", "correct horse", session=db_session).id == user.id
    with pytest.raises(ProjectAccessDeniedError):
        authenticate("login@example.com", "wrong password", session=db_session)

    token = create_session(user.id, session=db_session)
    assert resolve_session(token, session=db_session).id == user.id
    revoke_session(token, session=db_session)
    with pytest.raises(ProjectAccessDeniedError):
        resolve_session(token, session=db_session)


def test_channel_messages_are_project_scoped_and_idempotent(db_session) -> None:
    project, owner, member, other = _project_with_members(db_session)
    owner_token = create_session(owner.id, session=db_session)
    member_token = create_session(member.id, session=db_session)
    other_token = create_session(other.id, session=db_session)
    first = send_message(
        project_id=project.id,
        session_token=owner_token,
        content="same message",
        client_request_id="req-1",
        session=db_session,
    )
    duplicate = send_message(
        project_id=project.id,
        session_token=owner_token,
        content="same message",
        client_request_id="req-1",
        session=db_session,
    )
    assert duplicate.id == first.id
    assert (
        len(list_messages(project_id=project.id, session_token=member_token, session=db_session))
        == 1
    )
    with pytest.raises(ProjectAccessDeniedError):
        list_messages(project_id=project.id, session_token=other_token, session=db_session)


def test_file_storage_rejects_cross_project_access_and_preserves_hash(db_session, tmp_path) -> None:
    project, owner, member, other = _project_with_members(db_session)
    owner_token = create_session(owner.id, session=db_session)
    member_token = create_session(member.id, session=db_session)
    other_token = create_session(other.id, session=db_session)
    artifact = upload_project_file(
        project_id=project.id,
        session_token=owner_token,
        source=b"review_id,review_text\nR-1,box damaged\n",
        filename="reviews.csv",
        session=db_session,
        upload_root=tmp_path,
    )
    name, raw, mime = download_project_file(
        project_id=project.id,
        session_token=member_token,
        artifact_id=artifact.id,
        session=db_session,
        upload_root=tmp_path,
    )
    assert name == "reviews.csv"
    assert raw.startswith(b"review_id")
    assert mime == "text/csv"
    with pytest.raises(ProjectAccessDeniedError):
        download_project_file(
            project_id=project.id,
            session_token=other_token,
            artifact_id=artifact.id,
            session=db_session,
            upload_root=tmp_path,
        )
    with pytest.raises(ValueError, match="UNSUPPORTED_FILE_TYPE"):
        upload_project_file(
            project_id=project.id,
            session_token=owner_token,
            source=b"binary",
            filename="payload.exe",
            session=db_session,
            upload_root=tmp_path,
        )


def test_csv_and_txt_parsers_keep_source_locations_and_unsupported_state() -> None:
    csv_result = parse_bytes(b"sku,quantity\nH-1,4\n", ".csv")
    assert csv_result.status == "succeeded"
    assert csv_result.locator["columns"] == ["sku", "quantity"]
    rows = json.loads(csv_result.text_excerpt)
    assert rows[0]["row_number"] == 2

    txt_result = parse_bytes(b"first\nsecond", ".txt")
    assert txt_result.status == "succeeded"
    assert "1: first" in txt_result.text_excerpt
    assert "2: second" in txt_result.text_excerpt

    unsupported = parse_bytes(b"%PDF", ".pdf")
    assert unsupported.status == "unsupported"
    assert unsupported.error_code == "UNSUPPORTED_FILE_TYPE"


def test_document_analysis_persists_only_draft_requirements_with_real_sources(
    db_session, tmp_path
) -> None:
    project, owner, _member, _other = _project_with_members(db_session)
    owner_token = create_session(owner.id, session=db_session)
    artifact = upload_project_file(
        project_id=project.id,
        session_token=owner_token,
        source=b"sku,requirement\nH-1,Keep temperature below 40C\n",
        filename="spec.csv",
        session=db_session,
        upload_root=tmp_path,
    )
    from services.document_parser import extract_artifact

    extract_artifact(
        project_id=project.id,
        session_token=owner_token,
        artifact_id=artifact.id,
        session=db_session,
        upload_root=tmp_path,
    )
    request = {
        "project_id": project.id,
        "artifact_ids": [artifact.id],
        "target_market": "US",
        "analysis_type": "product_requirements",
    }
    result = analyze_project_documents(
        session_token=owner_token,
        request=DocumentAnalysisRequest.model_validate(request),
        analyzer=lambda **_kwargs: {
            "status": "success",
            "summary": "one requirement",
            "requirements": [
                {
                    "title": "Temperature limit",
                    "description": "Keep temperature below 40C.",
                    "target_role": "engineering",
                    "priority": "high",
                    "source": {
                        "artifact_id": artifact.id,
                        "locator": {"row": 2, "column": "requirement"},
                        "excerpt": "Keep temperature below 40C",
                    },
                    "status": "draft",
                }
            ],
        },
        session=db_session,
    )
    assert result.status == "success"
    stored = db_session.scalar(select(ExtractedRequirement))
    assert stored.review_status == "draft"
    assert json.loads(stored.source_locator_json)["row"] == 2


def test_requirement_task_publish_and_review_require_persisted_roles(db_session) -> None:
    project, owner, member, _other = _project_with_members(db_session)
    owner_token = create_session(owner.id, session=db_session)
    member_token = create_session(member.id, session=db_session)
    evidence = Evidence(
        project_id=project.id,
        evidence_type="document_requirement_source",
        source_entity_type="document_extraction",
        source_entity_id=1,
        locator_json='{"row":2}',
        excerpt="Keep temperature below 40C",
        content_hash="content-1",
        dedupe_key="dedupe-1",
    )
    db_session.add(evidence)
    db_session.flush()
    requirement = ExtractedRequirement(
        project_id=project.id,
        artifact_id=1,
        extraction_id=1,
        statement="Temperature limit\nKeep temperature below 40C.",
        owner_role="member",
        acceptance_criteria_json='["verify the requirement"]',
        source_locator_json='{"row":2}',
        source_excerpt="Keep temperature below 40C",
        source_evidence_id=evidence.id,
        review_status="draft",
    )
    db_session.add(requirement)
    db_session.flush()

    task = create_task_from_requirement(
        project_id=project.id,
        requirement_id=requirement.id,
        session_token=member_token,
        session=db_session,
    )
    assert task.status == "draft"
    with pytest.raises(Exception, match="不能发布"):
        publish_task(
            project_id=project.id,
            task_id=task.id,
            session_token=member_token,
            session=db_session,
        )
    publish_task(
        project_id=project.id,
        task_id=task.id,
        session_token=owner_token,
        session=db_session,
    )
    submission = submit_task_delivery_as_user(
        project_id=project.id,
        task_id=task.id,
        session_token=member_token,
        content="已完成温控检查。",
        evidence_excerpt="测试记录 TC-1。",
        session=db_session,
    )
    with pytest.raises(Exception, match="当前角色不能执行人工验收"):
        review_task_submission_as_user(
            project_id=project.id,
            submission_id=submission.id,
            session_token=member_token,
            decision="accepted",
            note="",
            session=db_session,
        )
    review_task_submission_as_user(
        project_id=project.id,
        submission_id=submission.id,
        session_token=owner_token,
        decision="accepted",
        note="已核验测试记录。",
        session=db_session,
    )
    assert task.status == "completed"


def test_project_review_snapshot_is_member_scoped_and_tracks_daily_report(db_session) -> None:
    project, owner, member, other = _project_with_members(db_session)
    owner_token = create_session(owner.id, session=db_session)
    member_token = create_session(member.id, session=db_session)
    other_token = create_session(other.id, session=db_session)
    submit_daily_report_as_user(
        project_id=project.id,
        task_id=None,
        session_token=member_token,
        completed="已核对供应商材料。",
        blocker="等待质量照片。",
        session=db_session,
    )
    snapshot = get_project_review_snapshot(
        project_id=project.id,
        session_token=owner_token,
        session=db_session,
    )
    assert snapshot.project_id == project.id
    assert snapshot.report_count == 1
    assert snapshot.blocker_report_count == 1
    assert any(item.risk_type == "reported_blocker" for item in snapshot.risks)
    with pytest.raises(ProjectAccessDeniedError):
        get_project_review_snapshot(
            project_id=project.id,
            session_token=other_token,
            session=db_session,
        )
