import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


def _float_env(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.getenv(name, str(default))))
    except ValueError:
        return default


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


settings = Settings()

