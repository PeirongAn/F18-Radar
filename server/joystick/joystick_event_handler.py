#!/usr/bin/env python3
"""
操纵杆事件处理器
作为JoystickWebSocketController和WebSocketServer之间的桥接器
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, Set, Callable
from threading import Lock
from .joystick_websocket_controller import JoystickWebSocketController

logger = logging.getLogger(__name__)

class JoystickEventHandler:
    """
    操纵杆事件处理器
    负责处理操纵杆事件并将其转发到WebSocket服务器
    """
    
    def __init__(self, websocket_server=None):
        """
        初始化事件处理器
        
        Args:
            websocket_server: WebSocket服务器实例
        """
        self.websocket_server = websocket_server
        self.joystick_controller = JoystickWebSocketController()
        
        # 客户端管理
        self.joystick_clients: Set[str] = set()  # 订阅操纵杆数据的客户端
        self.clients_lock = Lock()
        
        # 事件处理状态
        self.is_active = False
        
        # 异步事件循环相关
        self.loop = None
        self.data_queue = asyncio.Queue()
        self.data_processing_task = None
        
        # 设置操纵杆回调
        self.joystick_controller.set_data_callback(self._handle_joystick_data)
        self.joystick_controller.set_status_callback(self._handle_joystick_status)
        
        # 消息处理映射
        self.message_handlers = {
            'joystick_connect': self._handle_connect_request,
            'joystick_disconnect': self._handle_disconnect_request,
            'joystick_reset_center': self._handle_reset_center_request,
            'joystick_start_boundary': self._handle_start_boundary_request,
            'joystick_stop_boundary': self._handle_stop_boundary_request,
            'joystick_get_status': self._handle_get_status_request,
            'joystick_subscribe': self._handle_subscribe_request,
            'joystick_unsubscribe': self._handle_unsubscribe_request,
        }
    
    def set_websocket_server(self, websocket_server):
        """设置WebSocket服务器实例"""
        self.websocket_server = websocket_server
    
    def start(self):
        """启动事件处理器"""
        if not self.is_active:
            self.is_active = True
            
            # 获取当前事件循环
            try:
                self.loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.warning("启动时未发现运行中的事件循环")
            
            # 启动数据处理任务
            if self.loop and not self.data_processing_task:
                self.data_processing_task = self.loop.create_task(self._process_data_queue())
            
            logger.info("操纵杆事件处理器已启动")
    
    def stop(self):
        """停止事件处理器"""
        if self.is_active:
            self.is_active = False
            
            # 停止数据处理任务
            if self.data_processing_task:
                self.data_processing_task.cancel()
                self.data_processing_task = None
            
            self.joystick_controller.cleanup()
            logger.info("操纵杆事件处理器已停止")
    
    def _handle_joystick_data(self, data: Dict[str, Any]):
        """处理操纵杆数据"""
        if not self.is_active or not self.websocket_server:
            return
        self._enqueue_data(data)
    
    def _handle_joystick_status(self, event: str, data: Dict[str, Any]):
        """处理操纵杆状态变化"""
        if not self.is_active or not self.websocket_server:
            return
            
        # 将状态数据放入队列中等待异步处理
        self._enqueue_data(data)
        
        logger.info(f"操纵杆状态变化: {event}")
    
    def _enqueue_data(self, data: Dict[str, Any]):
        """将数据放入队列中等待异步处理"""
        try:
            if self.loop and self.data_queue:
                # 线程安全地放入数据队列
                self.loop.call_soon_threadsafe(self.data_queue.put_nowait, data)
        except Exception as e:
            logger.warning(f"数据入队失败: {e}")
    
    async def _process_data_queue(self):
        """异步处理数据队列"""
        while self.is_active:
            try:
                # 从队列中获取数据
                data = await asyncio.wait_for(self.data_queue.get(), timeout=1.0)
                
                # 广播给订阅的客户端
                await self._async_broadcast_to_joystick_clients(data)
                
            except asyncio.TimeoutError:
                # 超时继续循环
                continue
            except asyncio.CancelledError:
                # 任务被取消
                break
            except Exception as e:
                logger.error(f"处理数据队列时发生错误: {e}")
                await asyncio.sleep(0.1)  # 短暂延迟避免错误循环
    
    async def _async_broadcast_to_joystick_clients(self, data: Dict[str, Any]):
        """异步向订阅操纵杆数据的客户端广播消息"""
        if not self.joystick_clients:
            return
            
        with self.clients_lock:
            clients_to_remove = []
            
            for client_id in self.joystick_clients.copy():
                try:
                    # 异步发送消息
                    await self.websocket_server.send_to_client(client_id, data)
                except Exception as e:
                    logger.warning(f"向客户端 {client_id} 发送操纵杆数据失败: {e}")
                    clients_to_remove.append(client_id)
            
            # 移除断开的客户端
            for client_id in clients_to_remove:
                self.joystick_clients.discard(client_id)
    
    async def handle_message(self, client_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理来自客户端的操纵杆相关消息
        
        Args:
            client_id: 客户端ID
            message: 消息内容
            
        Returns:
            处理结果
        """
        message_type = message.get('type')
        
        if message_type in self.message_handlers:
            return await self.message_handlers[message_type](client_id, message)
        else:
            return {
                'type': 'error',
                'message': f'未知的操纵杆消息类型: {message_type}'
            }
    
    async def _handle_connect_request(self, client_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """处理连接操纵杆请求"""
        try:
            success = self.joystick_controller.connect_device()
            
            return {
                'type': 'joystick_connect_response',
                'success': success,
                'status': self.joystick_controller.get_device_status()
            }
        except Exception as e:
            logger.error(f"连接操纵杆失败: {e}")
            return {
                'type': 'joystick_connect_response',
                'success': False,
                'error': str(e)
            }
    
    async def _handle_disconnect_request(self, client_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """处理断开操纵杆请求"""
        try:
            self.joystick_controller.disconnect_device()
            
            return {
                'type': 'joystick_disconnect_response',
                'success': True,
                'status': self.joystick_controller.get_device_status()
            }
        except Exception as e:
            logger.error(f"断开操纵杆失败: {e}")
            return {
                'type': 'joystick_disconnect_response',
                'success': False,
                'error': str(e)
            }
    
    async def _handle_reset_center_request(self, client_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """处理重置中心位置请求"""
        try:
            success = self.joystick_controller.reset_center()
            
            return {
                'type': 'joystick_reset_center_response',
                'success': success,
                'status': self.joystick_controller.get_device_status()
            }
        except Exception as e:
            logger.error(f"重置中心位置失败: {e}")
            return {
                'type': 'joystick_reset_center_response',
                'success': False,
                'error': str(e)
            }
    
    async def _handle_start_boundary_request(self, client_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """处理开始边界检测请求"""
        try:
            print(f"[事件处理器] 客户端 {client_id} 请求开始边界检测")
            print(f"[事件处理器] 当前操纵杆控制器连接状态: {self.joystick_controller.is_connected()}")
            
            success = self.joystick_controller.start_boundary_detection()
            
            print(f"[事件处理器] 边界检测启动结果: {success}")
            
            return {
                'type': 'joystick_start_boundary_response',
                'success': success,
                'status': self.joystick_controller.get_device_status()
            }
        except Exception as e:
            logger.error(f"开始边界检测失败: {e}")
            print(f"[事件处理器] 边界检测启动异常: {e}")
            return {
                'type': 'joystick_start_boundary_response',
                'success': False,
                'error': str(e)
            }
    
    async def _handle_stop_boundary_request(self, client_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """处理停止边界检测请求"""
        try:
            success = self.joystick_controller.stop_boundary_detection()
            
            return {
                'type': 'joystick_stop_boundary_response',
                'success': success,
                'status': self.joystick_controller.get_device_status()
            }
        except Exception as e:
            logger.error(f"停止边界检测失败: {e}")
            return {
                'type': 'joystick_stop_boundary_response',
                'success': False,
                'error': str(e)
            }
    
    async def _handle_get_status_request(self, client_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """处理获取状态请求"""
        try:
            status = self.joystick_controller.get_device_status()
            latest_data = self.joystick_controller.get_latest_data()
            
            return {
                'type': 'joystick_status_response',
                'status': status,
                'latest_data': latest_data
            }
        except Exception as e:
            logger.error(f"获取操纵杆状态失败: {e}")
            return {
                'type': 'joystick_status_response',
                'error': str(e)
            }
    
    async def _handle_subscribe_request(self, client_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """处理订阅操纵杆数据请求"""
        with self.clients_lock:
            self.joystick_clients.add(client_id)
        
        logger.info(f"客户端 {client_id} 订阅操纵杆数据")
        
        return {
            'type': 'joystick_subscribe_response',
            'success': True,
            'message': '已订阅操纵杆数据'
        }
    
    async def _handle_unsubscribe_request(self, client_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """处理取消订阅操纵杆数据请求"""
        with self.clients_lock:
            self.joystick_clients.discard(client_id)
        
        logger.info(f"客户端 {client_id} 取消订阅操纵杆数据")
        
        return {
            'type': 'joystick_unsubscribe_response',
            'success': True,
            'message': '已取消订阅操纵杆数据'
        }
    
    def remove_client(self, client_id: str):
        """移除客户端（当客户端断开连接时调用）"""
        with self.clients_lock:
            self.joystick_clients.discard(client_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'active': self.is_active,
            'connected': self.joystick_controller.is_connected(),
            'subscribed_clients': len(self.joystick_clients),
            'device_status': self.joystick_controller.get_device_status()
        }