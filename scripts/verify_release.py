import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.release_verification import report_as_json, verify_release  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run TradeLoop release checks locally without contacting model APIs."
    )
    parser.add_argument("--full", action="store_true", help="Also run pytest and Ruff.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    report = verify_release(full=args.full)
    if args.json:
        print(report_as_json(report))
    else:
        for item in report.checks:
            print(f"[{item.status.upper()}] {item.name}: {item.summary}")
        counts = report.counts
        print(
            f"Summary: pass={counts['pass']} warning={counts['warning']} fail={counts['fail']}"
        )
    return report.exit_code


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
