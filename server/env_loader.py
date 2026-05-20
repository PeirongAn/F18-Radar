"""Small .env loader for server runtime settings.

This intentionally avoids adding a python-dotenv dependency. Existing process
environment variables win over values from the .env file.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_server_env(env_path: str | os.PathLike[str] | None = None) -> None:
    server_dir = Path(__file__).resolve().parent
    path = Path(env_path) if env_path is not None else server_dir / ".env"
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
