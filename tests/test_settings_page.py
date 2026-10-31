from pathlib import Path

from streamlit.testing.v1 import AppTest

PAGE = Path(__file__).resolve().parents[1] / "pages" / "06_设置.py"


def test_language_switch_and_provider_apply_without_network():
    app = AppTest.from_file(str(PAGE)).run()
    assert not app.exception
    app.selectbox[1].set_value("豆包（火山方舟）").run()
    assert app.text_input[0].value == "https://ark.cn-beijing.volces.com/api/v3"
    assert app.text_input[2].value == ""
    app.text_input[1].set_value("test-model")
    app.text_input[2].set_value("test-session-secret")
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state["active_model_profile"]["model"] == "test-model"
    app.selectbox[0].set_value("English").run()
    assert not app.exception
    assert any("Interface language" in item.value for item in app.subheader)
    app.selectbox[0].set_value("Deutsch").run()
    assert not app.exception
    assert any("Anzeigesprache" in item.value for item in app.subheader)
    app.button[-1].click().run()
    assert not app.exception
    assert "active_model_profile" not in app.session_state
