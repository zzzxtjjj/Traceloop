import streamlit as st

from core.config import settings
from core.display_language import LANGUAGES
from core.theme import apply_brand_theme, render_footer, render_page_header
from services.app_preferences import PROVIDERS, build_session_config

st.set_page_config(page_title="设置 · TradeLoop", page_icon="⚙️", layout="wide")
apply_brand_theme()
render_page_header("PREFERENCES · 使用偏好", "设置", "选择界面语言和本次使用的 AI 服务。")

st.subheader("界面语言")
if st.session_state.get("display_language") not in LANGUAGES:
    st.session_state["display_language"] = "简体中文"
st.selectbox("显示语言", LANGUAGES, key="display_language")
st.caption("切换界面提示和表单标题；评价原文、商品文案和已保存记录保持原语言。")

st.subheader("AI 服务")
st.caption("配置只对当前浏览器会话生效，不修改本机 .env，也不影响其他人的设置。")
provider = st.selectbox("服务商", list(PROVIDERS), key="settings_provider")
default_url = PROVIDERS[provider]
st.caption("模型和接口地址请从所选服务商控制台复制；不同地区、账户可能使用不同地址。")
with st.form(f"model_settings_{provider}"):
    url = st.text_input("接口地址", value=default_url)
    model = st.text_input("模型名称", value="deepseek-flash" if provider == "DeepSeek" else "")
    key = st.text_input(
        "该服务商的 API 密钥", type="password", value="", key=f"provider_secret_{provider}"
    )
    st.caption("输入框不会回显已保存密钥。切换服务商需要填写对应密钥，不会复用其他厂商密钥。")
    saved = st.form_submit_button("应用设置")
if saved:
    profile = {"provider": provider, "base_url": url, "model": model, "api_key": key}
    try:
        build_session_config(settings, profile)
    except ValueError as exc:
        st.error(str(exc))
    else:
        st.session_state["active_model_profile"] = profile
        st.success("已应用。下一次 AI 分析将使用此服务；保存设置不会发起付费请求。")

active = st.session_state.get("active_model_profile")
if active:
    st.write(f"当前会话使用：{active['provider']} · {active['model']}")
else:
    st.write("当前使用：本机环境配置。")
st.caption("服务商入口已提供；除 DeepSeek 外，其他服务仍需用你有权限的模型进行兼容性验证。")
if st.button("恢复本机配置并清除会话密钥"):
    st.session_state.pop("active_model_profile", None)
    for item in list(st.session_state):
        if item.startswith(("model_settings_", "provider_secret_")):
            del st.session_state[item]
    st.rerun()
render_footer()
