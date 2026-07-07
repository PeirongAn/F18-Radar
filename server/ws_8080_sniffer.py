"""
Simple WebSocket listener for validating external messages sent to port 8080.

This script does not forward messages to the F18 server. It only accepts
WebSocket connections, prints every received frame, and optionally sends a
small ack back to the client.

Example:
  python server/ws_8080_sniffer.py --port 8080

If port 8080 is already used by the real F18 server, stop that server first.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import time
from pathlib import Path
from typing import Optional

from aiohttp import WSMsgType, web


LOGGER = logging.getLogger("ws_8080_sniffer")


def now_ms() -> int:
    return int(time.time() * 1000)


def pretty_payload(data: str) -> str:
    try:
        parsed = json.loads(data)
    except (TypeError, json.JSONDecodeError):
        return data
    return json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True)


def emit(log_file: Optional[Path], line: str) -> None:
    print(line, flush=True)
    if not log_file:
        return
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


async def handle_ws(request: web.Request) -> web.StreamResponse:
    if request.headers.get("Upgrade", "").lower() != "websocket":
        return web.Response(
            status=426,
            text="WebSocket listener is running. Connect with ws://host:port/ws\n",
        )

    log_file: Optional[Path] = request.app["log_file"]
    send_ack: bool = request.app["send_ack"]
    conn_id = f"{request.remote or 'unknown'}#{now_ms()}"

    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)

    emit(log_file, f"\n[{now_ms()}] CONNECT {conn_id} path={request.rel_url}")

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            emit(log_file, f"[{now_ms()}] MESSAGE {conn_id}")
            emit(log_file, pretty_payload(msg.data))
            if send_ack:
                await ws.send_str(json.dumps({
                    "type": "sniffer_ack",
                    "ok": True,
                    "received_at_ms": now_ms(),
                }, ensure_ascii=False))
        elif msg.type == WSMsgType.BINARY:
            emit(log_file, f"[{now_ms()}] BINARY {conn_id} bytes={len(msg.data)}")
            if send_ack:
                await ws.send_str(json.dumps({
                    "type": "sniffer_ack",
                    "ok": True,
                    "binary_bytes": len(msg.data),
                    "received_at_ms": now_ms(),
                }, ensure_ascii=False))
        elif msg.type == WSMsgType.ERROR:
            emit(log_file, f"[{now_ms()}] ERROR {conn_id} {ws.exception()}")
            break

    emit(log_file, f"[{now_ms()}] DISCONNECT {conn_id}")
    return ws


async def run(args: argparse.Namespace) -> None:
    app = web.Application()
    app["log_file"] = Path(args.log_file) if args.log_file else None
    app["send_ack"] = not args.no_ack
    app.router.add_get("/{tail:.*}", handle_ws)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, args.host, args.port)
    await site.start()

    LOGGER.info("listening on ws://%s:%s", args.host, args.port)
    if app["log_file"]:
        LOGGER.info("also writing received messages to %s", app["log_file"])
    LOGGER.info("ack responses are %s", "disabled" if args.no_ack else "enabled")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass
    await stop_event.wait()
    await runner.cleanup()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple WebSocket message listener for port 8080.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--log-file", default="server/logs/ws_8080_sniffer.log")
    parser.add_argument("--no-ack", action="store_true", help="Do not send sniffer_ack responses.")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
