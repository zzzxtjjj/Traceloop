"""Allow feedback imports to preserve missing source fields as unknown."""

import sqlalchemy as sa
from alembic import op

revision = "0010_flexible_review_fields"
down_revision = "0009_task_management_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("reviews") as batch:
        batch.alter_column("rating", existing_type=sa.Integer(), nullable=True)
        batch.alter_column("sku", existing_type=sa.String(length=100), nullable=True)
        batch.alter_column("review_text", existing_type=sa.Text(), nullable=True)
        batch.add_column(sa.Column("review_date", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("reviews") as batch:
        batch.drop_column("review_date")
        batch.alter_column("review_text", existing_type=sa.Text(), nullable=False)
        batch.alter_column("sku", existing_type=sa.String(length=100), nullable=False)
        batch.alter_column("rating", existing_type=sa.Integer(), nullable=False)
