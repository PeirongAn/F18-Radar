"""
Tobii 眼动服务器入口

架构:
  GazeService  ——  核心业务（设备、数据、任务、文件写入）
       │
  ┌────┴─────┐
  HTTPServer  WebSocketServer
  (Flask)    (websockets)

数据存储：
  server/data/gaze/gaze_records.db 保存任务元数据、markers、targets、feedback 和统计
  server/data/gaze/raw/{user_id}/{task_id}/raw_gaze.jsonl 保存高频逐帧注视数据

任务 ID 联动：前端收到主服务器的 task_id（整数）后，
在调用 /tobii/hand（box_visible=true）或 WS hand 消息时
一起传入 task_id 字段，tobii 服务器将用该 ID 命名文件目录。

其他服务只需 import GazeService 即可复用眼动能力。
"""

import os
import threading
import asyncio
import time
import json
import logging

from flask import Flask, request, jsonify
import websockets

from gaze_service import GazeService
from test_ui import tobii_test_ui_html

# 眼动数据默认存储目录（相对于本文件向上两级到 server/data/gaze）
_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_DIR = os.path.join(_HERE, "..", "..", "server", "data", "gaze")


# ─────────────────────────────────────────────────────────────
# HTTP Server
# ─────────────────────────────────────────────────────────────

class HTTPServer:
    def __init__(self, host: str, port: int, gaze_service: GazeService):
        self.host = host
        self.port = port
        self._svc = gaze_service
        self.app = Flask(__name__)
        self._setup_routes()

    def _setup_routes(self):
        svc = self._svc

        @self.app.route("/")
        def index():
            return "Tobii Server Running"

        @self.app.route("/tobii/test-ui", methods=["GET"])
        def tobii_test_ui():
            return tobii_test_ui_html()

        @self.app.route("/tobii/test", methods=["POST"])
        def tobii_test():
            data = request.get_json()
            if data is None:
                return jsonify({"ok": False, "msg": "请求体必须是 JSON"}), 400
            print("收到前端请求:", data)
            return jsonify({"ok": True, "msg": "请求接收成功", "data": data})

        @self.app.route("/tobii/hand", methods=["POST"])
        def tobii_hand():
            data = request.get_json()
            if data is None:
                return jsonify({"ok": False, "msg": "请求体必须是 JSON"}), 400
            self.app.logger.warning(
                "[TOBII_HAND_REQUEST] POST /tobii/hand payload=%s",
                json.dumps(data, ensure_ascii=False, default=str),
            )
            if "box_visible" not in data:
                return jsonify({"ok": False, "msg": "缺少字段: box_visible"}), 400

            box_visible = bool(data.get("box_visible"))
            system_time = data.get("system_time", int(time.time() * 1_000_000))
            user_id = data.get("user_id", "")
            task_source = data.get("task_source", "")
            task_name = data.get("task_name", "")
            print("收到前端请求:", data)

            if box_visible:
                bbox = data.get("bbox") or []
                regions = data.get("regions")
                coordinate_space = data.get("coordinate_space")
                screen_data = data.get("screen_data")
                if not isinstance(screen_data, (list, tuple)) or len(screen_data) < 2:
                    screen_data = None
                # 优先使用前端传入的主服务器 task_id，不传则自动生成
                external_task_id = data.get("task_id")

                task_id = svc.start_task(
                    bbox=bbox,
                    screen_size=screen_data,
                    task_id=external_task_id,
                    user_id=user_id,
                    task_source=task_source,
                    task_name=task_name,
                    system_time=system_time,
                    regions=regions if isinstance(regions, list) else None,
                    coordinate_space=coordinate_space if isinstance(coordinate_space, str) else None,
                )
                return jsonify({"ok": True, "msg": "窗口出现，任务开始", "task_id": task_id})

            else:
                task_id = data.get("task_id") or svc.get_active_task_id()
                if not task_id:
                    return jsonify({"ok": False, "msg": "窗口消失时必须传 task_id"}), 400

                try:
                    result = svc.stop_task(
                        task_id=task_id,
                        user_id=user_id,
                        task_source=task_source,
                        task_name=task_name,
                        system_time=system_time,
                    )
                except ValueError as e:
                    return jsonify({"ok": False, "msg": str(e)}), 400

                return jsonify({
                    "ok": True,
                    "msg": "窗口消失，任务结束",
                    "task_id": result["task_id"],
                    "task_info": result["task_info"],
                })

        @self.app.route("/tobii/marker", methods=["POST"])
        def tobii_marker():
            data = request.get_json()
            if data is None:
                return jsonify({"ok": False, "msg": "request body must be JSON"}), 400
            try:
                marker = svc.record_marker(
                    name=data.get("name") or data.get("marker") or data.get("event") or "",
                    payload=data.get("payload") if isinstance(data.get("payload"), dict) else {},
                    task_id=data.get("task_id"),
                    user_id=data.get("user_id", ""),
                    system_time=data.get("system_time"),
                )
            except ValueError as e:
                return jsonify({"ok": False, "msg": str(e)}), 400
            except Exception as e:
                return jsonify({"ok": False, "msg": str(e)}), 500
            return jsonify({"ok": True, "type": "tobii_marker_result", "marker": marker})

        @self.app.route("/tobii/gaze_point", methods=["GET"])
        def get_gaze_point():
            point, ts = svc.get_latest_gaze_point()
            if point is None:
                return jsonify({"ok": False, "msg": "注视点数据不可用或已过期"}), 404
            return jsonify({"ok": True, "gaze_point": point, "timestamp": ts})

        @self.app.route("/tobii/gaze_data", methods=["GET"])
        def get_gaze_data():
            def query_int(name, default, min_value, max_value):
                try:
                    value = int(request.args.get(name, str(default)))
                except (TypeError, ValueError):
                    value = default
                return max(min_value, min(max_value, value))

            max_age_ms = query_int("max_age_ms", 1000, 1, 60000)
            limit = query_int("limit", 60, 0, 600)
            point, ts = svc.get_latest_gaze_point(max_age_ms=max_age_ms)
            window = svc.get_gaze_window_snapshot()
            if limit:
                window = window[-limit:]
            screen_size = svc.get_screen_size()
            return jsonify({
                "ok": point is not None,
                "msg": None if point is not None else "gaze point unavailable or expired",
                "gaze_point": point,
                "timestamp": ts,
                "active_task_id": svc.get_active_task_id(),
                "screen_size": list(screen_size) if screen_size else None,
                "window": window,
                "window_count": len(window),
                "max_age_ms": max_age_ms,
            })

    def start(self):
        print(f"[HTTPServer] 启动于 {self.host}:{self.port}")
        self.app.run(host=self.host, port=self.port, debug=False)


# ─────────────────────────────────────────────────────────────
# WebSocket Server
# ─────────────────────────────────────────────────────────────

class WebSocketServer:
    def __init__(self, host: str, port: int, gaze_service: GazeService):
        self.host = host
        self.port = port
        self._svc = gaze_service
        self.logger = logging.getLogger("tobii.websocket")

    async def _handle_client(self, websocket):
        self._svc.register_ws_client(websocket)
        try:
            async for raw in websocket:
                try:
                    data = json.loads(raw)
                    await self._process_message(websocket, data)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({"ok": False, "msg": "无效的 JSON 格式"}))
        except websockets.ConnectionClosed:
            pass
        finally:
            self._svc.unregister_ws_client(websocket)

    async def _process_message(self, websocket, data: dict):
        svc = self._svc
        msg_type = data.get("type")

        try:
            if msg_type == "test":
                await websocket.send(json.dumps({"ok": True, "msg": "请求接收成功", "data": data}))

            elif msg_type == "hand":
                self.logger.warning(
                    "[TOBII_HAND_REQUEST] WS hand payload=%s",
                    json.dumps(data, ensure_ascii=False, default=str),
                )
                if "box_visible" not in data:
                    await websocket.send(json.dumps({"ok": False, "msg": "缺少字段: box_visible"}))
                    return

                box_visible = bool(data.get("box_visible"))
                system_time = data.get("system_time", int(time.time() * 1_000_000))
                user_id = data.get("user_id", "")
                task_source = data.get("task_source", "")
                task_name = data.get("task_name", "")

                if box_visible:
                    print("[WS] 目标出现:", data)
                    bbox = data.get("bbox") or []
                    regions = data.get("regions")
                    coordinate_space = data.get("coordinate_space")
                    screen_data = data.get("screen_data")
                    if not isinstance(screen_data, (list, tuple)) or len(screen_data) < 2:
                        screen_data = None
                    # 优先使用前端传入的主服务器 task_id，不传则自动生成
                    external_task_id = data.get("task_id")

                    task_id = svc.start_task(
                        bbox=bbox,
                        screen_size=screen_data,
                        task_id=external_task_id,
                        user_id=user_id,
                        task_source=task_source,
                        task_name=task_name,
                        system_time=system_time,
                        regions=regions if isinstance(regions, list) else None,
                        coordinate_space=coordinate_space if isinstance(coordinate_space, str) else None,
                    )
                    await websocket.send(json.dumps({
                        "ok": True, "msg": "窗口出现，任务开始", "task_id": task_id
                    }))

                else:
                    print("[WS] 窗口消失:", data)
                    task_id = data.get("task_id") or svc.get_active_task_id()
                    if not task_id:
                        await websocket.send(json.dumps({"ok": False, "msg": "窗口消失时必须传 task_id"}))
                        return

                    try:
                        result = svc.stop_task(
                            task_id=task_id,
                            user_id=user_id,
                            task_source=task_source,
                            task_name=task_name,
                            system_time=system_time,
                        )
                    except ValueError as e:
                        await websocket.send(json.dumps({"ok": False, "msg": str(e)}))
                        return

                    await websocket.send(json.dumps({
                        "ok": True,
                        "msg": "窗口消失，任务结束",
                        "task_id": result["task_id"],
                        "task_info": result["task_info"],
                    }))

            elif msg_type in {"marker", "tobii_marker"}:
                try:
                    marker = svc.record_marker(
                        name=data.get("name") or data.get("marker") or data.get("event") or "",
                        payload=data.get("payload") if isinstance(data.get("payload"), dict) else {},
                        task_id=data.get("task_id"),
                        user_id=data.get("user_id", ""),
                        system_time=data.get("system_time"),
                    )
                except ValueError as e:
                    await websocket.send(json.dumps({"type": "tobii_marker_result", "ok": False, "msg": str(e)}))
                    return
                await websocket.send(json.dumps({
                    "type": "tobii_marker_result",
                    "ok": True,
                    "marker": marker,
                }))

            elif msg_type == "gaze_point":
                point, ts = svc.get_latest_gaze_point()
                if point is None:
                    await websocket.send(json.dumps({"ok": False, "msg": "注视点数据不可用或已过期"}))
                else:
                    await websocket.send(json.dumps({"ok": True, "gaze_point": point, "timestamp": ts}))

            else:
                await websocket.send(json.dumps({"ok": False, "msg": "未知的消息类型"}))

        except Exception as e:
            print(f"[WS] 处理消息出错: {e}")
            await websocket.send(json.dumps({"ok": False, "msg": f"服务器内部错误: {e}"}))

    async def _run(self):
        self._svc.set_ws_event_loop(asyncio.get_running_loop())
        print(f"[WebSocketServer] 启动于 {self.host}:{self.port}")
        async with websockets.serve(self._handle_client, self.host, self.port):
            await asyncio.Future()

    def start(self):
        asyncio.run(self._run())


# ─────────────────────────────────────────────────────────────
# 程序入口
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # 1. 创建服务实例（文件存储替代数据库）
    gaze_svc = GazeService(data_dir=DEFAULT_DATA_DIR)

    # 2. 连接眼动仪
    gaze_svc.connect()

    # 3. 启动 HTTP 服务（后台线程）
    http_server = HTTPServer("0.0.0.0", 8081, gaze_svc)
    http_thread = threading.Thread(target=http_server.start, daemon=True)
    http_thread.start()

    # 4. 启动 WebSocket 服务（主线程，阻塞）
    try:
        ws_server = WebSocketServer("0.0.0.0", 8082, gaze_svc)
        ws_server.start()
    finally:
        gaze_svc.shutdown()
