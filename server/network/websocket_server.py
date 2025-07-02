import asyncio
import websockets
import json
import time
from typing import Dict, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from managers import config_manager, target_manager, get_logger
from core import message_handler

class WebSocketServer:
    """WebSocket服务器，负责处理客户端连接和消息传输"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.logger = get_logger("websocket")
    
    async def send_message(self, websocket, message: Dict[str, Any]) -> bool:
        """发送消息到客户端"""
        try:
            json_str = json.dumps(message)
            await websocket.send(json_str)
            self.logger.debug(f"发送消息: {message['type']}")
            return True
        except Exception as e:
            self.logger.error(f"发送消息失败: {e}", exc_info=True)
            return False
    
    async def handle_client(self, websocket) -> None:
        """处理单个客户端连接"""
        self.logger.info("客户端已连接")
        session_state = {}  # 为每个连接创建一个独立的会话状态
        
        try:
            # 初始连接时发送不包含目标数据的基础数据
            initial_data = target_manager.get_radar_data(include_targets=False)
            initial_json = json.dumps(initial_data)
            await websocket.send(initial_json)
            self.logger.info(f"已发送基础数据（不含目标），长度: {len(initial_json)}")
            
            # 接收并处理客户端消息
            while True:
                try:
                    # 等待消息，但设置超时以保持连接活跃
                    message = await asyncio.wait_for(websocket.recv(), timeout=60)
                    self.logger.debug(f"接收到消息: {message[:50]}..." if len(message) > 50 else message)
                    
                    # 将会话状态传递给消息处理器
                    result = await message_handler.handle_client_message(message, session_state, websocket)
                    
                    # 检查返回结果类型
                    if isinstance(result, list):
                        for msg in result:
                            await self.send_message(websocket, msg)
                    elif isinstance(result, tuple) and len(result) == 2:
                        settings_updated, include_targets = result
                        if settings_updated:
                            # 确保验证消息在数据帧之前发送
                            if 'type' in settings_updated and settings_updated['type'] == 'settings_validation':
                                self.logger.debug(f"发送验证结果: {settings_updated}")
                                await websocket.send(json.dumps(settings_updated))

                            # 现在准备并发送主数据帧
                            data = target_manager.get_radar_data(include_targets=include_targets)
                            data["_timestamp"] = time.time()
                            data_json = json.dumps(data)

                            if include_targets:
                                self.logger.debug(f"正在发送包含目标的数据，JSON长度: {len(data_json)}")
                                self.logger.debug(f"数据键: {list(data.keys())}")
                                if 'externalTargets' in data:
                                    self.logger.debug(f"externalTargets长度: {len(data['externalTargets'])}")
                            else:
                                self.logger.debug(f"正在发送不含目标的数据，JSON长度: {len(data_json)}")
                            
                            await websocket.send(data_json)
                            
                            if include_targets:
                                self.logger.info("已发送更新后的数据（包含目标）")
                            else:
                                self.logger.info("已发送更新后的数据（不含目标）")
                                
                except asyncio.TimeoutError:
                    pass
                except websockets.exceptions.ConnectionClosed:
                    self.logger.info("客户端连接已关闭")
                    break
                    
        except websockets.exceptions.ConnectionClosed:
            self.logger.info("客户端已断开连接")
        except Exception as e:
            self.logger.error(f"WebSocket处理时出错: {e}", exc_info=True)
    
    async def start_server(self) -> None:
        """启动WebSocket服务器"""
        self.logger.info(f"雷达服务器启动中... ws://{self.host}:{self.port}")
        
        async with websockets.serve(self.handle_client, self.host, self.port):
            self.logger.info(f"雷达服务器已启动于 ws://{self.host}:{self.port}")
            await asyncio.Future()  # 运行直到被取消

# 全局WebSocket服务器实例
websocket_server = WebSocketServer() 