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

