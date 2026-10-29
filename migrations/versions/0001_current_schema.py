"""Create the current TradeLoop schema without removing legacy data."""

from alembic import op

from core.models import Base

revision = "0001_current_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # create_all is intentional for the baseline revision: it creates only missing
    # tables and indexes, preserving first-stage projects, artifacts and quotes.
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    raise RuntimeError(
        "TradeLoop migrations do not automatically delete tables. Restore a backup "
        "if an older schema is required."
    )
