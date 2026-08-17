import os
import asyncio
import uuid
from aiohttp import web, WSMsgType
from aiohttp.web_ws import WebSocketResponse
import json
import time
import sys



# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from managers import config_manager, target_manager, db_manager, get_logger
from runtime_paths import WEB_DIR
from core import message_handler
from network.netlog import (
    duration_ms,
    http_request_summary,
    log_http,
    log_ws_connect,
    log_ws_disconnect,
    log_ws_message,
    log_ws_send,
    now_ms,
    remote_from_request,
    should_log_http,
    should_log_ws_message,
)

class HTTPServer:
    """HTTP服务器，同时支持静态文件服务和WebSocket连接"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8080, static_dir: str = None):
        self.host = host
        self.port = port
        self.static_dir = static_dir or str(WEB_DIR)
        self.logger = get_logger("http_server")
        self.app = web.Application(middlewares=[self._interface_log_middleware])
        self._routes_setup = False
        self.joystick_handler = None
        self._gaze_svc = None
        self._physio_svc = None
        self._external_collectors = None
        self._runner = None
        self._setup_routes()
        self.seen_users = set()
        # 新增
        self.WS_URL = "ws://localhost:8080/ws"
        self.DEFAULT_CONFIG_TIMEOUT = 5 # 重连时间
        self.DEFAULT_PAYLOAD = {
            "userId": "test_pilot_103",
            "includeAI": True,
            "isPractice": False,# 固定
            "current_difficulty": "high",# hig, low
            "audio_enabled": False# 高工效 true
        }

    @web.middleware
    async def _interface_log_middleware(self, request, handler):
        if not should_log_http(request.path, request.method):
            return await handler(request)

        req_id = getattr(request, "request_id", None) or str(uuid.uuid4())[:8]
        request["request_id"] = req_id
        start_ms = now_ms()
        summary = await http_request_summary(request)
        status = 500

        try:
            response = await handler(request)
            status = getattr(response, "status", 200)
            return response
        except web.HTTPException as exc:
            status = exc.status
            raise
        except Exception:
            status = 500
            raise
        finally:
            log_http(self.logger, req_id, request, status, duration_ms(start_ms), summary)

    
    def set_joystick_handler(self, handler):
        """设置操纵杆事件处理器"""
        self.joystick_handler = handler

    def set_gaze_service(self, gaze_svc) -> None:
        """注入眼动追踪服务（由 server/main.py 的 initialize_system 调用）。"""
        self._gaze_svc = gaze_svc

    def set_physio_service(self, physio_svc) -> None:
        """Inject the optional physiological recording service."""
        self._physio_svc = physio_svc

    def set_external_collector_manager(self, external_collectors) -> None:
        """Inject optional external physiological collector integrations."""
        self._external_collectors = external_collectors
    
    def _setup_routes(self):
        """设置路由"""
        # 避免重复设置路由
        if self._routes_setup:
            return
            
        # WebSocket路由
        self.app.router.add_get('/ws', self.websocket_handler)

        # 问卷提交路由
        self.app.router.add_post('/api/questionnaire', self.questionnaire_submit_handler)
        self.app.router.add_get('/api/questionnaire/context', self.questionnaire_context_handler)
        self.app.router.add_get('/api/trust-history', self.trust_history_handler)

        # 眼动追踪路由
        self.app.router.add_get('/tobii/test-ui', self.tobii_test_ui_handler)
        self.app.router.add_post('/tobii/hand', self.tobii_hand_handler)
        self.app.router.add_post('/tobii/marker', self.tobii_marker_handler)
        self.app.router.add_get('/tobii/gaze_point', self.tobii_gaze_point_handler)
        self.app.router.add_get('/tobii/gaze_data', self.tobii_gaze_data_handler)
        self.app.router.add_get('/physio/check', self.physio_check_handler)
        self.app.router.add_get('/physio/dashboard', self.physio_dashboard_handler)
        self.app.router.add_get('/api/physio/status', self.physio_status_handler)
        self.app.router.add_post('/api/physio/export', self.physio_export_handler)
        self.app.router.add_get('/api/external-collectors/status', self.external_collectors_status_handler)
        self.app.router.add_get('/api/external-collectors/files', self.external_collectors_files_handler)

        # 静态文件路由
        self._setup_static_routes()
        
        self._routes_setup = True
    
    def _setup_static_routes(self):
        """设置静态文件路由"""
        if os.path.exists(self.static_dir):
            # 添加静态文件路由
            self.app.router.add_get('/', self.index_handler)
            self.app.router.add_static('/', self.static_dir, name='static', show_index=False)
            
            # 添加SPA fallback处理器 - 对于所有未找到的路由，返回index.html
            self.app.router.add_route('*', '/{path:.*}', self.spa_fallback_handler)
            
            self.logger.info(f"静态文件目录: {self.static_dir}")
            self.logger.info("已启用SPA模式，未匹配的路由将自动返回 index.html")
        else:
            self.logger.warning(f"静态文件目录不存在: {self.static_dir}")
            # 添加默认路由返回404
            self.app.router.add_get('/', self.not_found_handler)
    
    async def spa_fallback_handler(self, request):
        """SPA fallback处理器，为所有未找到的路由返回index.html"""
        # 检查请求的路径是否是API或WebSocket路径
        path = request.path
        if path.startswith('/ws') or path.startswith('/api') or path.startswith('/physio'):
            raise web.HTTPNotFound()
        
        # 检查是否请求的是静态资源文件（有文件扩展名）
        if '.' in os.path.basename(path) and not path.endswith('.html'):
            # 尝试返回实际的静态文件
            file_path = os.path.join(self.static_dir, path.lstrip('/'))
            if os.path.exists(file_path) and os.path.isfile(file_path):
                return web.FileResponse(file_path)
            else:
                raise web.HTTPNotFound()
        
        # 对于所有其他路径（包括根路径和SPA路由），返回index.html
        index_path = os.path.join(self.static_dir, 'index.html')
        
        if os.path.exists(index_path):
            return web.FileResponse(index_path)
        else:
            self.logger.warning(f"index.html不存在: {index_path}")
            return web.Response(
                text=f"index.html不存在: {index_path}\n请确保前端项目已正确构建",
                status=404
            )
    
    def update_static_directory(self, new_static_dir: str):
        """更新静态文件目录"""
        self.static_dir = new_static_dir
        self.logger.info(f"更新静态文件目录为: {self.static_dir}")
        
        # 清除现有的静态路由
        if self._routes_setup:
            # 创建新的应用实例以避免路由冲突
            self.app = web.Application(middlewares=[self._interface_log_middleware])
            self._runner = None
            self._routes_setup = False
            self._setup_routes()
    
    async def not_found_handler(self, request):
        """处理找不到静态文件的情况"""
        return web.Response(
            text=f"静态文件目录不存在: {self.static_dir}\n请确保前端文件已打包到此目录",
            status=404
        )
    
    async def index_handler(self, request):
        """处理根路径请求，自动返回index.html"""
        index_path = os.path.join(self.static_dir, 'index.html')
        
        if os.path.exists(index_path):
            try:
                # 读取index.html文件
                with open(index_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 返回HTML响应
                return web.Response(
                    text=content,
                    content_type='text/html',
                    charset='utf-8'
                )
            except Exception as e:
                self.logger.error(f"读取index.html失败: {e}")
                return web.Response(
                    text=f"无法读取index.html: {e}",
                    status=500
                )
        else:
            self.logger.warning(f"index.html不存在: {index_path}")
            return web.Response(
                text=f"index.html不存在: {index_path}\n请确保前端项目已正确构建",
                status=404
            )

    def _log_ws_request(self, client_id: str, message: str, message_data=None) -> None:
        """记录收到的 WebSocket 请求摘要到统一日志。"""
        log_ws_message(self.logger, client_id, "/ws", message, message_data)

    async def _send_platform_task_reply(self, ws, client_id: str, reply: dict) -> None:
        try:
            await ws.send_str(json.dumps(reply, ensure_ascii=False))
        except Exception as exc:
            log_ws_send(
                self.logger,
                client_id,
                "/ws",
                reply,
                success=False,
                error=str(exc),
            )
            raise
        log_ws_send(self.logger, client_id, "/ws", reply, success=True)
    
    async def websocket_handler(self, request):
        """处理WebSocket连接"""
        # Close WebSocket peers that stop answering control-frame heartbeats.
        # The connection is then removed from websocket_server in finally.
        ws = WebSocketResponse(protocols=("ws",), heartbeat=30.0)
        await ws.prepare(request)
        
        client_id = str(uuid.uuid4())
        ws_start_ms = now_ms()
        ws_remote = remote_from_request(request)
        session_state = {}
        
        # 将连接注册到 websocket_server，使操纵杆数据广播能找到此客户端
        from network import websocket_server
        websocket_server.add_client(client_id, ws, log_event=False, endpoint="/ws", remote=ws_remote)
        log_ws_connect(
            self.logger,
            client_id,
            "/ws",
            ws_remote,
            websocket_server.get_client_count(),
        )

        # 首个客户端连接时自动触发系统初始化（包括眼动服务）
        from main import initialize_system, _initialized
        if not _initialized:
            try:
                await initialize_system()
            except Exception as e:
                self.logger.error(f"首次连接延迟初始化失败: {e}")

        gaze_client_registered = False
        if self._gaze_svc is not None:
            self._gaze_svc.set_ws_event_loop(asyncio.get_running_loop())
            self._gaze_svc.register_ws_client(ws)
            gaze_client_registered = True

        try:
            # 消息处理循环
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    message = msg.data
                  # 检查是否为操纵杆相关消息
                    try:
                        message_data = json.loads(message)
                        message_type = message_data.get('type', '')
                    except json.JSONDecodeError:
                        message_data = None
                        message_type = ''

                    if should_log_ws_message(message_data):
                        self.logger.info("RAW WebSocket message client=%s: %s", client_id, message)
                        self.logger.debug("接收到WebSocket消息")
                        self._log_ws_request(client_id, message, message_data)

                    # UE has an application-level heartbeat too.  Reply on
                    # the same connection rather than via the broadcast path,
                    # which deliberately excludes the message sender.
                    if message_type == 'ue_ping':
                        session_state['client_role'] = 'ue'
                        await ws.send_str(json.dumps({
                            'type': 'ue_pong',
                            'timestamp': int(time.time() * 1000),
                        }, ensure_ascii=False))
                        continue
                    
                    # 1) 如果收到的是config_update
                    if  message_type == "config_update":
                        cfg_msg = {"type": "config_update", **message_data}
                        self.logger.info(f"收到payload，执行配置更新: {json.dumps(cfg_msg, ensure_ascii=False)}")
                        print("根据json处理了更新")
                        try:
                            from network.external_ws_receiver import apply_config_update
                            changes = apply_config_update(cfg_msg)

                            await ws.send_str(json.dumps({
                                "type": "config_update_result",
                                "status": "ok",
                                "changes": changes
                            }, ensure_ascii=False))

                        except Exception as e:
                            self.logger.error(f"配置更新失败: {e}", exc_info=True)
                            await ws.send_str(json.dumps({
                                "type": "config_update_result",
                                "status": "error",
                                "message": str(e)
                            }, ensure_ascii=False))
                        
                        continue  # 处理完毕，进入下一条

                    is_platform_packet = (
                        message_type == 'platform_task' or
                        (not message_type and
                         message_data and
                         message_data.get('TaskName') and
                         str(message_data.get('ID', '')).strip())
                    )
                    if is_platform_packet:
                        from network.platform_task_bridge import handle_platform_task_ws
                        for reply in await handle_platform_task_ws(
                            websocket_server,
                            client_id,
                            message_data,
                            gaze_svc=self._gaze_svc,
                            physio_svc=self._physio_svc,
                            external_collectors=self._external_collectors,
                        ):
                            await self._send_platform_task_reply(ws, client_id, reply)
                        continue

                    if message_type == 'platform_task_result':
                        from network.platform_task_bridge import handle_platform_task_result_ws
                        for reply in handle_platform_task_result_ws(
                            message_data,
                            gaze_svc=self._gaze_svc,
                            physio_svc=self._physio_svc,
                            external_collectors=self._external_collectors,
                        ):
                            await self._send_platform_task_reply(ws, client_id, reply)
                        continue

                    if message_type in {'external_pose_record', 'external_pose_data'}:
                        from network.external_pose_storage import handle_external_pose_record
                        reply = await asyncio.to_thread(
                            handle_external_pose_record,
                            message_data,
                        )
                        await self._send_platform_task_reply(ws, client_id, reply)
                        continue

                    if message_type == 'external_behavior_record':
                        from network.external_behavior_storage import handle_external_behavior_record
                        reply = await asyncio.to_thread(
                            handle_external_behavior_record,
                            message_data,
                        )
                        await self._send_platform_task_reply(ws, client_id, reply)
                        continue

                    if message_type == 'questionnaire_submitted':
                        message_data['source'] = message_data.get('source', 'websocket')
                        try:
                            db_manager.record_questionnaire(message_data)
                            await ws.send_str(json.dumps({
                                "type": "questionnaire_saved",
                                "ok": True,
                                "msg": "问卷已保存"
                            }, ensure_ascii=False))
                        except Exception as e:
                            self.logger.error(f"WebSocket 保存问卷失败: {e}", exc_info=True)
                            await ws.send_str(json.dumps({
                                "type": "questionnaire_saved",
                                "ok": False,
                                "msg": str(e)
                            }, ensure_ascii=False))
                        continue

                    # tobii_hand：当前前端连接的是 HTTP 服务器上的 /ws，
                    # 这里复用独立 WebSocketServer 的眼动 bbox 处理逻辑。
                    if message_type == 'tobii_hand':
                        reply = await websocket_server._handle_tobii_hand(message_data)
                        await ws.send_str(json.dumps(reply, ensure_ascii=False))
                        continue

                    if message_type == 'tobii_aoi_snapshot':
                        reply = await websocket_server._handle_tobii_aoi_snapshot(message_data)
                        await ws.send_str(json.dumps(reply, ensure_ascii=False))
                        continue

                    # 收到 joystick_connect 时触发延迟初始化
                    if message_type == 'tobii_marker':
                        reply = await websocket_server._handle_tobii_marker(message_data)
                        await ws.send_str(json.dumps(reply, ensure_ascii=False))
                        continue

                    if message_type == 'joystick_connect' and not self.joystick_handler:
                        try:
                            from main import initialize_system
                            await initialize_system()
                        except Exception as e:
                            self.logger.error(f"延迟初始化失败: {e}")

                    # 处理外部配置更新消息
                    if message_type == 'config_update':
                        try:
                            from network.external_ws_receiver import apply_config_update
                            changes = apply_config_update(message_data)
                            await ws.send_str(json.dumps({"type": "config_update_result", "status": "ok", "changes": changes}))
                        except Exception as e:
                            self.logger.error(f"配置更新失败: {e}", exc_info=True)
                            await ws.send_str(json.dumps({"type": "config_update_result", "status": "error", "message": str(e)}))
                        continue

                    if message_type.startswith('joystick_') and self.joystick_handler:
                        try:
                            joystick_result = await self.joystick_handler.handle_message(client_id, message_data)
                            await ws.send_str(json.dumps(joystick_result))
                            continue
                        except Exception as e:
                            self.logger.error(f"操纵杆消息处理失败: {e}")
                            await ws.send_str(json.dumps({
                                'type': 'error',
                                'message': f'操纵杆消息处理失败: {str(e)}'
                            }))
                            continue
                    
                    # 处理非操纵杆消息
                    result = await message_handler.handle_client_message(message, session_state, ws)

                    if message_type == 'task_exit_request' and isinstance(result, list):
                        for msg_data in result:
                            if isinstance(msg_data, dict) and msg_data.get('type') == 'task_exit_requested':
                                # The requester may be the UE-hosted questionnaire connection,
                                # so include it in the exit notification broadcast as well.
                                await websocket_server.broadcast_to_clients_except(msg_data, None)
                        continue
                    
                    # 发送响应
                    if isinstance(result, list):
                        for msg_data in result:
                            await ws.send_str(json.dumps(msg_data))
                    elif isinstance(result, tuple) and len(result) == 2:
                        settings_updated, include_targets = result
                        if settings_updated:
                            if 'type' in settings_updated and settings_updated['type'] == 'settings_validation':
                                await ws.send_str(json.dumps(settings_updated))
                            
                            # 发送主数据
                            data = target_manager.get_radar_data(include_targets=include_targets)
                            data["type"] = "radar_data"
                            if settings_updated.get("task_id") is not None:
                                data["task_id"] = settings_updated["task_id"]
                            data["_timestamp"] = time.time()
                            await ws.send_str(json.dumps(data))
                            
                elif msg.type == WSMsgType.ERROR:
                    self.logger.error(f'WebSocket错误: {ws.exception()}')
                    
        except Exception as e:
            self.logger.error(f"WebSocket处理错误: {e}", exc_info=True)
        finally:
            if gaze_client_registered and self._gaze_svc is not None:
                self._gaze_svc.unregister_ws_client(ws)
            websocket_server.remove_client(client_id, log_event=False)
            log_ws_disconnect(
                self.logger,
                client_id,
                "/ws",
                ws_remote,
                duration_ms(ws_start_ms),
                websocket_server.get_client_count(),
            )
            
        return ws
    
    async def physio_check_handler(self, request: web.Request) -> web.Response:
        """GET /physio/check - standalone pre-task physio service check page."""
        from physio.pages import check_page_html

        return web.Response(text=check_page_html(), content_type="text/html")

    async def physio_dashboard_handler(self, request: web.Request) -> web.Response:
        """GET /physio/dashboard - live physio monitor page."""
        from physio.pages import dashboard_html

        return web.Response(text=dashboard_html(), content_type="text/html")

    async def physio_status_handler(self, request: web.Request) -> web.Response:
        """GET /api/physio/status."""
        if self._physio_svc is None:
            try:
                from main import initialize_system
                await initialize_system()
            except Exception as e:
                self.logger.error(f"Physio service delayed initialization failed: {e}", exc_info=True)

        if self._physio_svc is None:
            return web.json_response({
                "ok": False,
                "enabled": False,
                "running": False,
                "error": "physio ring service is disabled or failed to initialize",
                "state": {},
                "collector": {"streams": {}, "warnings": ["Physio service is not available."]},
                "sample_storage": None,
                "sample_file": {},
                "formal_sample_count": 0,
            })
        try:
            return web.json_response(self._physio_svc.status_payload())
        except Exception as e:
            self.logger.error(f"Physio status failed: {e}", exc_info=True)
            return web.json_response({
                "ok": False,
                "enabled": True,
                "running": False,
                "error": str(e),
                "state": {},
                "collector": {"streams": {}, "warnings": [str(e)]},
                "sample_storage": None,
                "sample_file": {},
                "formal_sample_count": 0,
            }, status=500)

    async def physio_export_handler(self, request: web.Request) -> web.Response:
        """POST /api/physio/export."""
        if self._physio_svc is None:
            try:
                from main import initialize_system
                await initialize_system()
            except Exception as e:
                self.logger.error(f"Physio service delayed initialization failed: {e}", exc_info=True)

        if self._physio_svc is None:
            return web.json_response({"ok": False, "msg": "physio ring service is not available"}, status=503)
        try:
            data = await request.json()
        except Exception:
            data = {}
        try:
            result = self._physio_svc.export_data(
                subject_id=data.get("subject_id"),
                run_id=data.get("run_id"),
                trial_id=data.get("trial_id"),
            )
            return web.json_response({"ok": True, **result})
        except Exception as e:
            self.logger.error(f"Physio export failed: {e}", exc_info=True)
            return web.json_response({"ok": False, "msg": str(e)}, status=500)

    async def external_collectors_status_handler(self, request: web.Request) -> web.Response:
        """GET /api/external-collectors/status."""
        if self._external_collectors is None:
            try:
                from main import initialize_system
                await initialize_system()
            except Exception as e:
                self.logger.error(f"External collectors delayed initialization failed: {e}", exc_info=True)

        if self._external_collectors is None:
            return web.json_response({"ok": True, "enabled": False, "providers": {}})
        try:
            return web.json_response(self._external_collectors.status_payload())
        except Exception as e:
            self.logger.error(f"External collectors status failed: {e}", exc_info=True)
            return web.json_response({"ok": False, "enabled": True, "providers": {}, "error": str(e)}, status=500)

    async def external_collectors_files_handler(self, request: web.Request) -> web.Response:
        """GET /api/external-collectors/files?task_id=...&provider=..."""
        if self._external_collectors is None:
            try:
                from main import initialize_system
                await initialize_system()
            except Exception as e:
                self.logger.error(f"External collectors delayed initialization failed: {e}", exc_info=True)

        if self._external_collectors is None:
            return web.json_response({"ok": True, "enabled": False, "files": []})
        try:
            return web.json_response({
                "ok": True,
                "enabled": True,
                "files": self._external_collectors.task_files(
                    provider=request.query.get("provider"),
                    task_id=request.query.get("task_id"),
                ),
            })
        except Exception as e:
            self.logger.error(f"External collectors file lookup failed: {e}", exc_info=True)
            return web.json_response({"ok": False, "enabled": True, "files": [], "error": str(e)}, status=500)

    async def questionnaire_submit_handler(self, request: web.Request) -> web.Response:
        """POST /api/questionnaire — 保存问卷提交到数据库"""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "msg": "请求体必须是 JSON"}, status=400)

        if not data.get('answers'):
            return web.json_response({"ok": False, "msg": "缺少 answers 字段"}, status=400)

        if 'source' not in data:
            data['source'] = 'http_api'

        try:
            db_manager.record_questionnaire(data)
            self.logger.info("问卷已通过 HTTP 接口保存: user=%s task=%s",
                             data.get('userId'), data.get('taskType'))
            return web.json_response({"ok": True, "msg": "问卷已保存"})
        except Exception as e:
            self.logger.error(f"保存问卷失败: {e}", exc_info=True)
            return web.json_response({"ok": False, "msg": str(e)}, status=500)

    async def tobii_test_ui_handler(self, request: web.Request) -> web.Response:
        """GET /tobii/test-ui - standalone Tobii gaze test console."""
        from tobii.test_ui import tobii_test_ui_html

        return web.Response(text=tobii_test_ui_html(), content_type="text/html")

    async def tobii_marker_handler(self, request: web.Request) -> web.Response:
        """POST /tobii/marker - record a Tobii gaze marker."""
        if self._gaze_svc is None:
            try:
                from main import initialize_system
                await initialize_system()
            except Exception as e:
                self.logger.error(f"Tobii marker delayed initialization failed: {e}", exc_info=True)

        if self._gaze_svc is None:
            return web.json_response({"ok": False, "msg": "Tobii gaze service is not available"}, status=503)

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "msg": "request body must be JSON"}, status=400)

        try:
            marker = self._gaze_svc.record_marker(
                name=data.get("name") or data.get("marker") or data.get("event") or "",
                payload=data.get("payload") if isinstance(data.get("payload"), dict) else {},
                task_id=data.get("task_id"),
                user_id=data.get("user_id", ""),
                system_time=data.get("system_time"),
            )
        except ValueError as e:
            return web.json_response({"ok": False, "msg": str(e)}, status=400)
        except Exception as e:
            self.logger.error(f"Tobii marker failed: {e}", exc_info=True)
            return web.json_response({"ok": False, "msg": str(e)}, status=500)

        return web.json_response({"ok": True, "type": "tobii_marker_result", "marker": marker})

    async def trust_history_handler(self, request: web.Request) -> web.Response:
        """GET /api/trust-history — 聚合历史信任事件，供设置页展示样本状态。"""
        user_id = request.query.get('user_id') or None
        try:
            limit = int(request.query.get('limit', '500'))
        except ValueError:
            limit = 500
        try:
            minimum_sample_size = int(request.query.get('minimum_sample_size', '30'))
        except ValueError:
            minimum_sample_size = 30

        try:
            history = db_manager.get_trust_calibration_history(
                user_id=user_id,
                limit=limit,
                minimum_sample_size=minimum_sample_size,
            )
            return web.json_response({"ok": True, **history})
        except Exception as e:
            self.logger.error(f"读取信任历史失败: {e}", exc_info=True)
            return web.json_response({"ok": False, "msg": str(e)}, status=500)

    async def questionnaire_context_handler(self, request: web.Request) -> web.Response:
        """Return the authoritative completed task context for questionnaire display.

        URL query parameters other than task identity and control mode are ignored.
        Active, incomplete, and practice task groups are never eligible.
        """
        user_id = str(request.query.get('userId') or request.query.get('user_id') or '').strip()
        task_type = str(request.query.get('taskType') or request.query.get('task_type') or '').strip()
        task_group_id = request.query.get('taskGroupId') or request.query.get('task_group_id')
        control_mode = request.query.get('controlMode') or request.query.get('control_mode')
        context = db_manager.resolve_questionnaire_task_context(
            user_id,
            task_type,
            submitted_task_group_id=task_group_id,
            control_mode=control_mode,
        )
        if context.get('task_id') is None:
            return web.json_response({"ok": False, "msg": "no completed task context found"}, status=404)
        if not db_manager.is_questionnaire_context_eligible(context):
            reason = 'practice_task' if context.get('is_practice') else 'task_incomplete'
            return web.json_response({
                "ok": False,
                "reason": reason,
                "msg": "questionnaire is only available after a formal task group is completed",
            }, status=409)

        return web.json_response({
            "ok": True,
            "type": "questionnaire_context",
            "taskId": context.get('task_id'),
            "taskGroupId": context.get('task_group_id'),
            "userId": context.get('user_id') or user_id,
            "taskType": context.get('task_type') or task_type,
            "difficulty": context.get('difficulty'),
            "autonomyLevel": context.get('autonomy_level'),
            "controlMode": context.get('control_mode'),
            "isPractice": bool(context.get('is_practice')),
            "isAIActive": context.get('is_ai_active'),
            "experimentNo": context.get('repetition_current'),
            "total": context.get('repetition_total'),
        })

    async def tobii_hand_handler(self, request: web.Request) -> web.Response:
        """
        POST /tobii/hand

        前端在目标框出现（box_visible=true）或消失（box_visible=false）时调用。

        box_visible=true 时更新当前活动任务的注意力区域（bbox），
        不重新创建任务——任务已由主服务器在 task_start 时创建。

        请求体示例（出现）:
            {"box_visible": true, "task_id": 123, "bbox": [[x1,y1,x2,y2]]}
        请求体示例（消失）:
            {"box_visible": false, "task_id": 123}
        """
        if self._gaze_svc is None:
            return web.json_response({"ok": False, "msg": "眼动追踪服务未启动"}, status=503)

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "msg": "请求体必须是 JSON"}, status=400)

        self.logger.warning(
            "[TOBII_HAND_REQUEST] POST /tobii/hand payload=%s",
            json.dumps(data, ensure_ascii=False, default=str),
        )

        if "box_visible" not in data:
            return web.json_response({"ok": False, "msg": "缺少字段: box_visible"}, status=400)

        box_visible = bool(data.get("box_visible"))
        task_id = data.get("task_id")
        task_name = data.get("task_name")
        effective_task_id = None if task_name == "WeaponLaunchMission" else task_id
        if task_name == "WeaponLaunchMission" and task_id is not None:
            self.logger.warning(
                "[TOBII_HAND_REQUEST] POST /tobii/hand ignoring request task_id for WeaponLaunchMission; "
                "request_task_id=%s active_task_id=%s",
                task_id,
                self._gaze_svc.get_active_task_id(),
            )

        if box_visible:
            bbox = data.get("bbox") or []
            regions = data.get("regions")
            coordinate_space = data.get("coordinate_space")
            screen_data = data.get("screen_data")
            if not isinstance(screen_data, (list, tuple)) or len(screen_data) < 2:
                screen_data = None
            updated = self._gaze_svc.set_task_bbox(
                bbox=bbox,
                screen_size=screen_data,
                task_id=str(effective_task_id) if effective_task_id is not None else None,
                regions=regions if isinstance(regions, list) else None,
                coordinate_space=coordinate_space if isinstance(coordinate_space, str) else None,
            )
            active_id = self._gaze_svc.get_active_task_id()
            return web.json_response({
                "ok": updated,
                "msg": "bbox 已更新" if updated else "无活动任务，bbox 未更新",
                "task_id": active_id,
            })

        else:
            # box_visible=False：清空 bbox（目标框消失，gaze 任务本身由主服务器驱动结束）
            updated = self._gaze_svc.set_task_bbox(
                bbox=[],
                screen_size=None,
                task_id=str(effective_task_id) if effective_task_id is not None else None,
            )
            return web.json_response({
                "ok": True,
                "msg": "目标框消失，bbox 已清空",
                "task_id": self._gaze_svc.get_active_task_id(),
            })

    async def tobii_gaze_point_handler(self, request: web.Request) -> web.Response:
        """GET /tobii/gaze_point — 返回最新注视点坐标（供 visible_gaze.py 轮询）。"""
        if self._gaze_svc is None:
            try:
                from main import initialize_system
                await initialize_system()
            except Exception as e:
                self.logger.error(f"眼动服务延迟初始化失败: {e}", exc_info=True)

        if self._gaze_svc is None:
            return web.json_response({"ok": False, "msg": "眼动追踪服务未启动"}, status=503)

        point, ts = self._gaze_svc.get_latest_gaze_point()
        if point is None:
            return web.json_response({"ok": False, "msg": "注视点数据不可用或已过期"}, status=404)
        return web.json_response({"ok": True, "gaze_point": point, "timestamp": ts})

    async def tobii_gaze_data_handler(self, request: web.Request) -> web.Response:
        """GET /tobii/gaze_data — 返回最新注视点、活动任务和近期注视窗口。"""
        if self._gaze_svc is None:
            try:
                from main import initialize_system
                await initialize_system()
            except Exception as e:
                self.logger.error(f"眼动服务延迟初始化失败: {e}", exc_info=True)

        if self._gaze_svc is None:
            return web.json_response({"ok": False, "msg": "眼动追踪服务未启动"}, status=503)

        def _query_int(name: str, default: int, min_value: int, max_value: int) -> int:
            try:
                value = int(request.query.get(name, str(default)))
            except (TypeError, ValueError):
                value = default
            return max(min_value, min(max_value, value))

        max_age_ms = _query_int("max_age_ms", 1000, 1, 60000)
        limit = _query_int("limit", 60, 0, 600)

        point, ts = self._gaze_svc.get_latest_gaze_point(max_age_ms=max_age_ms)
        window = self._gaze_svc.get_gaze_window_snapshot()
        if limit:
            window = window[-limit:]

        screen_size = self._gaze_svc.get_screen_size()
        return web.json_response({
            "ok": point is not None,
            "msg": None if point is not None else "注视点数据不可用或已过期",
            "gaze_point": point,
            "timestamp": ts,
            "active_task_id": self._gaze_svc.get_active_task_id(),
            "screen_size": list(screen_size) if screen_size else None,
            "window": window,
            "window_count": len(window),
            "max_age_ms": max_age_ms,
        })

    async def start_server(self):
        """启动HTTP服务器"""
        self.logger.info(f"HTTP服务器启动中... http://{self.host}:{self.port}")
        
        # 创建运行器
        runner = web.AppRunner(self.app)
        await runner.setup()
        self._runner = runner
        
        # 创建站点
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        
        self.logger.info(f"HTTP服务器已启动:")
        self.logger.info(f"  - 静态文件服务: http://{self.host}:{self.port}/")
        self.logger.info(f"  - WebSocket连接: ws://{self.host}:{self.port}/ws")
        
        # 保持运行
        try:
            await asyncio.Future()
        finally:
            self.logger.info("HTTP服务器正在停止...")
            await runner.cleanup()
            self._runner = None

    # 判断消息是否是json
    def _looks_like_payload(self, data: dict) -> bool:
        """判断消息是否是 DEFAULT_PAYLOAD 同结构（不要求首条）"""
        if not isinstance(data, dict):
            return False

        # 如果显式带 type，那就交给 type 分支处理（避免误判）
        if "type" in data:
            return False

        required = {"userId", "includeAI", "isPractice", "current_difficulty", "audio_enabled"}
        return required.issubset(data.keys())

# 全局HTTP服务器实例
http_server = HTTPServer() 
