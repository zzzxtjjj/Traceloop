"""Add reversible project archive flag."""

import sqlalchemy as sa
from alembic import op

revision = "0007_project_archive"
down_revision = "0006_production_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("projects")}
    if "archived" not in columns:
        op.add_column(
            "projects",
            sa.Column("archived", sa.Boolean(), nullable=True, server_default=sa.text("0")),
        )
    op.execute("UPDATE projects SET archived = 0 WHERE archived IS NULL")
    indexes = {item["name"] for item in inspector.get_indexes("projects")}
    if "ix_projects_archived" not in indexes:
        op.create_index("ix_projects_archived", "projects", ["archived"])


def downgrade() -> None:
    raise RuntimeError("Project archive history is not automatically removed.")
