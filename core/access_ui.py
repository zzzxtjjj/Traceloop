import re

import streamlit as st

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
    TradeLoopError,
)

ACCESS_DENIED_MESSAGE = "无权访问或对象不存在。"
DEFAULT_ERROR_MESSAGE = "操作失败，请检查输入后重试。"
RULE_ERROR_MESSAGE = "规则资料不可用、缺少来源或版本信息，请人工确认。"

MODEL_MESSAGES = {
    ModelNotConfiguredError: "模型未配置，未发起外部调用。",
    ModelTimeoutError: "模型调用超时，请稍后重试。",
    ModelAuthenticationError: "模型鉴权失败，请检查 API Key。",
    ModelRateLimitError: "模型调用频率受限，请稍后重试。",
    ModelProviderError: "模型服务暂时不可用，请稍后重试。",
    ModelResponseError: "模型服务返回了无法解析的响应。",
    ModelOutputValidationError: "模型输出未通过结构校验，未写入关键业务状态。",
}

SENSITIVE_TEXT = re.compile(
    r"(?:[A-Za-z]:[\\/]|sqlite:/{2,3}|file://|/home/|/users/|/tmp/|traceback)",
    re.IGNORECASE,
)


def safe_error_message(exc: Exception, *, fallback: str = DEFAULT_ERROR_MESSAGE) -> str:
    if isinstance(exc, (ProjectAccessDeniedError, CrossProjectReferenceError)):
        return ACCESS_DENIED_MESSAGE
    for error_type, message in MODEL_MESSAGES.items():
        if isinstance(exc, error_type):
            return message
    if isinstance(exc, RuleSourceError):
        return RULE_ERROR_MESSAGE

    raw = str(exc).strip()
    if not raw or SENSITIVE_TEXT.search(raw):
        return fallback
    if isinstance(exc, (TradeLoopError, ValueError)):
        return raw[:300]
    return fallback


def render_user_error(exc: Exception, *, fallback: str = DEFAULT_ERROR_MESSAGE) -> None:
    st.error(safe_error_message(exc, fallback=fallback))


def render_role_boundary_notice(role: str) -> None:
    st.caption(
        f"当前演示身份：{role}。角色选择只用于隐藏或禁用界面操作；"
        "最终访问和修改权限必须由后端按项目成员关系再次校验。"
    )
