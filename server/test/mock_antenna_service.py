#!/usr/bin/env python3
"""
Mock service for antenna round websocket testing.

Run:
  python server/test/mock_antenna_service.py

Endpoints:
  - WS  /ws/antenna-adjustment
  - POST /api/antenna-adjustment-status (compat)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from datetime import datetime
from typing import Any, Dict, Set

from aiohttp import WSMsgType, web


def _cors_headers() -> Dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


async def options_handler(_: web.Request) -> web.Response:
    return web.Response(status=204, headers=_cors_headers())


async def antenna_status_handler(request: web.Request) -> web.Response:
    """HTTP compat endpoint."""
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception:
        return web.json_response(
            {"ok": False, "message": "Invalid JSON payload"},
            status=400,
            headers=_cors_headers(),
        )

    print(f"[{_now()}] HTTP /api/antenna-adjustment-status <- {json.dumps(payload, ensure_ascii=False)}")
    await asyncio.sleep(3)

    response_body = {
        "ok": True,
        "should_flash": random.choice([True, False]),
        "duration_ms": 3000,
        "message": "mock delayed http response",
        "serverTime": _now(),
    }
    print(f"[{_now()}] HTTP /api/antenna-adjustment-status -> {json.dumps(response_body, ensure_ascii=False)}")
    return web.json_response(response_body, headers=_cors_headers())


async def _delayed_ws_push(ws: web.WebSocketResponse, payload: Dict[str, Any], delay_sec: float = 3.0) -> None:
    await asyncio.sleep(delay_sec)
    if ws.closed:
        return

    response_body = {
        "type": "round_feedback",
        "should_flash": random.choice([True, False]),
        "duration_ms": 3000,
        "message": "mock delayed ws feedback",
        "echo": {
            "box_visible": payload.get("box_visible"),
            "task_name": payload.get("task_name"),
            "user_id": payload.get("user_id"),
        },
        "serverTime": _now(),
    }
    await ws.send_str(json.dumps(response_body, ensure_ascii=False))
    print(f"[{_now()}] WS /ws/antenna-adjustment -> {json.dumps(response_body, ensure_ascii=False)}")


async def antenna_ws_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    print(f"[{_now()}] WS client connected: /ws/antenna-adjustment")

    delayed_tasks: Set[asyncio.Task] = set()

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except Exception:
                    await ws.send_str(json.dumps({"type": "error", "message": "invalid json"}, ensure_ascii=False))
                    continue

                print(f"[{_now()}] WS /ws/antenna-adjustment <- {json.dumps(data, ensure_ascii=False)}")
                msg_type = data.get("type")

                if msg_type == "start_round":
                    task = asyncio.create_task(_delayed_ws_push(ws, data, 3.0))
                    delayed_tasks.add(task)
                    task.add_done_callback(lambda t: delayed_tasks.discard(t))
                elif msg_type == "update_bbox":
                    await ws.send_str(json.dumps({"type": "ack", "message": "bbox updated"}, ensure_ascii=False))
                elif msg_type == "end_round":
                    await ws.send_str(json.dumps({"type": "ack", "message": "round ended"}, ensure_ascii=False))
                else:
                    await ws.send_str(json.dumps({"type": "ack", "message": "unknown message type"}, ensure_ascii=False))

            elif msg.type == WSMsgType.ERROR:
                print(f"[{_now()}] WS connection error: {ws.exception()}")
                break
    finally:
        for task in list(delayed_tasks):
            task.cancel()
        print(f"[{_now()}] WS client disconnected: /ws/antenna-adjustment")

    return ws


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_route("OPTIONS", "/api/antenna-adjustment-status", options_handler)
    app.router.add_post("/api/antenna-adjustment-status", antenna_status_handler)
    app.router.add_get("/ws/antenna-adjustment", antenna_ws_handler)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock antenna websocket/http service")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", default=8081, type=int, help="Port to bind (default: 8081)")
    args = parser.parse_args()

    print(f"[{_now()}] mock antenna service listening at http://{args.host}:{args.port}")
    web.run_app(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
