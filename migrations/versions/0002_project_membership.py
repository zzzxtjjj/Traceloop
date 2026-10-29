"""Add persistent users and project memberships without rebuilding existing tables."""

from alembic import op

from core.models import ProjectMember, User

revision = "0002_project_membership"
down_revision = "0001_current_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # The baseline revision intentionally uses the current dynamic metadata. On a
    # fresh database it may already create these tables; checkfirst also supports
    # databases that were stamped at 0001 before membership existed.
    User.__table__.create(bind=bind, checkfirst=True)
    ProjectMember.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    raise RuntimeError(
        "TradeLoop migrations do not automatically delete membership data. "
        "Restore a backup if an older schema is required."
    )
