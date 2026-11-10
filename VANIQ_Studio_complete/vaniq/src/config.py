"""Central configuration. All settings come from environment variables (optionally a local .env)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # python-dotenv is optional at import time so tests never depend on a .env file
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VALID_MODES = ("live", "demo")


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer, got {raw!r}") from exc


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a number, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    mode: str
    data_dir: Path
    host: str
    port: int
    gnani_api_key: str | None
    gnani_base_url: str
    gnani_model: str
    gnani_timeout_s: float
    gnani_max_retries: int
    max_upload_mb: int
    max_audio_seconds: int
    seg_energy_threshold: float
    seg_max_dur_s: float
    log_level: str

    @property
    def is_demo(self) -> bool:
        return self.mode == "demo"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "vaniq.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def normalized_dir(self) -> Path:
        return self.data_dir / "normalized"

    @property
    def clips_dir(self) -> Path:
        return self.data_dir / "clips"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def stt_configured(self) -> bool:
        return bool(self.gnani_api_key)

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.normalized_dir, self.clips_dir, self.exports_dir):
            d.mkdir(parents=True, exist_ok=True)


def load_settings(load_env_file: bool = True) -> Settings:
    """Build Settings from the current environment.

    Demo and live modes use separate data directories so synthetic demo data can never
    mix with real recordings.
    """
    if load_env_file and load_dotenv is not None:
        load_dotenv(PROJECT_ROOT / ".env", override=False)

    mode = os.getenv("VANIQ_MODE", "live").strip().lower()
    if mode not in VALID_MODES:
        raise ValueError(f"VANIQ_MODE must be one of {VALID_MODES}, got {mode!r}")

    base_data = Path(os.getenv("VANIQ_DATA_DIR", str(PROJECT_ROOT / "data")))
    data_dir = base_data / ("demo" if mode == "demo" else "live")

    return Settings(
        mode=mode,
        data_dir=data_dir,
        host=os.getenv("VANIQ_HOST", "127.0.0.1"),
        port=_int("VANIQ_PORT", 8000),
        gnani_api_key=(os.getenv("GNANI_API_KEY") or None),
        gnani_base_url=os.getenv("GNANI_BASE_URL", "https://api.vachana.ai"),
        gnani_model=os.getenv("GNANI_MODEL", "prisma-v3.0"),
        gnani_timeout_s=_float("GNANI_TIMEOUT_S", 30.0),
        gnani_max_retries=_int("GNANI_MAX_RETRIES", 2),
        max_upload_mb=_int("VANIQ_MAX_UPLOAD_MB", 50),
        max_audio_seconds=_int("VANIQ_MAX_AUDIO_SECONDS", 600),
        seg_energy_threshold=_float("VANIQ_SEG_ENERGY_THRESHOLD", 50.0),
        seg_max_dur_s=_float("VANIQ_SEG_MAX_DUR_S", 15.0),
        log_level=os.getenv("VANIQ_LOG_LEVEL", "INFO").upper(),
    )
