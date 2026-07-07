"""
WebSocket sniffer/proxy for external messages normally sent to port 8080.

Run this script on port 8080, and run the real F18 server on another port
such as 8081. External clients continue connecting to this script; all
WebSocket frames are logged and forwarded to the real server.

Example:
  python server/ws_8080_sniffer.py --listen-port 8080 --target-base ws://127.0.0.1:8081

If the client connects to ws://host:8080/ws, this script forwards to
ws://127.0.0.1:8081/ws by default.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Optional

from aiohttp import ClientSession, WSMsgType, web


LOGGER = logging.getLogger("ws_8080_sniffer")


def _format_payload(data: str) -> str:
    try:
        parsed = json.loads(data)
    except (TypeError, json.JSONDecodeError):
        return data
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True)


def _write_line(log_file: Optional[Path], line: str) -> None:
    print(line, flush=True)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _target_url(target_base: str, path_qs: str) -> str:
    base = target_base.rstrip("/")
    suffix = path_qs if path_qs.startswith("/") else f"/{path_qs}"
    return f"{base}{suffix}"


async def _pump_client_to_target(
    client_ws: web.WebSocketResponse,
    target_ws,
    conn_id: str,
    log_file: Optional[Path],
) -> None:
    async for msg in client_ws:
        if msg.type == WSMsgType.TEXT:
            payload = _format_payload(msg.data)
            _write_line(log_file, f"[{_now_ms()}] {conn_id} CLIENT -> TARGET {payload}")
            await target_ws.send_str(msg.data)
        elif msg.type == WSMsgType.BINARY:
            _write_line(log_file, f"[{_now_ms()}] {conn_id} CLIENT -> TARGET <binary {len(msg.data)} bytes>")
            await target_ws.send_bytes(msg.data)
        elif msg.type == WSMsgType.ERROR:
            LOGGER.warning("client websocket error conn=%s error=%s", conn_id, client_ws.exception())
            break
        elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
            break
    await target_ws.close()


async def _pump_target_to_client(
    target_ws,
    client_ws: web.WebSocketResponse,
    conn_id: str,
    log_file: Optional[Path],
) -> None:
    async for msg in target_ws:
        if msg.type == WSMsgType.TEXT:
            payload = _format_payload(msg.data)
            _write_line(log_file, f"[{_now_ms()}] {conn_id} TARGET -> CLIENT {payload}")
            await client_ws.send_str(msg.data)
        elif msg.type == WSMsgType.BINARY:
            _write_line(log_file, f"[{_now_ms()}] {conn_id} TARGET -> CLIENT <binary {len(msg.data)} bytes>")
            await client_ws.send_bytes(msg.data)
        elif msg.type == WSMsgType.ERROR:
            LOGGER.warning("target websocket error conn=%s error=%s", conn_id, target_ws.exception())
            break
        elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
            break
    await client_ws.close()


async def handle_websocket(request: web.Request) -> web.StreamResponse:
    if request.headers.get("Upgrade", "").lower() != "websocket":
        return web.Response(
            status=426,
            text="This sniffer only handles WebSocket upgrade requests.\n",
        )

    app = request.app
    target_base = app["target_base"]
    log_file = app["log_file"]
    conn_id = f"{request.remote or 'unknown'}#{_now_ms()}"
    target = _target_url(target_base, request.rel_url.raw_path_qs)

    client_ws = web.WebSocketResponse(heartbeat=30)
    await client_ws.prepare(request)

    _write_line(log_file, f"[{_now_ms()}] {conn_id} CONNECT path={request.rel_url} target={target}")

    try:
        async with ClientSession() as session:
            async with session.ws_connect(target, heartbeat=30) as target_ws:
                await asyncio.gather(
                    _pump_client_to_target(client_ws, target_ws, conn_id, log_file),
                    _pump_target_to_client(target_ws, client_ws, conn_id, log_file),
                )
    except Exception as exc:
        _write_line(log_file, f"[{_now_ms()}] {conn_id} ERROR {type(exc).__name__}: {exc}")
        await client_ws.close(message=str(exc).encode("utf-8"))
    finally:
        _write_line(log_file, f"[{_now_ms()}] {conn_id} DISCONNECT")

    return client_ws


async def start_server(args: argparse.Namespace) -> None:
    app = web.Application()
    app["target_base"] = args.target_base
    app["log_file"] = Path(args.log_file) if args.log_file else None
    app.router.add_get("/{tail:.*}", handle_websocket)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, args.listen_host, args.listen_port)
    await site.start()

    LOGGER.info(
        "listening on ws://%s:%s and forwarding to %s",
        args.listen_host,
        args.listen_port,
        args.target_base,
    )
    if app["log_file"]:
        LOGGER.info("writing captured frames to %s", app["log_file"])

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
    parser = argparse.ArgumentParser(description="Listen on port 8080 and log proxied WebSocket messages.")
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=8080)
    parser.add_argument("--target-base", default="ws://127.0.0.1:8081")
    parser.add_argument("--log-file", default="server/logs/ws_8080_sniffer.log")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(start_server(args))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
