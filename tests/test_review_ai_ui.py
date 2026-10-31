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
    ModelInputLimitError,
    ModelOutputValidationError,
    ModelProviderError,
    ModelRateLimitError,
    ModelResponseError,
    ModelTimeoutError,
)

PAGE = Path(__file__).resolve().parents[1] / "pages" / "04_差评改进.py"


def _prepare_page(monkeypatch, *, configured: bool) -> AppTest:
    user = SimpleNamespace(id=7, display_name="UI User", email="ui@example.com")
    project = SimpleNamespace(
        id=1,
        name="UI Test",
        product_name="Bottle",
        markets_json='["US", "DE"]',
    )
    batch = SimpleNamespace(id=11, name="Before", market="US", sample_size=12)
    monkeypatch.setattr(core.ui, "list_users", lambda: [user])
    monkeypatch.setattr(core.ui, "list_user_projects", lambda _user_id: [project])
    monkeypatch.setattr(
        core.ui,
        "require_project_member",
        lambda _project_id, _user_id: SimpleNamespace(role="owner"),
    )
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
            model_base_url="https://api.openai.com/v1",
        ),
    )
    app = AppTest.from_file(str(PAGE))
    app.session_state["current_user_id"] = user.id
    app.session_state["unlocked_project_ids"] = [project.id]
    app.session_state["active_project_id"] = project.id
    return app


def test_unconfigured_model_does_not_fall_back_when_ai_selected(monkeypatch) -> None:
    app = _prepare_page(monkeypatch, configured=False).run(timeout=10)
    rule_calls = []
    monkeypatch.setattr(
        services.review_service,
        "analyze_review_batch",
        lambda **kwargs: rule_calls.append(kwargs) or [],
    )

    assert not app.exception
    assert app.radio[0].options == ["规则分类", "真实 AI 分类"]
    assert any("模型配置不完整或无效" in item.value for item in app.warning)
    metric_values = {item.label: item.value for item in app.metric}
    assert "API Key" not in metric_values

    app.radio[0].set_value("真实 AI 分类")
    next(button for button in app.button if button.label == "运行所选分类").click()
    app.run(timeout=10)

    assert not app.exception
    assert app.error
    assert not rule_calls
    assert not any("已降级" in item.value for item in app.warning)


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
    initial_metrics = {item.label: item.value for item in app.metric}
    assert "API Key" not in initial_metrics
    assert any("AI 已配置" in item.value for item in app.caption)
    app.radio[0].set_value("真实 AI 分类")
    next(button for button in app.button if button.label == "运行所选分类").click()
    app.run(timeout=10)

    assert not app.exception
    assert any("真实 AI 分类完成" in item.value for item in app.success)
    metric_values = {item.label: item.value for item in app.metric}
    assert "AiRun ID" not in metric_values
    assert any("分析记录" in item.label for item in app.expander)


@pytest.mark.parametrize(
    ("error_type", "expected_message"),
    [
        (ModelTimeoutError, "模型调用超时"),
        (ModelAuthenticationError, "模型鉴权失败"),
        (ModelRateLimitError, "模型调用频率受限"),
        (ModelProviderError, "模型服务暂时不可用"),
        (ModelResponseError, "无法解析"),
        (ModelOutputValidationError, "结构校验"),
        (ModelInputLimitError, "输入超过本次模型分析上限"),
    ],
)
def test_model_failures_are_clear_and_do_not_fall_back(
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
    assert any("没有生成规则替代结果" in item.value for item in app.info)
    assert not any("已降级" in item.value for item in app.warning)


def test_page_never_displays_api_key_or_offers_live_test_button(monkeypatch) -> None:
    secret = "sk-DO-NOT-LEAK-123456"
    project = SimpleNamespace(
        id=1,
        name="UI Test",
        product_name="Bottle",
        markets_json='["US"]',
    )
    user = SimpleNamespace(id=7, display_name="UI User", email="ui@example.com")
    batch = SimpleNamespace(id=11, name="Before", market="US", sample_size=12)
    monkeypatch.setattr(core.ui, "list_users", lambda: [user])
    monkeypatch.setattr(core.ui, "list_user_projects", lambda _user_id: [project])
    monkeypatch.setattr(
        core.ui,
        "require_project_member",
        lambda _project_id, _user_id: SimpleNamespace(role="owner"),
    )
    monkeypatch.setattr(services.review_service, "list_review_batches", lambda _id: [batch])
    monkeypatch.setattr(
        services.review_service,
        "list_batch_findings",
        lambda _project_id, _batch_id: [],
    )
    monkeypatch.setattr(
        core.config,
        "settings",
        Settings(model_api_key=secret, model_name="safe-model"),
    )
    app = AppTest.from_file(str(PAGE))
    app.session_state["current_user_id"] = user.id
    app.session_state["unlocked_project_ids"] = [project.id]
    app.session_state["active_project_id"] = project.id

    app.run(timeout=10)

    assert not app.exception
    assert secret not in str(app)
    assert all("在线测试" not in button.label for button in app.button)
    assert all(item.label != "API Key" for item in app.metric)
    assert any("页面不提供在线测试按钮" in item.value for item in app.caption)


def test_decision_passport_renders_evidence_mode_and_next_action(monkeypatch) -> None:
    finding = SimpleNamespace(
        id=41,
        finding_type="review:packaging_damage",
        statement="包装破损反馈需要人工核对。",
        epistemic_status="causal_hypothesis",
        review_status="pending_review",
        sample_size=3,
        model_run_id=None,
        missing_info_json='["订单号"]',
        alternative_explanations_json='["运输损伤"]',
        suggested_actions_json='["核对运输记录"]',
    )
    evidence = [
        SimpleNamespace(
            id=77,
            locator_json='{"review_id":"R-41","csv_row":4}',
            excerpt="The box arrived crushed.",
        )
    ]
    import importlib.util

    spec = importlib.util.spec_from_file_location("review_page_under_test", PAGE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except BaseException:
        # The page stops early when no active project exists; helper definitions remain loaded.
        pass

    captured = []
    monkeypatch.setattr(module.st, "markdown", captured.append)
    monkeypatch.setattr(module.st, "dataframe", lambda rows, **_kwargs: captured.append(rows))
    monkeypatch.setattr(module.st, "caption", captured.append)
    module.render_decision_passport(finding=finding, evidence=evidence)

    rows = next(item for item in captured if isinstance(item, list))
    values = {row["字段"]: row["值"] for row in rows}
    assert values["结论模式"] == "规则降级"
    assert values["证据引用"] == "#77"
    assert values["下一步行动"] == "核对运输记录"
