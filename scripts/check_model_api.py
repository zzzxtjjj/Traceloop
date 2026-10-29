import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config import Settings, settings  # noqa: E402
from core.errors import TradeLoopError  # noqa: E402
from services.model_provider import OpenAICompatibleProvider  # noqa: E402
from services.model_readiness import (  # noqa: E402
    check_model_readiness,
    verify_model_live,
)


def main(
    argv: list[str] | None = None,
    *,
    config: Settings = settings,
    provider: OpenAICompatibleProvider | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Safely check TradeLoop model configuration and optional connectivity."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Send exactly one minimal structured request after local validation.",
    )
    args = parser.parse_args(argv)
    readiness = check_model_readiness(config)

    if not readiness.configured:
        print("configured=false")
        print("live_verified=false")
        if readiness.missing_fields:
            print(f"missing={','.join(readiness.missing_fields)}")
        if readiness.issues:
            print(f"issues={'; '.join(readiness.issues)}")
        return 1

    if not args.live:
        print("configured=true")
        print("live_verified=false")
        print(f"model={readiness.model_name}")
        print(f"base_url={readiness.base_url}")
        print(f"timeout_seconds={readiness.timeout_seconds:g}")
        print(f"max_input_chars={readiness.max_input_chars}")
        print(f"max_reviews_per_run={readiness.max_reviews_per_run}")
        print(f"max_attempts={readiness.max_attempts}")
        return 0

    try:
        result = verify_model_live(config, provider=provider)
    except TradeLoopError as exc:
        print(f"live_verified=false error_code={exc.code}", file=sys.stderr)
        return 1
    print(f"model={result.model_name}")
    print(f"latency_ms={result.latency_ms}")
    print("structured_schema_valid=true")
    print("live_verified=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
