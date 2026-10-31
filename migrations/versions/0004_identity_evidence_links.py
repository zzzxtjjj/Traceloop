"""Add authenticated submitter and direct requirement evidence references."""

import sqlalchemy as sa
from alembic import op

revision = "0004_identity_evidence_links"
down_revision = "0003_backend_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def add_column_if_missing(table: str, column: sa.Column) -> None:
        if column.name not in {item["name"] for item in inspector.get_columns(table)}:
            op.add_column(table, column)

    add_column_if_missing(
        "task_submissions", sa.Column("submitted_by_user_id", sa.Integer(), nullable=True)
    )
    add_column_if_missing(
        "extracted_requirements", sa.Column("source_evidence_id", sa.Integer(), nullable=True)
    )

    for name, table, columns in (
        ("ix_task_submissions_submitted_by_user_id", "task_submissions", ["submitted_by_user_id"]),
        (
            "ix_extracted_requirements_source_evidence_id",
            "extracted_requirements",
            ["source_evidence_id"],
        ),
    ):
        existing = {item["name"] for item in inspector.get_indexes(table)}
        if name not in existing:
            op.create_index(name, table, columns)


def downgrade() -> None:
    raise RuntimeError(
        "TradeLoop migrations do not automatically delete identity/evidence history."
    )
