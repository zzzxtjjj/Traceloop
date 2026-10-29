from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import core.access_ui
from core.access_ui import (
    ACCESS_DENIED_MESSAGE,
    RULE_ERROR_MESSAGE,
    render_role_boundary_notice,
    render_user_error,
    safe_error_message,
)
from core.errors import (
    CrossProjectReferenceError,
    ModelAuthenticationError,
    ModelNotConfiguredError,
    ModelOutputValidationError,
    ModelProviderError,
    ModelRateLimitError,
    ModelResponseError,
    ModelTimeoutError,
    ProjectAccessDeniedError,
    RuleSourceError,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
PAGES = [
    ROOT_DIR / "pages" / "02_报价决策.py",
    ROOT_DIR / "pages" / "03_任务与日报.py",
    ROOT_DIR / "pages" / "04_差评改进.py",
    ROOT_DIR / "pages" / "05_本地化与校验.py",
]


@pytest.mark.parametrize(
    "exc",
    [
        ProjectAccessDeniedError("项目 A 不允许当前用户读取"),
        CrossProjectReferenceError("任务 19 实际属于秘密项目 B"),
    ],
)
def test_access_errors_do_not_reveal_object_information(exc) -> None:
    assert safe_error_message(exc) == ACCESS_DENIED_MESSAGE


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (ModelNotConfiguredError("private"), "模型未配置"),
        (ModelTimeoutError("private"), "模型调用超时"),
        (ModelAuthenticationError("private"), "模型鉴权失败"),
        (ModelRateLimitError("private"), "模型调用频率受限"),
        (ModelProviderError("private"), "模型服务暂时不可用"),
        (ModelResponseError("private"), "无法解析"),
        (ModelOutputValidationError("private"), "结构校验"),
    ],
)
def test_model_errors_remain_actionable_without_upstream_details(exc, expected) -> None:
    message = safe_error_message(exc)
    assert expected in message
    assert "private" not in message


def test_rule_error_does_not_leak_rule_file_path() -> None:
    exc = RuleSourceError(r"无法读取 D:\private\rules.json")
    assert safe_error_message(exc) == RULE_ERROR_MESSAGE
    assert "D:" not in safe_error_message(exc)


@pytest.mark.parametrize(
    "raw",
    [
        r"数据库位于 C:\Users\secret\tradeloop.db",
        "sqlite:///private/data.db",
        "Traceback: /tmp/private.py line 7",
    ],
)
def test_validation_errors_with_sensitive_paths_use_safe_fallback(raw) -> None:
    message = safe_error_message(ValueError(raw), fallback="数据校验失败。")
    assert message == "数据校验失败。"
    assert raw not in message


def test_renderer_uses_sanitized_message(monkeypatch) -> None:
    messages = []
    monkeypatch.setattr(core.access_ui.st, "error", messages.append)

    render_user_error(CrossProjectReferenceError("项目 B 的文件路径"))

    assert messages == [ACCESS_DENIED_MESSAGE]


def test_role_notice_states_backend_is_authoritative(monkeypatch) -> None:
    messages = []
    monkeypatch.setattr(core.access_ui.st, "caption", messages.append)

    render_role_boundary_notice("采购")

    assert len(messages) == 1
    assert "岗位来自项目成员记录" in messages[0]
    assert "本地用户选择仅用于演示，不等于登录认证" in messages[0]
    assert "最终权限仍由后端校验" in messages[0]


@pytest.mark.parametrize("page", PAGES, ids=lambda path: path.name)
def test_permission_sensitive_pages_start_without_exception(page: Path) -> None:
    app = AppTest.from_file(str(page)).run(timeout=10)
    assert not app.exception
