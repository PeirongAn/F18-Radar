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
        self._setup_routes()
    
    def set_joystick_handler(self, handler):
        """设置操纵杆事件处理器"""
        self.joystick_handler = handler
    
    def _setup_routes(self):
        """设置路由"""
        # 避免重复设置路由
        if self._routes_setup:
            return
            
        # WebSocket路由
        self.app.router.add_get('/ws', self.websocket_handler)
        
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

# 全局HTTP服务器实例
http_server = HTTPServer() 