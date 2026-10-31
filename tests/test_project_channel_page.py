from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "06_项目群聊.py"


def test_project_channel_page_shows_server_session_login() -> None:
    app = AppTest.from_file(str(PAGE)).run(timeout=10)

    assert not app.exception
    assert any(item.label == "邮箱" for item in app.text_input)
    assert any(item.label == "密码" for item in app.text_input)
    assert any(item.label == "登录" for item in app.button)
