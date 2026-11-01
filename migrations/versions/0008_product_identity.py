"""Add optional explicit product links and persistent authentication throttles.

No inferred historical backfill. Downgrade removes only the two new tables.
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_product_identity"
down_revision = "0007_project_archive"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "auth_throttles" not in tables:
        op.create_table(
            "auth_throttles",
            sa.Column("email_digest", sa.String(64), primary_key=True),
            sa.Column("failures", sa.Integer(), nullable=False),
            sa.Column("locked_until", sa.DateTime(), nullable=True),
        )
    if "product_entity_links" in tables:
        return
    targets = {
        "artifact": "artifacts", "extraction": "document_extractions",
        "evidence": "evidence", "generation": "generations",
        "review_batch": "review_batches", "finding": "findings",
        "improvement": "improvement_records", "validation": "validation_results",
    }
    columns = [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("business_objects.id"), nullable=False),
        *[sa.Column(key + "_id", sa.Integer(), sa.ForeignKey(table + ".id"),
                    nullable=True, unique=True) for key, table in targets.items()],
        sa.Column("original_generation_id", sa.Integer(), sa.ForeignKey("generations.id")),
        sa.Column("revised_generation_id", sa.Integer(), sa.ForeignKey("generations.id")),
        sa.Column("assigned_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            " + ".join(f"({key}_id IS NOT NULL)" for key in targets) + " = 1",
            name="ck_product_entity_single_target",
        ),
    ]
    op.create_table("product_entity_links", *columns)
    for column in ("project_id", "product_id"):
        op.create_index("ix_product_entity_links_" + column, "product_entity_links", [column])


def downgrade() -> None:
    op.drop_table("product_entity_links")
    op.drop_table("auth_throttles")
