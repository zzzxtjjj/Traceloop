"""Add email verification and first-login password controls."""

import sqlalchemy as sa
from alembic import op

revision = "0006_production_identity"
down_revision = "0005_daily_report_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("users")}
    additions = (
        ("email_verified", sa.Boolean(), True),
        ("force_password_change", sa.Boolean(), False),
        ("email_verification_expires_at", sa.DateTime(), None),
        ("email_verification_code_hash", sa.String(length=128), None),
        ("email_verification_attempts", sa.Integer(), 0),
        ("email_verification_sent_at", sa.DateTime(), None),
    )
    for name, column_type, default in additions:
        if name not in columns:
            server_default = (
                sa.text("1") if default is True else sa.text("0") if default is False else None
            )
            op.add_column(
                "users",
                sa.Column(name, column_type, nullable=True, server_default=server_default),
            )
    op.execute("UPDATE users SET email_verified = 1 WHERE email_verified IS NULL")
    op.execute("UPDATE users SET force_password_change = 0 WHERE force_password_change IS NULL")
    op.execute(
        "UPDATE users SET email_verification_attempts = 0 "
        "WHERE email_verification_attempts IS NULL"
    )


def downgrade() -> None:
    raise RuntimeError("Identity migration is non-destructive and is not automatically downgraded.")
