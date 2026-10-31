"""Add authenticated submitter identity to daily reports."""

import sqlalchemy as sa
from alembic import op

revision = "0005_daily_report_identity"
down_revision = "0004_identity_evidence_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns("daily_reports")}
    if "submitted_by_user_id" not in columns:
        op.add_column(
            "daily_reports",
            sa.Column("submitted_by_user_id", sa.Integer(), nullable=True),
        )
    indexes = {item["name"] for item in inspector.get_indexes("daily_reports")}
    if "ix_daily_reports_submitted_by_user_id" not in indexes:
        op.create_index(
            "ix_daily_reports_submitted_by_user_id",
            "daily_reports",
            ["submitted_by_user_id"],
        )


def downgrade() -> None:
    raise RuntimeError(
        "TradeLoop migrations do not automatically delete daily-report identity history."
    )
