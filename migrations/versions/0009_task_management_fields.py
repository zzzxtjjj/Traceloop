"""Add optional fields for manually managed tasks."""

import sqlalchemy as sa
from alembic import op

revision = "0009_task_management_fields"
down_revision = "0008_product_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("tasks")}
    if "description" not in columns:
        op.add_column(
            "tasks", sa.Column("description", sa.Text(), nullable=False, server_default="")
        )
    if "assignee_user_id" not in columns:
        op.add_column("tasks", sa.Column("assignee_user_id", sa.Integer(), nullable=True))
        columns.add("assignee_user_id")
    foreign_keys = {
        item.get("name") for item in sa.inspect(op.get_bind()).get_foreign_keys("tasks")
    }
    if "fk_tasks_assignee_user" not in foreign_keys:
        with op.batch_alter_table("tasks") as batch:
            batch.create_foreign_key(
                "fk_tasks_assignee_user", "users", ["assignee_user_id"], ["id"]
            )
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("tasks")}
    if "ix_tasks_assignee_user_id" not in indexes:
        op.create_index("ix_tasks_assignee_user_id", "tasks", ["assignee_user_id"])
    if "priority" not in columns:
        op.add_column(
            "tasks", sa.Column("priority", sa.String(20), nullable=False, server_default="medium")
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("tasks")}
    if "priority" in columns:
        op.drop_column("tasks", "priority")
    if "assignee_user_id" in columns:
        indexes = {item["name"] for item in inspector.get_indexes("tasks")}
        if "ix_tasks_assignee_user_id" in indexes:
            op.drop_index("ix_tasks_assignee_user_id", table_name="tasks")
        foreign_keys = {item.get("name") for item in inspector.get_foreign_keys("tasks")}
        if "fk_tasks_assignee_user" in foreign_keys:
            with op.batch_alter_table("tasks") as batch:
                batch.drop_constraint("fk_tasks_assignee_user", type_="foreignkey")
        op.drop_column("tasks", "assignee_user_id")
    if "description" in columns:
        op.drop_column("tasks", "description")
