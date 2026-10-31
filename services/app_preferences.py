"""Browser-session preferences; credentials are never written to disk."""
from dataclasses import replace
from urllib.parse import urlsplit

from core.config import Settings

PROVIDERS = {
    "DeepSeek": "https://api.deepseek.com",
    "通义千问（百炼）": "",
    "豆包（火山方舟）": "https://ark.cn-beijing.volces.com/api/v3",
    "Kimi（月之暗面）": "",
    "智谱 GLM": "",
    "其他兼容服务": "",
}


def build_session_config(base: Settings, profile: dict) -> Settings:
    url = profile.get("base_url", "").strip().rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("请填写服务商提供的 HTTPS 接口地址。")
    if parsed.query or parsed.fragment:
        raise ValueError("接口地址不能包含查询参数或密钥。")
    model = profile.get("model", "").strip()
    key = profile.get("api_key", "").strip()
    if not model or not key:
        raise ValueError("请填写模型名称和该服务商的密钥。")
    return replace(
        base, model_api_key=key, model_name=model, model_base_url=url,
        model_json_object=True,
    )


def runtime_config(base: Settings) -> Settings:
    from streamlit.runtime.scriptrunner import get_script_run_ctx

    if get_script_run_ctx(suppress_warning=True) is None:
        return base
    import streamlit as st

    profile = st.session_state.get("active_model_profile")
    return build_session_config(base, profile) if profile else base
