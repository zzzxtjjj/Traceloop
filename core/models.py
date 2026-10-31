from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    product_name: Mapped[str] = mapped_column(String(160))
    access_code_hash: Mapped[str] = mapped_column(String(256))
    markets_json: Mapped[str] = mapped_column(Text, default='["US", "DE"]')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_member_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(40), index=True)
    batch_name: Mapped[str] = mapped_column(String(120))
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(Text, default="")
    sha256: Mapped[str] = mapped_column(String(64))
    uploader_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    mime_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("artifacts.id"), nullable=True, index=True
    )
    parsing_status: Mapped[str] = mapped_column(String(30), default="pending")
    storage_location: Mapped[str] = mapped_column(Text, default="")
    parse_status: Mapped[str] = mapped_column(String(30), default="valid")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ChannelMessage(Base):
    __tablename__ = "channel_messages"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "sender_id", "client_request_id", name="uq_channel_message_request"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    message_type: Mapped[str] = mapped_column(String(30), default="text")
    content: Mapped[str] = mapped_column(Text)
    reply_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_messages.id"), nullable=True
    )
    artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("artifacts.id"), nullable=True, index=True
    )
    client_request_id: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class DocumentExtraction(Base):
    __tablename__ = "document_extractions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("artifacts.id"), index=True)
    parser_name: Mapped[str] = mapped_column(String(80))
    parser_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    text_excerpt: Mapped[str] = mapped_column(Text, default="")
    locator_json: Mapped[str] = mapped_column(Text, default="{}")
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ExtractedRequirement(Base):
    __tablename__ = "extracted_requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("artifacts.id"), index=True)
    extraction_id: Mapped[int] = mapped_column(ForeignKey("document_extractions.id"), index=True)
    statement: Mapped[str] = mapped_column(Text)
    requirement_type: Mapped[str] = mapped_column(String(80), default="general")
    owner_role: Mapped[str] = mapped_column(String(40), default="member")
    acceptance_criteria_json: Mapped[str] = mapped_column(Text, default="[]")
    source_locator_json: Mapped[str] = mapped_column(Text, default="{}")
    source_excerpt: Mapped[str] = mapped_column(Text, default="")
    source_evidence_id: Mapped[int | None] = mapped_column(
        ForeignKey("evidence.id"), nullable=True, index=True
    )
    epistemic_status: Mapped[str] = mapped_column(String(30), default="unknown")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    ai_run_id: Mapped[int | None] = mapped_column(ForeignKey("ai_runs.id"), nullable=True)
    review_status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class SupplierQuote(Base):
    __tablename__ = "supplier_quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("artifacts.id"), index=True)
    supplier: Mapped[str] = mapped_column(String(160))
    unit_price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8))
    moq: Mapped[int] = mapped_column(Integer)
    lead_time_days: Mapped[int] = mapped_column(Integer)
    payment_terms: Mapped[str] = mapped_column(String(200))
    quality_note: Mapped[str] = mapped_column(Text, default="")


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("artifacts.id"), index=True)
    ai_choice: Mapped[str | None] = mapped_column(String(160), nullable=True)
    human_choice: Mapped[str] = mapped_column(String(160))
    reason: Mapped[str] = mapped_column(Text)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(40), default="manual")
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    owner_role: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    acceptance_criteria_json: Mapped[str] = mapped_column(Text, default="[]")
    dependency: Mapped[str] = mapped_column(Text, default="")
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    submitted_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    role: Mapped[str] = mapped_column(String(30))
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    completed: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text, default="")
    blocker: Mapped[str] = mapped_column(Text, default="")
    next_plan: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ReviewBatch(Base):
    __tablename__ = "review_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    market: Mapped[str] = mapped_column(String(10))
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    prompt_version: Mapped[str] = mapped_column(String(30), default="review_classify_v1")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("review_batches.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(100))
    rating: Mapped[int] = mapped_column(Integer)
    sku: Mapped[str] = mapped_column(String(100))
    review_text: Mapped[str] = mapped_column(Text)


class Insight(Base):
    __tablename__ = "insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("review_batches.id"), index=True)
    theme: Mapped[str] = mapped_column(String(80))
    count: Mapped[int] = mapped_column(Integer)
    share: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    evidence_review_ids_json: Mapped[str] = mapped_column(Text, default="[]")


class Generation(Base):
    __tablename__ = "generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    market: Mapped[str] = mapped_column(String(10))
    language: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("generations.id"), nullable=True)
    feedback: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(String(40), default="market_content_v1")


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    generation_id: Mapped[int] = mapped_column(ForeignKey("generations.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(80))
    quote: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(10))
    explanation: Mapped[str] = mapped_column(Text)
    suggestion: Mapped[str] = mapped_column(Text)


class AiRun(Base):
    __tablename__ = "ai_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    run_type: Mapped[str] = mapped_column(String(50))
    provider: Mapped[str] = mapped_column(String(80), default="unknown")
    model: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(50))
    schema_version: Mapped[str] = mapped_column(String(40), default="v1")
    input_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    actor_role: Mapped[str] = mapped_column(String(30))
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class BusinessObject(Base):
    __tablename__ = "business_objects"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "object_type", "external_key", name="uq_business_object_key"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    object_type: Mapped[str] = mapped_column(String(40), index=True)
    external_key: Mapped[str] = mapped_column(String(160))
    display_name: Mapped[str] = mapped_column(String(200))
    attributes_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("project_id", "dedupe_key", name="uq_evidence_project_dedupe"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(50), index=True)
    source_entity_type: Mapped[str] = mapped_column(String(50), index=True)
    source_entity_id: Mapped[int] = mapped_column(Integer, index=True)
    locator_json: Mapped[str] = mapped_column(Text, default="{}")
    excerpt: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    dedupe_key: Mapped[str] = mapped_column(String(64))
    business_object_id: Mapped[int | None] = mapped_column(
        ForeignKey("business_objects.id"), nullable=True, index=True
    )
    observed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    finding_type: Mapped[str] = mapped_column(String(50), index=True)
    statement: Mapped[str] = mapped_column(Text)
    epistemic_status: Mapped[str] = mapped_column(String(30), index=True)
    review_status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    denominator_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    denominator_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    time_window_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    time_window_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    model_run_id: Mapped[int | None] = mapped_column(ForeignKey("ai_runs.id"), nullable=True)
    missing_info_json: Mapped[str] = mapped_column(Text, default="[]")
    alternative_explanations_json: Mapped[str] = mapped_column(Text, default="[]")
    suggested_actions_json: Mapped[str] = mapped_column(Text, default="[]")
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class EvidenceLink(Base):
    __tablename__ = "evidence_links"
    __table_args__ = (
        UniqueConstraint(
            "evidence_id",
            "target_type",
            "target_id",
            "relation_type",
            name="uq_evidence_link",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(50), index=True)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    relation_type: Mapped[str] = mapped_column(String(40), default="supports")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ReviewImportMetadata(Base):
    __tablename__ = "review_import_metadata"
    __table_args__ = (UniqueConstraint("batch_id", name="uq_review_metadata_batch"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("review_batches.id"), index=True)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("artifacts.id"), index=True)
    source_sha256: Mapped[str] = mapped_column(String(64), index=True)
    time_window_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    time_window_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    taxonomy_version: Mapped[str] = mapped_column(String(40), default="review_themes_v1")
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ReviewThemeAssignment(Base):
    __tablename__ = "review_theme_assignments"
    __table_args__ = (
        UniqueConstraint(
            "review_id", "theme", "taxonomy_version", name="uq_review_theme_assignment"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("review_batches.id"), index=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id"), index=True)
    theme: Mapped[str] = mapped_column(String(80), index=True)
    classification_method: Mapped[str] = mapped_column(String(30), default="rule_based")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    evidence_excerpt: Mapped[str] = mapped_column(Text)
    taxonomy_version: Mapped[str] = mapped_column(String(40), default="review_themes_v1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class TaskSubmission(Base):
    __tablename__ = "task_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    submitted_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    submitted_by_role: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"), index=True)
    review_status: Mapped[str] = mapped_column(String(30), default="pending_review")
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ImprovementRecord(Base):
    __tablename__ = "improvement_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    baseline_batch_id: Mapped[int] = mapped_column(ForeignKey("review_batches.id"), index=True)
    followup_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("review_batches.id"), nullable=True, index=True
    )
    theme: Mapped[str] = mapped_column(String(80), index=True)
    baseline_count: Mapped[int] = mapped_column(Integer)
    baseline_share: Mapped[float] = mapped_column(Float)
    baseline_sample_size: Mapped[int] = mapped_column(Integer)
    followup_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    followup_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    followup_sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    count_delta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    share_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="planned")
    limitation_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class RuleCheckRecord(Base):
    __tablename__ = "rule_check_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(100), index=True)
    market: Mapped[str] = mapped_column(String(10), index=True)
    scenario: Mapped[str] = mapped_column(String(50), index=True)
    source_type: Mapped[str] = mapped_column(String(30))
    source_reference: Mapped[str] = mapped_column(Text)
    source_version: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), index=True)
    matched_text: Mapped[str] = mapped_column(Text, default="")
    explanation: Mapped[str] = mapped_column(Text)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    human_review_status: Mapped[str] = mapped_column(String(30), default="pending_review")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

