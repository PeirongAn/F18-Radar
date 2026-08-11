"""Smoke-test the generated portable package. Not included in the package."""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets


def wait_for_port(process: subprocess.Popen, port: int, timeout: float = 90.0) -> float:
    started = time.monotonic()
    deadline = started + timeout
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(f"server exited early with code {exit_code}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return time.monotonic() - started
        except OSError:
            time.sleep(0.5)
    raise TimeoutError("TCP startup timeout")


async def check_websocket(port: int) -> str:
    async with websockets.connect(
        f"ws://127.0.0.1:{port}/ws", open_timeout=30
    ) as ws:
        return ws.state.name


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("usage: smoke_portable.py PACKAGE_DIR [PORT]", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    port = int(sys.argv[2]) if len(sys.argv) == 3 else 8080
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "F18_RADAR_HOME": str(root),
            "F18_RADAR_WEB_DIR": str(root / "web"),
            "F18_RADAR_CONFIG_DIR": str(root / "web"),
            "F18_RADAR_DATA_DIR": str(root / "data"),
            "F18_RADAR_LOG_DIR": str(logs),
            "F18_RADAR_ENV_FILE": str(root / "config" / "portable.env"),
            "PHYSIO_RING_ENABLED": "false",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )

    stdout_path = logs / "smoke.stdout.log"
    stderr_path = logs / "smoke.stderr.log"
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr:
        process = subprocess.Popen(
            [
                str(root / "runtime" / "F18RadarServer.exe"),
                "--static-dir",
                str(root / "web"),
                "--http-port",
                str(port),
            ],
            cwd=root,
            env=env,
            stdout=stdout,
            stderr=stderr,
        )
        try:
            startup_seconds = wait_for_port(process, port)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(f"http://127.0.0.1:{port}/", timeout=10) as response:
                html = response.read()
                http_status = response.status
            match = re.search(rb'src="([^"]+\.js)"', html)
            if not match:
                raise RuntimeError("index script reference missing")
            asset_url = f"http://127.0.0.1:{port}" + match.group(1).decode("ascii")
            with opener.open(asset_url, timeout=10) as response:
                asset = response.read()
                asset_status = response.status
            with opener.open(
                f"http://127.0.0.1:{port}/questionnaire_config.json", timeout=10
            ) as response:
                questionnaire = response.read()
                questionnaire_status = response.status

            websocket_state = asyncio.run(check_websocket(port))
            time.sleep(1)
            result = {
                "startup_seconds": round(startup_seconds, 1),
                "http_status": http_status,
                "index_bytes": len(html),
                "asset_status": asset_status,
                "asset_bytes": len(asset),
                "questionnaire_status": questionnaire_status,
                "questionnaire_bytes": len(questionnaire),
                "websocket_state": websocket_state,
                "database_exists": (root / "data" / "radar_operations.db").exists(),
                "log_exists": any(logs.iterdir()),
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
