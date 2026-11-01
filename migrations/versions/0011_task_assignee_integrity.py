"""Ensure task assignee foreign key and index on partially upgraded databases."""

import sqlalchemy as sa
from alembic import op

revision = "0011_task_assignee_integrity"
down_revision = "0010_flexible_review_fields"
branch_labels = None
depends_on = None


def _has_assignee_foreign_key(bind) -> bool:
    if bind.dialect.name == "sqlite":
        rows = bind.exec_driver_sql("PRAGMA foreign_key_list('tasks')").fetchall()
        return any(
            row[2] == "users" and row[3] == "assignee_user_id" and row[4] == "id"
            for row in rows
        )
    return any(
        item.get("constrained_columns") == ["assignee_user_id"]
        and item.get("referred_table") == "users"
        and item.get("referred_columns") == ["id"]
        for item in sa.inspect(bind).get_foreign_keys("tasks")
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns("tasks")}
    if "assignee_user_id" not in columns:
        return
    if not _has_assignee_foreign_key(bind):
        with op.batch_alter_table("tasks") as batch:
            batch.create_foreign_key(
                "fk_tasks_assignee_user", "users", ["assignee_user_id"], ["id"]
            )
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("tasks")}
    if "ix_tasks_assignee_user_id" not in indexes:
        op.create_index("ix_tasks_assignee_user_id", "tasks", ["assignee_user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns("tasks")}
    if "assignee_user_id" not in columns:
        return
    indexes = {item["name"] for item in inspector.get_indexes("tasks")}
    if "ix_tasks_assignee_user_id" in indexes:
        op.drop_index("ix_tasks_assignee_user_id", table_name="tasks")
    if _has_assignee_foreign_key(bind):
        with op.batch_alter_table("tasks") as batch:
            batch.drop_constraint("fk_tasks_assignee_user", type_="foreignkey")
