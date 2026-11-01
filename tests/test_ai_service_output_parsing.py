import pytest
from pydantic import BaseModel, ConfigDict, Field

from core.errors import ModelOutputValidationError
from services.ai_service import run_structured_model


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1)


class Provider:
    model_name = "offline"
    max_attempts = 1

    def __init__(self, value):
        self.value = value

    def generate(self, **kwargs):
        return self.value


@pytest.mark.parametrize("raw", [
    '{"title":"ok"}',
    'Here is the JSON:\n```json\n{"title":"ok"}\n```',
    'prefix {"title":"ok"}',
])
def test_structured_output_extracts_json_object(raw):
    result = run_structured_model(
        project_id=1, run_type="test", prompt_version="v1", prompt="x",
        evidence_ids=[], output_model=Output, provider=Provider(raw), record_run=False,
    )
    assert result.title == "ok"


def test_structured_output_reports_field_path():
    with pytest.raises(ModelOutputValidationError, match="title"):
        run_structured_model(
            project_id=1, run_type="test", prompt_version="v1", prompt="x",
            evidence_ids=[], output_model=Output,
            provider=Provider('{"wrong": 1}'), record_run=False,
        )
