import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return 0


@dataclass(frozen=True)
class Settings:
    root_dir: Path = ROOT_DIR
    data_dir: Path = ROOT_DIR / "data"
    upload_dir: Path = ROOT_DIR / "data" / "uploads"
    database_url: str = os.getenv("DATABASE_URL") or (
        f"sqlite:///{ROOT_DIR / 'data' / 'tradeloop.db'}"
    )
    model_api_key: str = os.getenv("MODEL_API_KEY", "")
    model_name: str = os.getenv("MODEL_NAME", "")
    model_base_url: str = os.getenv("MODEL_BASE_URL", "https://api.openai.com/v1")
    model_timeout_seconds: float = _float_env("MODEL_TIMEOUT_SECONDS", 30.0)
    model_max_input_chars: int = _positive_int_env("MODEL_MAX_INPUT_CHARS", 50_000)
    model_max_reviews_per_run: int = _positive_int_env(
        "MODEL_MAX_REVIEWS_PER_RUN", 200
    )
    model_max_attempts: int = _positive_int_env("MODEL_MAX_ATTEMPTS", 1)


settings = Settings()

