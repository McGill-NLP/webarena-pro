from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


IS_HUGGINGFACE_SPACE = bool(os.getenv("SPACE_ID") or os.getenv("SPACE_HOST"))


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "TravelMap")
    database_url: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(DATA_DIR / 'webarena_airbnb.db').as_posix()}",
    )
    session_secret: str = os.getenv("SESSION_SECRET", "webarena-airbnb-dev-secret")
    session_same_site: str = os.getenv(
        "SESSION_SAME_SITE",
        "none" if IS_HUGGINGFACE_SPACE else "lax",
    )
    session_https_only: bool = _env_bool("SESSION_HTTPS_ONLY", IS_HUGGINGFACE_SPACE)
    reset_token: str = os.getenv("RESET_TOKEN", "")
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "7860"))
    seed_file: Path = Path(os.getenv("SEED_FILE", DATA_DIR / "seed_data.json"))


settings = Settings()
