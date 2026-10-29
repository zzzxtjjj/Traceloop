import json
import re
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy.engine import make_url

from core.config import ROOT_DIR, Settings, settings
from services.model_readiness import check_model_readiness

CheckStatus = Literal["pass", "warning", "fail"]
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]

REQUIRED_FILES = (
    "app.py",
    "README.md",
    "requirements.txt",
    ".env.example",
    "alembic.ini",
    "scripts/migrate_db.py",
    "scripts/seed_demo.py",
)
REQUIRED_PAGES = tuple(f"0{number}_" for number in range(1, 6))
EXPECTED_REVISION = "0002_project_membership"
EXPECTED_DEMO_PROJECT = "保温杯新品出海"
EXPECTED_DEMO_EMAILS = (
    "owner@tradeloop.demo",
    "procurement@tradeloop.demo",
    "operations@tradeloop.demo",
    "quality@tradeloop.demo",
)


@dataclass(frozen=True)
class ReleaseCheck:
    name: str
    status: CheckStatus
    summary: str


@dataclass(frozen=True)
class ReleaseReport:
    checks: tuple[ReleaseCheck, ...]

    @property
    def exit_code(self) -> int:
        return 1 if any(item.status == "fail" for item in self.checks) else 0

    @property
    def counts(self) -> dict[str, int]:
        return {
            status: sum(item.status == status for item in self.checks)
            for status in ("pass", "warning", "fail")
        }

    def to_dict(self) -> dict:
        return {
            "exit_code": self.exit_code,
            "counts": self.counts,
            "checks": [asdict(item) for item in self.checks],
        }


def _check_required_files(root: Path) -> ReleaseCheck:
    missing = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    if missing:
        return ReleaseCheck("required_files", "fail", f"缺少 {len(missing)} 个必需文件。")
    return ReleaseCheck("required_files", "pass", "必需启动与配置文件齐全。")


def _check_pages(root: Path) -> ReleaseCheck:
    pages_dir = root / "pages"
    existing = [item.name for item in pages_dir.glob("*.py")] if pages_dir.is_dir() else []
    missing = [
        prefix
        for prefix in REQUIRED_PAGES
        if not any(name.startswith(prefix) for name in existing)
    ]
    if missing:
        return ReleaseCheck("pages", "fail", f"5 个页面中缺少 {len(missing)} 个。")
    return ReleaseCheck("pages", "pass", "5 个业务页面均存在。")


def _check_alembic_revision(root: Path) -> ReleaseCheck:
    revision_file = root / "migrations" / "versions" / "0002_project_membership.py"
    if not revision_file.is_file():
        return ReleaseCheck("alembic_revision", "fail", "缺少 0002 迁移文件。")
    source = revision_file.read_text(encoding="utf-8")
    match = re.search(r'^revision\s*=\s*["\']([^"\']+)["\']', source, re.MULTILINE)
    if not match or match.group(1) != EXPECTED_REVISION:
        return ReleaseCheck("alembic_revision", "fail", "最新迁移版本不是预期的 0002。")
    return ReleaseCheck("alembic_revision", "pass", "Alembic 最新迁移版本为 0002。")


def _sqlite_path(database_url: str, root: Path) -> Path | None:
    try:
        url = make_url(database_url)
    except Exception:
        return None
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    path = Path(url.database)
    return path if path.is_absolute() else root / path


def _check_demo_data(root: Path, database_url: str) -> ReleaseCheck:
    database_path = _sqlite_path(database_url, root)
    if database_path is None:
        return ReleaseCheck(
            "demo_data",
            "warning",
            "为保持离线，本次未检查非本地 SQLite 数据库。",
        )
    if not database_path.is_file():
        return ReleaseCheck("demo_data", "warning", "本地数据库不存在，请在演示前运行 seed。")

    try:
        connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if not {"projects", "users", "project_members"}.issubset(tables):
                return ReleaseCheck("demo_data", "fail", "数据库尚未升级到成员权限结构。")
            if "alembic_version" not in tables:
                return ReleaseCheck("demo_data", "fail", "数据库缺少 Alembic 版本记录。")
            database_revision = connection.execute(
                "SELECT version_num FROM alembic_version LIMIT 1"
            ).fetchone()
            if not database_revision or database_revision[0] != EXPECTED_REVISION:
                return ReleaseCheck("demo_data", "fail", "数据库尚未升级到 Alembic 0002。")
            project_row = connection.execute(
                "SELECT id FROM projects WHERE name = ?", (EXPECTED_DEMO_PROJECT,)
            ).fetchone()
            user_count = connection.execute(
                "SELECT COUNT(*) FROM users WHERE email IN (?, ?, ?, ?)",
                EXPECTED_DEMO_EMAILS,
            ).fetchone()[0]
            member_count = 0
            if project_row:
                member_count = connection.execute(
                    "SELECT COUNT(*) FROM project_members "
                    "WHERE project_id = ? AND status = 'active'",
                    (project_row[0],),
                ).fetchone()[0]
        finally:
            connection.close()
    except sqlite3.Error:
        return ReleaseCheck("demo_data", "fail", "本地数据库无法安全读取或结构异常。")

    if not project_row or user_count != 4 or member_count != 4:
        return ReleaseCheck(
            "demo_data",
            "fail",
            "演示 seed 不完整：需要 1 个项目、4 个用户和 4 个成员。",
        )
    return ReleaseCheck("demo_data", "pass", "演示项目、4 个用户和 4 个成员已就绪。")


def _check_model(config: Settings) -> ReleaseCheck:
    readiness = check_model_readiness(config)
    if readiness.configured:
        return ReleaseCheck(
            "model_readiness",
            "pass",
            f"模型本地配置有效；live_verified=false；max_attempts={readiness.max_attempts}。",
        )
    issue_count = len(readiness.missing_fields) + len(readiness.issues)
    return ReleaseCheck(
        "model_readiness",
        "warning",
        f"模型尚未完成本地配置（{issue_count} 项）；未执行在线验证。",
    )


def _check_poster(root: Path) -> ReleaseCheck:
    poster = root / "deliverables" / "poster" / "tradeloop_poster.svg"
    if not poster.is_file():
        return ReleaseCheck("poster", "fail", "海报 SVG 不存在。")
    try:
        svg_root = ET.parse(poster).getroot()
    except (ET.ParseError, OSError):
        return ReleaseCheck("poster", "fail", "海报 SVG 无法解析。")
    if svg_root.get("width") != "800mm" or svg_root.get("height") != "1800mm":
        return ReleaseCheck("poster", "fail", "海报尺寸必须为 800mm × 1800mm。")
    if "二维码占位" in poster.read_text(encoding="utf-8"):
        return ReleaseCheck(
            "poster", "warning", "海报尺寸正确，但正式发布前需替换二维码占位。"
        )
    return ReleaseCheck("poster", "pass", "海报 SVG 尺寸为 800mm × 1800mm。")


def _check_pitch(root: Path) -> ReleaseCheck:
    pitch_files = (
        root / "deliverables" / "pitch" / "index.html",
        root / "deliverables" / "pitch" / "THREE_MINUTE_SCRIPT.md",
    )
    if not all(item.is_file() for item in pitch_files):
        return ReleaseCheck("pitch", "fail", "三分钟路演页面或讲稿缺失。")
    return ReleaseCheck("pitch", "pass", "三分钟路演页面与讲稿均存在。")


def _run_command(
    runner: CommandRunner,
    command: list[str],
    root: Path,
) -> subprocess.CompletedProcess[str]:
    return runner(command, cwd=root, capture_output=True, text=True, check=False)


def _check_git(root: Path, runner: CommandRunner) -> list[ReleaseCheck]:
    head = _run_command(runner, ["git", "rev-parse", "--verify", "HEAD"], root)
    head_check = (
        ReleaseCheck("git_head", "pass", "Git HEAD 可用。")
        if head.returncode == 0 and head.stdout.strip()
        else ReleaseCheck("git_head", "fail", "Git HEAD 不可用。")
    )
    worktree = _run_command(runner, ["git", "status", "--porcelain"], root)
    if worktree.returncode != 0:
        tree_check = ReleaseCheck("git_worktree", "fail", "无法读取 Git 工作树状态。")
    elif worktree.stdout.strip():
        changed_count = len(worktree.stdout.splitlines())
        tree_check = ReleaseCheck(
            "git_worktree", "fail", f"Git 工作树有 {changed_count} 项未提交变更。"
        )
    else:
        tree_check = ReleaseCheck("git_worktree", "pass", "Git 工作树干净。")

    upstream = _run_command(
        runner,
        ["git", "rev-parse", "--verify", "@{upstream}"],
        root,
    )
    if upstream.returncode != 0 or not upstream.stdout.strip():
        upstream_check = ReleaseCheck(
            "git_upstream", "warning", "当前分支未配置本地 upstream 记录。"
        )
    elif head.returncode == 0 and head.stdout.strip() == upstream.stdout.strip():
        upstream_check = ReleaseCheck(
            "git_upstream", "pass", "本地 HEAD 与已记录 upstream 一致。"
        )
    else:
        divergence = _run_command(
            runner,
            ["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
            root,
        )
        match = re.fullmatch(r"\s*(\d+)\s+(\d+)\s*", divergence.stdout)
        if divergence.returncode == 0 and match:
            ahead, behind = match.groups()
            summary = f"本地分支与 upstream 不一致：ahead={ahead}，behind={behind}。"
        else:
            summary = "本地分支与 upstream 不一致。"
        upstream_check = ReleaseCheck("git_upstream", "fail", summary)
    return [head_check, tree_check, upstream_check]


def _check_tool(
    name: str,
    command: list[str],
    root: Path,
    runner: CommandRunner,
) -> ReleaseCheck:
    result = _run_command(runner, command, root)
    if result.returncode == 0:
        return ReleaseCheck(name, "pass", f"{name} 检查通过。")
    return ReleaseCheck(name, "fail", f"{name} 检查失败（退出码 {result.returncode}）。")


def verify_release(
    *,
    root_dir: Path = ROOT_DIR,
    database_url: str | None = None,
    config: Settings = settings,
    full: bool = False,
    runner: CommandRunner = subprocess.run,
) -> ReleaseReport:
    root = Path(root_dir)
    checks = [
        _check_required_files(root),
        _check_pages(root),
        _check_alembic_revision(root),
        _check_demo_data(root, database_url or config.database_url),
        _check_model(config),
        _check_poster(root),
        _check_pitch(root),
        *_check_git(root, runner),
    ]
    if full:
        checks.append(
            _check_tool(
                "pytest", [sys.executable, "-m", "pytest", "-q"], root, runner
            )
        )
        checks.append(
            _check_tool(
                "ruff",
                [
                    sys.executable,
                    "-m",
                    "ruff",
                    "check",
                    "core",
                    "services",
                    "pages",
                    "scripts",
                    "tests",
                    "migrations",
                ],
                root,
                runner,
            )
        )
    return ReleaseReport(tuple(checks))


def report_as_json(report: ReleaseReport) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
