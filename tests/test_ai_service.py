import pytest

from core.errors import (
    ModelAuthenticationError,
    ModelOutputValidationError,
    ModelProviderError,
    ModelRateLimitError,
    ModelResponseError,
    ModelTimeoutError,
)
from core.models import AiRun, Project
from core.schemas import StructuredAIOutput
from services.ai_service import run_structured_model


class FakeProvider:
    model_name = "fake-model"

    def __init__(self, responses):
        self.responses = iter(responses)

    def generate(self, *, prompt, schema, repair_from=None):
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def make_project(session) -> Project:
    project = Project(
        name="AI Test",
        product_name="Product",
        access_code_hash="test",
        markets_json='["US"]',
    )
    session.add(project)
    session.flush()
    return project


def test_invalid_model_output_is_retried_once(db_session) -> None:
    project = make_project(db_session)
    provider = FakeProvider(
        [
            "not-json",
            {
                "result_type": "review_summary",
                "conclusion": "Evidence is insufficient.",
                "missing_information": ["production batch"],
                "requires_human_review": True,
            },
        ]
    )
    result = run_structured_model(
        project_id=project.id,
        run_type="review_analysis",
        prompt_version="v1",
        prompt="Analyze evidence.",
        evidence_ids=[],
        output_model=StructuredAIOutput,
        provider=provider,
        session=db_session,
    )
    assert result.requires_human_review is True
    run = db_session.query(AiRun).one()
    assert run.status == "success"


def test_invalid_model_output_never_enters_success_state(db_session) -> None:
    project = make_project(db_session)
    provider = FakeProvider(["bad", "still bad"])
    with pytest.raises(ModelOutputValidationError):
        run_structured_model(
            project_id=project.id,
            run_type="review_analysis",
            prompt_version="v1",
            prompt="Analyze evidence.",
            evidence_ids=[],
            output_model=StructuredAIOutput,
            provider=provider,
            session=db_session,
        )
    run = db_session.query(AiRun).one()
    assert run.status == "failed"
    assert run.error_code == "MODEL_BAD_JSON"


def test_model_timeout_is_recorded(db_session) -> None:
    project = make_project(db_session)
    provider = FakeProvider([TimeoutError("timeout")])
    with pytest.raises(ModelTimeoutError):
        run_structured_model(
            project_id=project.id,
            run_type="review_analysis",
            prompt_version="v1",
            prompt="Analyze evidence.",
            evidence_ids=[],
            output_model=StructuredAIOutput,
            provider=provider,
            session=db_session,
        )
    run = db_session.query(AiRun).one()
    assert run.status == "failed"
    assert run.error_code == "MODEL_TIMEOUT"


@pytest.mark.parametrize(
    ("provider_error", "error_code"),
    [
        (ModelAuthenticationError("auth"), "MODEL_AUTH_ERROR"),
        (ModelRateLimitError("rate"), "MODEL_RATE_LIMIT"),
        (ModelProviderError("server"), "MODEL_PROVIDER_ERROR"),
        (ModelResponseError("bad response"), "MODEL_BAD_RESPONSE"),
    ],
)
def test_provider_error_is_recorded_without_repair_retry(
    db_session, provider_error: Exception, error_code: str
) -> None:
    project = make_project(db_session)
    provider = FakeProvider([provider_error])

    with pytest.raises(type(provider_error)):
        run_structured_model(
            project_id=project.id,
            run_type="review_analysis",
            prompt_version="v1",
            prompt="Sensitive review text.",
            evidence_ids=[42],
            output_model=StructuredAIOutput,
            provider=provider,
            session=db_session,
        )

    run = db_session.query(AiRun).one()
    assert run.status == "failed"
    assert run.error_code == error_code
    assert run.input_hash

