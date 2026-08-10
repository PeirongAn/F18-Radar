"""Resolve source-tree and packaged runtime paths in one place.

Source runs keep the historical repository layout. A portable launcher can
override individual locations with ``F18_RADAR_*`` environment variables so
runtime data is written outside the frozen executable directory.
"""

from __future__ import annotations

import os
from pathlib import Path


SERVER_SOURCE_DIR = Path(__file__).resolve().parent
PROJECT_SOURCE_DIR = SERVER_SOURCE_DIR.parent


def _env_path(name: str, fallback: Path) -> Path:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser().resolve() if value else fallback.resolve()


RUNTIME_HOME = _env_path("F18_RADAR_HOME", PROJECT_SOURCE_DIR)
WEB_DIR = _env_path("F18_RADAR_WEB_DIR", PROJECT_SOURCE_DIR / "dist")
CONFIG_DIR = _env_path("F18_RADAR_CONFIG_DIR", PROJECT_SOURCE_DIR / "public")
DATA_DIR = _env_path("F18_RADAR_DATA_DIR", SERVER_SOURCE_DIR / "data")
LOG_DIR = _env_path("F18_RADAR_LOG_DIR", SERVER_SOURCE_DIR / "logs")


def ensure_writable_directories() -> None:
    """Create the common writable roots before services initialize."""

    for path in (DATA_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)
