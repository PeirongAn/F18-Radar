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

from managers import config_manager, target_manager, get_logger
from core import message_handler

class HTTPServer:
    """HTTP服务器，同时支持静态文件服务和WebSocket连接"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8080, static_dir: str = None):
        self.host = host
        self.port = port
        self.static_dir = static_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'dist')
        self.logger = get_logger("http_server")
        self.app = web.Application()
        self._routes_setup = False
        self.joystick_handler = None
        self._gaze_svc = None
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

    
    def set_joystick_handler(self, handler):
        """设置操纵杆事件处理器"""
        self.joystick_handler = handler

    def set_gaze_service(self, gaze_svc) -> None:
        """注入眼动追踪服务（由 server/main.py 的 initialize_system 调用）。"""
        self._gaze_svc = gaze_svc
    
    def _setup_routes(self):
        """设置路由"""
        # 避免重复设置路由
        if self._routes_setup:
            return
            
        # WebSocket路由
        self.app.router.add_get('/ws', self.websocket_handler)

        # 眼动追踪路由
        self.app.router.add_post('/tobii/hand', self.tobii_hand_handler)
        self.app.router.add_get('/tobii/gaze_point', self.tobii_gaze_point_handler)

        # 静态文件路由
        self._setup_static_routes()
        
        self._routes_setup = True
    
    def _setup_static_routes(self):
        """设置静态文件路由"""
        if os.path.exists(self.static_dir):
            # 添加静态文件路由
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
        if path.startswith('/ws') or path.startswith('/api'):
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
            self.app = web.Application()
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
    
    async def websocket_handler(self, request):
        """处理WebSocket连接"""
        ws = WebSocketResponse()
        await ws.prepare(request)
        
        client_id = str(uuid.uuid4())
        self.logger.info(f"WebSocket客户端已连接: {client_id}")
        session_state = {}
        
        # 将连接注册到 websocket_server，使操纵杆数据广播能找到此客户端
        from network import websocket_server
        websocket_server.add_client(client_id, ws)

        # 首个客户端连接时自动触发系统初始化（包括眼动服务）
        from main import initialize_system, _initialized
        if not _initialized:
            try:
                await initialize_system()
            except Exception as e:
                self.logger.error(f"首次连接延迟初始化失败: {e}")

        try:
            # 发送初始数据
            initial_data = target_manager.get_radar_data(include_targets=False)
            await ws.send_str(json.dumps(initial_data))
            self.logger.info(f"已发送WebSocket初始数据")
            # 消息处理循环
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    message = msg.data
                    self.logger.debug(f"接收到WebSocket消息")
                    


                  # 检查是否为操纵杆相关消息
                    try:
                        message_data = json.loads(message)
                        message_type = message_data.get('type', '')
                    except json.JSONDecodeError:
                        message_data = None
                        message_type = ''
                    
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
                        for reply in await handle_platform_task_ws(websocket_server, client_id, message_data):
                            await ws.send_str(json.dumps(reply, ensure_ascii=False))
                        continue

                    # 收到 joystick_connect 时触发延迟初始化
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
                            data["_timestamp"] = time.time()
                            await ws.send_str(json.dumps(data))
                            
                elif msg.type == WSMsgType.ERROR:
                    self.logger.error(f'WebSocket错误: {ws.exception()}')
                    
        except Exception as e:
            self.logger.error(f"WebSocket处理错误: {e}", exc_info=True)
        finally:
            websocket_server.remove_client(client_id)
            self.logger.info(f"WebSocket客户端已断开连接: {client_id}")
            
        return ws
    
    async def tobii_hand_handler(self, request: web.Request) -> web.Response:
        """
        POST /tobii/hand

        前端在目标框出现（box_visible=true）或消失（box_visible=false）时调用。

        box_visible=true 时更新当前活动任务的注意力区域（bbox），
        不重新创建任务——任务已由主服务器在 task_start 时创建。

        请求体示例（出现）:
            {"box_visible": true, "task_id": 123, "bbox": [[x1,y1,x2,y2]],
             "scream_data": [1920, 1080]}
        请求体示例（消失）:
            {"box_visible": false, "task_id": 123}
        """
        if self._gaze_svc is None:
            return web.json_response({"ok": False, "msg": "眼动追踪服务未启动"}, status=503)

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "msg": "请求体必须是 JSON"}, status=400)

        if "box_visible" not in data:
            return web.json_response({"ok": False, "msg": "缺少字段: box_visible"}, status=400)

        box_visible = bool(data.get("box_visible"))
        task_id = data.get("task_id")

        if box_visible:
            bbox = data.get("bbox") or []
            scream_data = data.get("scream_data") or [1, 1]
            if not isinstance(scream_data, (list, tuple)) or len(scream_data) < 2:
                scream_data = [1, 1]
            screen_size = (scream_data[0] or 1, scream_data[1] or 1)

            updated = self._gaze_svc.set_task_bbox(
                bbox=bbox,
                screen_size=screen_size,
                task_id=str(task_id) if task_id is not None else None,
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
                screen_size=(1, 1),
                task_id=str(task_id) if task_id is not None else None,
            )
            return web.json_response({
                "ok": True,
                "msg": "目标框消失，bbox 已清空",
                "task_id": self._gaze_svc.get_active_task_id(),
            })

    async def tobii_gaze_point_handler(self, request: web.Request) -> web.Response:
        """GET /tobii/gaze_point — 返回最新注视点坐标（供 visible_gaze.py 轮询）。"""
        if self._gaze_svc is None:
            return web.json_response({"ok": False, "msg": "眼动追踪服务未启动"}, status=503)

        point, ts = self._gaze_svc.get_latest_gaze_point()
        if point is None:
            return web.json_response({"ok": False, "msg": "注视点数据不可用或已过期"}, status=404)
        return web.json_response({"ok": True, "gaze_point": point, "timestamp": ts})

    async def start_server(self):
        """启动HTTP服务器"""
        self.logger.info(f"HTTP服务器启动中... http://{self.host}:{self.port}")
        
        # 创建运行器
        runner = web.AppRunner(self.app)
        await runner.setup()
        
        # 创建站点
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        
        self.logger.info(f"HTTP服务器已启动:")
        self.logger.info(f"  - 静态文件服务: http://{self.host}:{self.port}/")
        self.logger.info(f"  - WebSocket连接: ws://{self.host}:{self.port}/ws")
        
        # 保持运行
        await asyncio.Future()

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