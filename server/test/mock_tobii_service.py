#!/usr/bin/env python3
"""
Mock Tobii websocket service for frontend antenna-round testing.

Run:
  python server/test/mock_tobii_service.py

Default endpoint:
  ws://127.0.0.1:8082/

Protocol (compatible with current frontend):
  - Client sends: {"type":"hand", "box_visible": true, ...}
    Server replies with task_id and starts periodic flash feedback.
  - Server pushes every 5s:
    {"type":"attention_feedback","action":"flash_mode","should_flash":true,...}
  - Client sends: {"type":"hand", "box_visible": false, "task_id":"..."}
    Server replies:
    {"ok": true, "msg": "窗口消失，任务结束", ...}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from aiohttp import WSMsgType, web


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


async def _periodic_flash_push(
    ws: web.WebSocketResponse,
    task_id: str,
    interval_sec: float = 5.0,
    duration_ms: int = 3000,
) -> None:
    """Push flash feedback periodically while the connection is alive."""
    try:
        while not ws.closed:
            await asyncio.sleep(interval_sec)
            if ws.closed:
                return

            payload = {
                "ok": True,
                "type": "attention_feedback",
                "action": "flash_mode",
                "should_flash": True,
                "duration_ms": duration_ms,
                "reason": "mock_periodic_feedback",
                "task_id": task_id,
                "serverTime": _now(),
            }
            await ws.send_str(json.dumps(payload, ensure_ascii=False))
            print(f"[{_now()}] WS -> {json.dumps(payload, ensure_ascii=False)}")
    except asyncio.CancelledError:
        return


async def _handle_hand_message(
    ws: web.WebSocketResponse,
    data: Dict[str, Any],
    current_task_id: Optional[str],
    flash_task: Optional[asyncio.Task],
) -> tuple[Optional[str], Optional[asyncio.Task]]:
    """Handle `type: hand` messages and return updated task state."""
    box_visible = bool(data.get("box_visible"))

    if box_visible:
        task_id = str(uuid.uuid4())
        ack = {
            "ok": True,
            "msg": "窗口出现，任务开始",
            "task_id": task_id,
            "serverTime": _now(),
        }
        await ws.send_str(json.dumps(ack, ensure_ascii=False))
        print(f"[{_now()}] WS -> {json.dumps(ack, ensure_ascii=False)}")

        if flash_task:
            flash_task.cancel()
        flash_task = asyncio.create_task(_periodic_flash_push(ws, task_id, interval_sec=5.0))
        return task_id, flash_task

    # box_visible = false => end round
    task_id = data.get("task_id") or current_task_id
    if not task_id:
        nack = {
            "ok": False,
            "msg": "窗口消失时必须传 task_id",
            "serverTime": _now(),
        }
        await ws.send_str(json.dumps(nack, ensure_ascii=False))
        print(f"[{_now()}] WS -> {json.dumps(nack, ensure_ascii=False)}")
        return current_task_id, flash_task

    if flash_task:
        flash_task.cancel()
        flash_task = None

    ack = {
        "ok": True,
        "msg": "窗口消失，任务结束",
        "task_id": str(task_id),
        "serverTime": _now(),
    }
    await ws.send_str(json.dumps(ack, ensure_ascii=False))
    print(f"[{_now()}] WS -> {json.dumps(ack, ensure_ascii=False)}")
    return None, flash_task


async def ws_root_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    print(f"[{_now()}] WS client connected: /")

    current_task_id: Optional[str] = None
    flash_task: Optional[asyncio.Task] = None

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data: Dict[str, Any] = json.loads(msg.data)
                except Exception:
                    err = {"ok": False, "msg": "invalid json", "serverTime": _now()}
                    await ws.send_str(json.dumps(err, ensure_ascii=False))
                    continue

                print(f"[{_now()}] WS <- {json.dumps(data, ensure_ascii=False)}")
                msg_type = data.get("type")
                if msg_type != "hand":
                    ack = {
                        "ok": True,
                        "msg": f"ignored message type: {msg_type}",
                        "serverTime": _now(),
                    }
                    await ws.send_str(json.dumps(ack, ensure_ascii=False))
                    continue

                current_task_id, flash_task = await _handle_hand_message(
                    ws=ws,
                    data=data,
                    current_task_id=current_task_id,
                    flash_task=flash_task,
                )

            elif msg.type == WSMsgType.ERROR:
                print(f"[{_now()}] WS error: {ws.exception()}")
                break
    finally:
        if flash_task:
            flash_task.cancel()
        print(f"[{_now()}] WS client disconnected: /")

    return ws


def create_app() -> web.Application:
    app = web.Application()
    # Frontend currently connects to ws://localhost:8082 (root path).
    app.router.add_get("/", ws_root_handler)
    # Add /ws alias for convenience.
    app.router.add_get("/ws", ws_root_handler)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock Tobii websocket service")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", default=8082, type=int, help="Port to bind (default: 8082)")
    args = parser.parse_args()

    print(f"[{_now()}] mock tobii service listening at ws://{args.host}:{args.port}/")
    web.run_app(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
