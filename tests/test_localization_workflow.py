import pytest
from sqlalchemy import func, select

from core.errors import CrossProjectReferenceError
from core.models import Generation, Project
from services.localization_service import (
    MANUAL_PROMPT_VERSION,
    create_v1_generation,
    create_v2_generation,
    list_generations,
)


def _project(db_session, name: str, markets: str = '["US", "DE"]') -> Project:
    project = Project(
        name=name,
        product_name="Insulated Bottle",
        access_code_hash="test",
        markets_json=markets,
    )
    db_session.add(project)
    db_session.flush()
    return project


@pytest.mark.parametrize(
    ("market", "language"),
    [("US", "en-US"), ("DE", "de-DE")],
)
def test_create_v1_for_supported_markets(db_session, market, language) -> None:
    project = _project(db_session, f"Project-{market}")

    generation = create_v1_generation(
        project_id=project.id,
        market=market,
        content="  Initial market content.  ",
        session=db_session,
    )

    assert generation.version == 1
    assert generation.parent_id is None
    assert generation.language == language
    assert generation.content == "Initial market content."
    assert generation.feedback == ""
    assert generation.prompt_version == MANUAL_PROMPT_VERSION


def test_v2_preserves_feedback_and_points_to_v1(db_session) -> None:
    project = _project(db_session, "Version Chain")
    v1 = create_v1_generation(
        project_id=project.id,
        market="US",
        content="Bottle for daily use.",
        session=db_session,
    )

    v2 = create_v2_generation(
        project_id=project.id,
        parent_id=v1.id,
        feedback="Use a more specific capacity claim.",
        content="750 ml bottle for daily use.",
        session=db_session,
    )

    assert v2.version == 2
    assert v2.parent_id == v1.id
    assert v2.feedback == "Use a more specific capacity claim."
    assert v2.market == v1.market
    assert v2.language == v1.language
    assert [item.id for item in list_generations(project.id, session=db_session)] == [
        v1.id,
        v2.id,
    ]


def test_invalid_input_does_not_create_empty_versions(db_session) -> None:
    project = _project(db_session, "No Empty Versions")

    with pytest.raises(ValueError, match="V1 内容不能为空"):
        create_v1_generation(
            project_id=project.id,
            market="US",
            content="   ",
            session=db_session,
        )
    assert db_session.scalar(select(func.count(Generation.id))) == 0

    v1 = create_v1_generation(
        project_id=project.id,
        market="US",
        content="Valid V1",
        session=db_session,
    )
    with pytest.raises(ValueError, match="修改反馈不能为空"):
        create_v2_generation(
            project_id=project.id,
            parent_id=v1.id,
            feedback=" ",
            content="Valid V2",
            session=db_session,
        )
    with pytest.raises(ValueError, match="V2 内容不能为空"):
        create_v2_generation(
            project_id=project.id,
            parent_id=v1.id,
            feedback="Valid feedback",
            content=" ",
            session=db_session,
        )
    assert db_session.scalar(select(func.count(Generation.id))) == 1


def test_generation_cannot_cross_project_or_disabled_market(db_session) -> None:
    first = _project(db_session, "First", '["US"]')
    second = _project(db_session, "Second", '["US"]')
    v1 = create_v1_generation(
        project_id=first.id,
        market="US",
        content="First project content",
        session=db_session,
    )

    with pytest.raises(ValueError, match="未启用"):
        create_v1_generation(
            project_id=first.id,
            market="DE",
            content="German content",
            session=db_session,
        )
    with pytest.raises(CrossProjectReferenceError):
        create_v2_generation(
            project_id=second.id,
            parent_id=v1.id,
            feedback="Change",
            content="Second project content",
            session=db_session,
        )


def test_v1_allows_only_one_v2_child(db_session) -> None:
    project = _project(db_session, "Single V2")
    v1 = create_v1_generation(
        project_id=project.id,
        market="DE",
        content="Erste Version",
        session=db_session,
    )
    create_v2_generation(
        project_id=project.id,
        parent_id=v1.id,
        feedback="Präziser formulieren",
        content="Zweite präzisere Version",
        session=db_session,
    )

    with pytest.raises(ValueError, match="existiert|存在"):
        create_v2_generation(
            project_id=project.id,
            parent_id=v1.id,
            feedback="Noch einmal",
            content="Dritte Version",
            session=db_session,
        )
