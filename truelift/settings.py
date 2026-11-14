"""Service configuration, read once from the environment (twelve-factor style).

Every constant the page also needs (consent weeks, holdout share, commission and GST rates) is
served from here at `/api/v1/config`, so the page never carries its own copy (audit TL-033).

Environment variables (all optional):
  TRUELIFT_MODEL            model bundle path (default data/processed/model.pkl)
  TRUELIFT_DATA_DIR         directory with restaurants.csv (default data/processed)
  TRUELIFT_CACHE_DIR        where the serving cache is written (default data/processed)
  TRUELIFT_DB               SQLite file for the consent ledger and exposure log (default: in memory)
  TRUELIFT_CONSENT_WEEKS    weeks an OTP approval lasts (default 4)
  TRUELIFT_HOLDOUT          share of eligible customers held out (default 0.10)
  TRUELIFT_DEMO_RESTAURANT  restaurant opened first in the demo (default 233)
  TRUELIFT_SESSION_IDLE     seconds before an idle demo session is dropped (default 3600)
  TRUELIFT_LOG_JSON         1 to write one JSON log line per request (default 1)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env(name: str, default: str) -> str:
    v = os.environ.get(name)
    return default if v is None or v == "" else v


@dataclass(frozen=True)
class Settings:
    model_path: Path
    data_dir: Path
    cache_dir: Path
    db_path: str
    consent_weeks: int
    holdout_share: float
    demo_restaurant: int
    session_idle_seconds: int
    log_json: bool


def load_settings() -> Settings:
    data_dir = Path(_env("TRUELIFT_DATA_DIR", str(ROOT / "data/processed")))
    return Settings(
        model_path=Path(_env("TRUELIFT_MODEL", str(ROOT / "data/processed/model.pkl"))),
        data_dir=data_dir,
        cache_dir=Path(_env("TRUELIFT_CACHE_DIR", str(data_dir))),
        db_path=_env("TRUELIFT_DB", ":memory:"),
        consent_weeks=int(_env("TRUELIFT_CONSENT_WEEKS", "4")),
        holdout_share=float(_env("TRUELIFT_HOLDOUT", "0.10")),
        demo_restaurant=int(_env("TRUELIFT_DEMO_RESTAURANT", "233")),
        session_idle_seconds=int(_env("TRUELIFT_SESSION_IDLE", "3600")),
        log_json=_env("TRUELIFT_LOG_JSON", "1") == "1",
    )
