from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT_DIR = Path(__file__).resolve().parents[1]
APP_FILES = [ROOT_DIR / "app.py", *sorted((ROOT_DIR / "pages").glob("*.py"))]


@pytest.mark.parametrize("app_file", APP_FILES, ids=lambda path: path.name)
def test_streamlit_page_starts_without_exception(app_file: Path) -> None:
    app = AppTest.from_file(str(app_file)).run(timeout=10)
    assert not app.exception

