from datetime import date

import pytest

from core.errors import InvalidStateTransitionError
from core.schemas import ProjectCreate
from services.auth_service import create_session
from services.membership_service import add_project_member, create_user
from services.project_service import create_project
from services.task_service import create_manual_task, list_tasks


def test_owner_can_create_assigned_manual_task_and_member_cannot(db_session):
    owner = create_user("负责人", "task-owner@example.test", session=db_session)
    member = create_user("执行人", "task-member@example.test", session=db_session)
    owner_token = create_session(owner.id, session=db_session)
    member_token = create_session(member.id, session=db_session)
    project = create_project(
        ProjectCreate(
            name="Task project", product_name="Product", access_code="secure-1", markets=["DE"]
        ),
        owner_user_id=owner.id, session=db_session,
    )
    add_project_member(project.id, owner.id, member.id, "procurement", session=db_session)
    task = create_manual_task(
        project_id=project.id, session_token=owner_token, title="报价复核",
        description="核对供应商报价", assignee_user_id=member.id, priority="high",
        due_date=date.today(), acceptance_criteria=["提交复核表"], session=db_session,
    )
    assert task.source_type == "manual"
    assert task.assignee_user_id == member.id
    assert task.status == "todo"
    with pytest.raises(InvalidStateTransitionError):
        create_manual_task(
            project_id=project.id, session_token=member_token, title="越权任务",
            description="", assignee_user_id=member.id, priority="medium",
            due_date=date.today(), acceptance_criteria=["x"], session=db_session,
        )
    assert len(list_tasks(project.id, session=db_session)) == 1
