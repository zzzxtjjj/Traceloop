import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

import core.config
import core.ui
import services.review_service
from core.config import Settings
from core.errors import (
    ModelAuthenticationError,
    ModelOutputValidationError,
    ModelProviderError,
    ModelRateLimitError,
    ModelResponseError,
    ModelTimeoutError,
)

PAGE = Path(__file__).resolve().parents[1] / "pages" / "04_差评改进.py"


def _prepare_page(monkeypatch, *, configured: bool) -> AppTest:
    project = SimpleNamespace(
        id=1,
        name="UI Test",
        product_name="Bottle",
        markets_json='["US", "DE"]',
    )
    batch = SimpleNamespace(id=11, name="Before", market="US", sample_size=12)
    monkeypatch.setattr(core.ui, "list_projects", lambda: [project])
    monkeypatch.setattr(services.review_service, "list_review_batches", lambda _project_id: [batch])
    monkeypatch.setattr(
        services.review_service,
        "list_batch_findings",
        lambda _project_id, _batch_id: [],
    )
    monkeypatch.setattr(
        services.review_service,
        "analyze_review_batch",
        lambda **_kwargs: [SimpleNamespace(theme="packaging_damage")],
    )
    monkeypatch.setattr(
        core.config,
        "settings",
        Settings(
            model_api_key="configured-key" if configured else "",
            model_name="configured-model" if configured else "",
        ),
    )
    app = AppTest.from_file(str(PAGE))
    app.session_state["unlocked_project_ids"] = [project.id]
    app.session_state["active_project_id"] = project.id
    return app


def test_unconfigured_model_downgrades_to_rules_without_page_error(monkeypatch) -> None:
    app = _prepare_page(monkeypatch, configured=False).run(timeout=10)

    assert not app.exception
    assert app.radio[0].options == ["规则分类", "真实 AI 分类"]
    assert any("模型未配置" in item.value for item in app.warning)

    app.radio[0].set_value("真实 AI 分类")
    next(button for button in app.button if button.label == "运行所选分类").click()
    app.run(timeout=10)

    assert not app.exception
    assert any("已降级为可复现规则分类" in item.value for item in app.warning)


def test_configured_model_displays_run_metadata(monkeypatch) -> None:
    fake_service = ModuleType("services.review_ai_service")
    result = SimpleNamespace(
        ai_run_id=27,
        finding_ids=[101, 102],
        prompt_version="review_classify_v1",
        status="success",
        model_name="configured-model",
        error_code=None,
    )
    fake_service.analyze_review_batch_with_model = lambda **_kwargs: result
    fake_service.get_latest_review_ai_run = lambda **_kwargs: result
    monkeypatch.setitem(sys.modules, "services.review_ai_service", fake_service)

    app = _prepare_page(monkeypatch, configured=True).run(timeout=10)
    app.radio[0].set_value("真实 AI 分类")
    next(button for button in app.button if button.label == "运行所选分类").click()
    app.run(timeout=10)

    assert not app.exception
    assert any("真实 AI 分类完成" in item.value for item in app.success)
    metric_values = {item.label: item.value for item in app.metric}
    assert metric_values["AiRun ID"] == "27"
    assert metric_values["模型"] == "configured-model"
    assert metric_values["Prompt 版本"] == "review_classify_v1"
    assert metric_values["运行状态"] == "success"


@pytest.mark.parametrize(
    ("error_type", "expected_message"),
    [
        (ModelTimeoutError, "模型调用超时"),
        (ModelAuthenticationError, "模型鉴权失败"),
        (ModelRateLimitError, "模型调用频率受限"),
        (ModelProviderError, "模型服务暂时不可用"),
        (ModelResponseError, "无法解析"),
        (ModelOutputValidationError, "结构校验"),
    ],
)
def test_model_failures_are_clear_and_fall_back_without_crashing(
    monkeypatch, error_type, expected_message
) -> None:
    fake_service = ModuleType("services.review_ai_service")

    def fail_analysis(**_kwargs):
        raise error_type("private upstream detail")

    fake_service.analyze_review_batch_with_model = fail_analysis
    fake_service.get_latest_review_ai_run = lambda **_kwargs: SimpleNamespace(
        id=28,
        model="configured-model",
        prompt_version="review_classify_v1",
        status="failed",
        error_code=error_type.code,
    )
    monkeypatch.setitem(sys.modules, "services.review_ai_service", fake_service)

    app = _prepare_page(monkeypatch, configured=True).run(timeout=10)
    app.radio[0].set_value("真实 AI 分类")
    next(button for button in app.button if button.label == "运行所选分类").click()
    app.run(timeout=10)

    assert not app.exception
    assert any(expected_message in item.value for item in app.error)
    assert any("已降级为规则分类" in item.value for item in app.warning)
