import json
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def _run_process(
    command: list[str],
    *,
    env: dict[str, str],
    timeout: int,
    stage: str,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=ROOT_DIR,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    assert result.returncode == 0, (
        f"{stage} failed with exit code {result.returncode}.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    return result


def test_seeded_demo_opens_all_pages_without_network(tmp_path) -> None:
    database_path = tmp_path / "seeded-pages.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": database_url,
            "MODEL_API_KEY": "",
            "MODEL_NAME": "",
            "MODEL_BASE_URL": "https://api.openai.com/v1",
            "PYTHONPATH": os.pathsep.join(
                [str(ROOT_DIR), env.get("PYTHONPATH", "")]
            ).rstrip(os.pathsep),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )

    _run_process(
        [
            sys.executable,
            "scripts/migrate_db.py",
            "--database-url",
            database_url,
        ],
        env=env,
        timeout=30,
        stage="temporary database migration",
    )
    _run_process(
        [sys.executable, "scripts/seed_demo.py"],
        env=env,
        timeout=30,
        stage="temporary demo data seed",
    )

    app_test_script = r'''
import json
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

from services.membership_service import get_user_by_email
from services.project_service import get_project_by_name

root = Path.cwd()
files = [root / "app.py", *sorted((root / "pages").glob("*.py"))]
owner = get_user_by_email("owner@tradeloop.demo")
project = get_project_by_name("保温杯新品出海")
failures = []
results = []

if owner is None or project is None:
    print(
        "SEEDED_SMOKE_JSON="
        + json.dumps(
            {"failures": ["seed did not create the demo owner and project"]},
            ensure_ascii=False,
        )
    )
    raise SystemExit(1)

for path in files:
    try:
        app = AppTest.from_file(str(path))
        app.session_state["current_user_id"] = owner.id
        app.session_state["active_project_id"] = project.id
        app.session_state["unlocked_project_ids"] = [project.id]
        app.run(timeout=15)
        exceptions = [str(item.value) for item in app.exception]
        if exceptions:
            failures.append(f"{path.name}: page exceptions: {exceptions}")
        results.append({"page": path.name, "exceptions": exceptions})

        if path.name == "01_项目首页.py":
            rendered_tables = "\n".join(
                frame.value.to_string() for frame in app.dataframe
            )
            if "项目负责人" not in rendered_tables:
                failures.append(
                    "01_项目首页.py: persisted owner membership role was not rendered"
                )

        if path.name == "04_差评改进.py":
            metrics = {item.label: item.value for item in app.metric}
            if "API Key" in metrics:
                failures.append(
                    "04_差评改进.py: technical credentials should not appear as metrics"
                )
            if not any("模型配置不完整或无效" in item.value for item in app.warning):
                failures.append(
                    "04_差评改进.py: expected not-live-verified model status"
                )
    except Exception as exc:
        failures.append(f"{path.name}: AppTest runner failed: {type(exc).__name__}: {exc}")

print(
    "SEEDED_SMOKE_JSON="
    + json.dumps({"results": results, "failures": failures}, ensure_ascii=False)
)
raise SystemExit(1 if failures else 0)
'''
    result = _run_process(
        [sys.executable, "-c", app_test_script],
        env=env,
        timeout=90,
        stage="seeded Streamlit page smoke test",
    )

    summary_line = next(
        (
            line.removeprefix("SEEDED_SMOKE_JSON=")
            for line in result.stdout.splitlines()
            if line.startswith("SEEDED_SMOKE_JSON=")
        ),
        None,
    )
    assert summary_line is not None, f"child process returned no page summary:\n{result.stdout}"
    summary = json.loads(summary_line)
    assert not summary["failures"]
    assert len(summary["results"]) == 8
