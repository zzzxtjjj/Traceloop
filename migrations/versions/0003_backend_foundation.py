"""Add backend foundation tables and non-destructive artifact/auth fields."""

import sqlalchemy as sa
from alembic import op

from core.models import Base

revision = "0003_backend_foundation"
down_revision = "0002_project_membership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # A legacy database stamped at 0001 may contain only a subset of the
    # baseline tables. Create missing tables additively before altering columns.
    Base.metadata.create_all(bind=bind)
    inspector = sa.inspect(bind)

    def add_column_if_missing(table: str, column: sa.Column) -> None:
        if column.name not in {item["name"] for item in inspector.get_columns(table)}:
            op.add_column(table, column)

    add_column_if_missing(
        "users", sa.Column("password_hash", sa.String(length=256), nullable=True)
    )
    add_column_if_missing(
        "ai_runs",
        sa.Column("provider", sa.String(length=80), nullable=False, server_default="unknown"),
    )
    add_column_if_missing(
        "ai_runs",
        sa.Column("schema_version", sa.String(length=40), nullable=False, server_default="v1"),
    )
    add_column_if_missing(
        "task_submissions", sa.Column("submitted_by_user_id", sa.Integer(), nullable=True)
    )
    add_column_if_missing(
        "extracted_requirements", sa.Column("source_evidence_id", sa.Integer(), nullable=True)
    )
    for column in (
        sa.Column("uploader_id", sa.Integer(), nullable=True),
        sa.Column(
            "mime_type",
            sa.String(length=120),
            nullable=False,
            server_default="application/octet-stream",
        ),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=True),
        sa.Column("file_hash", sa.String(length=64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parent_artifact_id", sa.Integer(), nullable=True),
        sa.Column("parsing_status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("storage_location", sa.Text(), nullable=False, server_default=""),
    ):
        add_column_if_missing("artifacts", column)
    existing_indexes = {item["name"] for item in inspector.get_indexes("artifacts")}
    for name, columns in (
        ("ix_artifacts_uploader_id", ["uploader_id"]),
        ("ix_artifacts_file_hash", ["file_hash"]),
        ("ix_artifacts_parent_artifact_id", ["parent_artifact_id"]),
    ):
        if name not in existing_indexes:
            op.create_index(name, "artifacts", columns)

    if "auth_sessions" not in inspector.get_table_names():
        op.create_table(
            "auth_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("token_hash", name="uq_auth_session_token_hash"),
        )
    existing_indexes = {item["name"] for item in inspector.get_indexes("auth_sessions")}
    for name, columns in (
        ("ix_auth_sessions_user_id", ["user_id"]),
        ("ix_auth_sessions_token_hash", ["token_hash"]),
        ("ix_auth_sessions_expires_at", ["expires_at"]),
    ):
        if name not in existing_indexes:
            op.create_index(name, "auth_sessions", columns)

    if "channel_messages" not in inspector.get_table_names():
        op.create_table(
            "channel_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("message_type", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("reply_to_id", sa.Integer(), nullable=True),
        sa.Column("artifact_id", sa.Integer(), nullable=True),
        sa.Column("client_request_id", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reply_to_id"], ["channel_messages.id"]),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"]),
        sa.UniqueConstraint(
            "project_id",
            "sender_id",
            "client_request_id",
            name="uq_channel_message_request",
        ),
        )
    existing_indexes = {item["name"] for item in inspector.get_indexes("channel_messages")}
    for name, columns in (
        ("ix_channel_messages_project_id", ["project_id"]),
        ("ix_channel_messages_sender_id", ["sender_id"]),
        ("ix_channel_messages_artifact_id", ["artifact_id"]),
        ("ix_channel_messages_created_at", ["created_at", "id"]),
    ):
        if name not in existing_indexes:
            op.create_index(name, "channel_messages", columns)

    if "document_extractions" not in inspector.get_table_names():
        op.create_table(
            "document_extractions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("artifact_id", sa.Integer(), nullable=False),
        sa.Column("parser_name", sa.String(length=80), nullable=False),
        sa.Column("parser_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("text_excerpt", sa.Text(), nullable=False),
        sa.Column("locator_json", sa.Text(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"]),
        )
    existing_indexes = {item["name"] for item in inspector.get_indexes("document_extractions")}
    for name, columns in (
        ("ix_document_extractions_project_id", ["project_id"]),
        ("ix_document_extractions_artifact_id", ["artifact_id"]),
        ("ix_document_extractions_status", ["status"]),
        ("ix_document_extractions_content_hash", ["content_hash"]),
    ):
        if name not in existing_indexes:
            op.create_index(name, "document_extractions", columns)

    if "extracted_requirements" not in inspector.get_table_names():
        op.create_table(
            "extracted_requirements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("artifact_id", sa.Integer(), nullable=False),
        sa.Column("extraction_id", sa.Integer(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("requirement_type", sa.String(length=80), nullable=False),
        sa.Column("owner_role", sa.String(length=40), nullable=False),
        sa.Column("acceptance_criteria_json", sa.Text(), nullable=False),
        sa.Column("source_locator_json", sa.Text(), nullable=False),
        sa.Column("source_excerpt", sa.Text(), nullable=False),
        sa.Column("epistemic_status", sa.String(length=30), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("ai_run_id", sa.Integer(), nullable=True),
        sa.Column("review_status", sa.String(length=30), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"]),
        sa.ForeignKeyConstraint(["extraction_id"], ["document_extractions.id"]),
        sa.ForeignKeyConstraint(["ai_run_id"], ["ai_runs.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        )
    existing_indexes = {item["name"] for item in inspector.get_indexes("extracted_requirements")}
    for name, columns in (
        ("ix_extracted_requirements_project_id", ["project_id"]),
        ("ix_extracted_requirements_artifact_id", ["artifact_id"]),
        ("ix_extracted_requirements_extraction_id", ["extraction_id"]),
        ("ix_extracted_requirements_review_status", ["review_status"]),
        ("ix_extracted_requirements_ai_run_id", ["ai_run_id"]),
        ("ix_extracted_requirements_task_id", ["task_id"]),
    ):
        if name not in existing_indexes:
            op.create_index(name, "extracted_requirements", columns)


def downgrade() -> None:
    raise RuntimeError(
        "TradeLoop migrations do not automatically delete backend foundation data. "
        "Restore a backup if an older schema is required."
    )
