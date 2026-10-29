from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    product_name: str = Field(min_length=2, max_length=160)
    access_code: str = Field(min_length=8, max_length=64)
    markets: list[str] = Field(min_length=1)

    @field_validator("name", "product_name", "access_code")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ProjectView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    product_name: str
    markets: list[str]


class QuoteRow(BaseModel):
    supplier: str = Field(min_length=1, max_length=160)
    unit_price: float = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    moq: int = Field(gt=0)
    lead_time_days: int = Field(gt=0)
    payment_terms: str = Field(min_length=1, max_length=200)
    quality_note: str = Field(default="", max_length=1000)

    @field_validator("supplier", "payment_terms", "quality_note")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return str(value).strip()

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


class RowError(BaseModel):
    row_number: int
    field: str
    message: str


class QuoteImportPreview(BaseModel):
    rows: list[QuoteRow]
    errors: list[RowError]
    filename: str
    sha256: str

    @property
    def is_valid(self) -> bool:
        return bool(self.rows) and not self.errors


class SupplierScore(BaseModel):
    supplier: str
    unit_price: float
    currency: str
    moq: int
    lead_time_days: int
    payment_terms: str
    quality_note: str
    price_score: float
    moq_score: float
    lead_time_score: float
    quality_score: float
    total_score: float
    risk_hits: list[str]


class QuoteRiskAssessment(BaseModel):
    quote_id: int
    supplier: str
    finding_id: int
    evidence_id: int
    risk_level: Literal["green", "yellow", "red", "unknown"]
    risk_reasons: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)


class QuoteAnalysis(BaseModel):
    artifact_id: int
    scores: list[SupplierScore]
    assessments: list[QuoteRiskAssessment]
    comparability_notes: list[str] = Field(default_factory=list)


class DailyRiskItem(BaseModel):
    risk_type: str
    severity: Literal["info", "yellow", "red"]
    task_id: int | None = None
    report_id: int | None = None
    message: str
    evidence_id: int | None = None


class RuleDefinition(BaseModel):
    rule_id: str
    market: Literal["US", "DE", "ALL"]
    scenario: Literal["platform_product", "consumer_contract", "procurement"]
    rule_type: Literal["platform_policy", "legal_information", "internal_standard"]
    content: str
    source_type: Literal["official_url", "internal_file", "unverified"]
    source_url: str = ""
    source_file: str = ""
    source_title: str
    version: str
    source_checked_at: date
    check_type: Literal["forbidden_regex", "max_length", "required_term_groups", "manual"]
    pattern: str = ""
    max_length: int | None = None
    required_term_groups: list[list[str]] = Field(default_factory=list)
    severity: Literal["yellow", "red"]


class RuleEvaluation(BaseModel):
    rule_id: str
    market: str
    scenario: str
    rule_type: str
    status: Literal["passed", "warning", "failed", "not_covered"]
    matched_text: str = ""
    explanation: str
    source_reference: str
    source_version: str
    requires_human_review: bool = True


class EvidenceReference(BaseModel):
    evidence_id: int
    relation: str = "supports"
    excerpt: str = ""


class RuleCheckOutput(BaseModel):
    rule_id: str
    status: Literal["passed", "warning", "failed", "not_covered"]
    matched_text: str = ""
    reason: str


class StructuredAIOutput(BaseModel):
    result_type: str
    conclusion: str
    supporting_evidence: list[EvidenceReference] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    rule_checks: list[RuleCheckOutput] = Field(default_factory=list)
    risk_level: Literal["green", "yellow", "red", "unknown"] = "unknown"
    risk_reasons: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
    requires_human_review: bool = True


class ReviewRow(BaseModel):
    review_id: str = Field(min_length=1, max_length=100)
    batch: str = Field(min_length=1, max_length=120)
    rating: int = Field(ge=1, le=5)
    date: date
    sku: str = Field(min_length=1, max_length=100)
    market: str = Field(min_length=2, max_length=10)
    review_text: str = Field(min_length=2, max_length=5000)
    order_id: str = Field(default="", max_length=120)
    production_batch: str = Field(default="", max_length=120)
    supplier: str = Field(default="", max_length=160)

    @field_validator(
        "review_id",
        "batch",
        "sku",
        "market",
        "review_text",
        "order_id",
        "production_batch",
        "supplier",
    )
    @classmethod
    def normalize_review_text_fields(cls, value: str) -> str:
        return str(value).strip()


class ReviewImportPreview(BaseModel):
    rows: list[ReviewRow]
    errors: list[RowError]
    filename: str
    sha256: str

    @property
    def is_valid(self) -> bool:
        return bool(self.rows) and not self.errors


class ReviewClassification(BaseModel):
    review_id: str
    themes: list[str]
    evidence_excerpt: str
    confidence: float = Field(ge=0, le=1)
    classification_method: Literal["rule_based", "ai"] = "rule_based"
    missing_information: list[str] = Field(default_factory=list)
    alternative_explanations: list[str] = Field(default_factory=list)


class ReviewModelClassification(BaseModel):
    review_id: str = Field(min_length=1, max_length=100)
    themes: list[str] = Field(min_length=1)
    evidence_span: str = Field(min_length=1, max_length=5000)
    confidence: float = Field(ge=0, le=1)
    missing_info: list[str] = Field(default_factory=list)
    alternative_explanations: list[str] = Field(default_factory=list)


class ReviewModelBatchOutput(BaseModel):
    classifications: list[ReviewModelClassification] = Field(min_length=1)


class ReviewAIAnalysisResult(BaseModel):
    ai_run_id: int
    finding_ids: list[int]
    prompt_version: str
    status: Literal["success"] = "success"


class ReviewThemeSummary(BaseModel):
    theme: str
    count: int
    share: float
    sample_size: int
    denominator_type: Literal["reviews"] = "reviews"
    finding_id: int | None = None


class BatchComparison(BaseModel):
    theme: str
    baseline_batch_id: int
    followup_batch_id: int
    baseline_count: int
    followup_count: int
    baseline_share: float
    followup_share: float
    baseline_sample_size: int
    followup_sample_size: int
    count_delta: int
    share_delta: float
    conclusion: str
    limitation_note: str


class ReviewImportOutcome(BaseModel):
    batch_id: int
    artifact_id: int
    inserted_count: int
    duplicate_count: int
    duplicate_file: bool = False

