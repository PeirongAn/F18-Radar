#!/usr/bin/env python3
"""
操纵杆WebSocket控制器
专门用于与WebSocket服务器集成的操纵杆控制器
"""

import sys
import os

# 添加项目根目录到Python路径
current_dir = os.path.dirname(__file__)
server_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(server_dir)
operator_cc_dir = os.path.join(project_root, 'operator-cc')
sys.path.insert(0, operator_cc_dir)

from simple_joystick import SimpleJoystickController
import asyncio
import json
import time
from typing import Dict, Any, Callable, Optional
from threading import Lock

class JoystickWebSocketController:
    """
    操纵杆WebSocket控制器
    基于SimpleJoystickController，添加WebSocket集成功能
    """
    
    def __init__(self):
        # 初始化基础操纵杆控制器
        self.joystick = SimpleJoystickController()
        
        # 事件回调函数
        self.data_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self.status_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
        
        # 状态信息
        self.device_status = "disconnected"
        self.last_data_time = 0
        
        # 数据缓存和锁
        self.last_joystick_data = {}
        self.data_lock = Lock()
        
        # 用于检测状态变化的缓存
        self.previous_data = None
        self.change_threshold = 0.001  # 变化阈值，只有超过此阈值才认为状态发生变化
        
        # 设置数据回调
        self.joystick.set_data_callback(self._on_joystick_data)
        
    def _on_joystick_data(self, data: Dict[str, Any]) -> None:
        """处理操纵杆数据的内部回调"""
        with self.data_lock:
            # 在边界检测模式下添加调试信息
            if hasattr(self.joystick, 'boundary_detection_mode') and self.joystick.boundary_detection_mode:
                if self.joystick.boundary_sample_count % 100 == 0:
                    print(f"[WebSocket控制器] 边界检测数据 #{self.joystick.boundary_sample_count}: main_x={data['main_x']:.3f}, main_y={data['main_y']:.3f}, sub_y={data['sub_y']:.3f}")
                
                # 边界检测模式下，总是发送数据（用于实时监控）
                self._send_websocket_data(data)
                return
            
            # 检查状态是否发生显著变化
            if not self._has_significant_change(data):
                return  # 没有显著变化，不发送数据
            
            # 有显著变化，发送数据
            self._send_websocket_data(data)
    
    def _has_significant_change(self, current_data: Dict[str, Any]) -> bool:
        """检查操纵杆状态是否发生显著变化"""
        if self.previous_data is None:
            # 第一次接收数据，记录并发送
            self.previous_data = current_data.copy()
            return True
        
        # 检查按钮状态变化
        for button in ['button1', 'button2', 'button7']:
            if current_data[button] != self.previous_data[button]:
                self.previous_data = current_data.copy()
                return True
        
        # 检查轴位置变化
        for axis in ['main_x', 'main_y', 'sub_y']:
            if abs(current_data[axis] - self.previous_data[axis]) > self.change_threshold:
                self.previous_data = current_data.copy()
                return True
        
        return False
    
    def _send_websocket_data(self, data: Dict[str, Any]) -> None:
        """发送WebSocket数据"""
        # 添加时间戳和设备状态
        websocket_data = {
            "type": "joystick_data",
            "timestamp": time.time(),
            "device_status": self.device_status,
            "data": {
                "main_x": data['main_x'],
                "main_y": data['main_y'],
                "sub_y": data['sub_y'],
                "buttons": {
                    "button1": data['button1'],
                    "button2": data['button2'],
                    "button7": data['button7']
                }
            }
        }
        
        # 如果有原始数据，也包含进去
        if hasattr(self.joystick, 'last_raw_data') and self.joystick.last_raw_data:
            websocket_data["raw_data"] = {
                "x_axis": self.joystick.last_raw_data['x_axis'],
                "y_axis": self.joystick.last_raw_data['y_axis'],
                "ry_axis": self.joystick.last_raw_data['ry_axis']
            }
        
        # 缓存最新数据
        self.last_joystick_data = websocket_data.copy()
        self.last_data_time = time.time()
        
        # 调用外部回调
        if self.data_callback:
            self.data_callback(websocket_data)
    
    def set_data_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """设置数据回调函数"""
        self.data_callback = callback
    
    def set_status_callback(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """设置状态回调函数"""
        self.status_callback = callback
    
    def connect_device(self) -> bool:
        """连接操纵杆设备"""
        try:
            success = self.joystick.connect_joystick()
            if success:
                self.device_status = "connected"
                self._notify_status("device_connected", {
                    "message": "操纵杆已连接",
                    "device_info": {
                        "vendor_id": getattr(self.joystick.device, 'vendor_id', None),
                        "product_id": getattr(self.joystick.device, 'product_id', None),
                        "product_name": getattr(self.joystick.device, 'product_name', None)
                    } if self.joystick.device else None
                })
                return True
            else:
                self.device_status = "connection_failed"
                self._notify_status("device_connection_failed", {
                    "message": "操纵杆连接失败"
                })
                return False
        except Exception as e:
            self.device_status = "error"
            self._notify_status("device_error", {
                "message": f"操纵杆连接错误: {str(e)}"
            })
            return False
    
    def disconnect_device(self) -> None:
        """断开操纵杆连接"""
        try:
            self.joystick.disconnect_joystick()
            self.device_status = "disconnected"
            self._notify_status("device_disconnected", {
                "message": "操纵杆已断开连接"
            })
        except Exception as e:
            self._notify_status("device_error", {
                "message": f"操纵杆断开连接错误: {str(e)}"
            })
    
    def reset_center(self) -> bool:
        """重置中心位置"""
        try:
            success = self.joystick.reset_center()
            if success:
                self._notify_status("center_reset", {
                    "message": "中心位置已重置",
                    "center_values": self.joystick.center_values.copy()
                })
                return True
            else:
                self._notify_status("center_reset_failed", {
                    "message": "中心位置重置失败"
                })
                return False
        except Exception as e:
            self._notify_status("center_reset_error", {
                "message": f"中心位置重置错误: {str(e)}"
            })
            return False
    
    def start_boundary_detection(self) -> bool:
        """开始边界检测"""
        try:
            print(f"[操纵杆控制器] 开始边界检测，设备状态: {self.device_status}")
            print(f"[操纵杆控制器] 操纵杆连接状态: {self.joystick.device is not None}")
            
            success = self.joystick.start_boundary_detection()
            if success:
                print(f"[操纵杆控制器] 边界检测启动成功")
                self._notify_status("boundary_detection_started", {
                    "message": "边界检测已启动",
                    "instruction": "请移动操纵杆到各个极限位置"
                })
                return True
            else:
                print(f"[操纵杆控制器] 边界检测启动失败")
                self._notify_status("boundary_detection_start_failed", {
                    "message": "边界检测启动失败"
                })
                return False
        except Exception as e:
            print(f"[操纵杆控制器] 边界检测启动异常: {e}")
            self._notify_status("boundary_detection_error", {
                "message": f"边界检测启动错误: {str(e)}"
            })
            return False
    
    def stop_boundary_detection(self) -> bool:
        """停止边界检测"""
        try:
            success = self.joystick.stop_boundary_detection()
            if success:
                self._notify_status("boundary_detection_completed", {
                    "message": "边界检测已完成",
                    "boundaries": self.joystick.axis_boundaries.copy(),
                    "center_values": self.joystick.center_values.copy(),
                    "sample_count": self.joystick.boundary_sample_count
                })
                return True
            else:
                self._notify_status("boundary_detection_stop_failed", {
                    "message": "边界检测停止失败"
                })
                return False
        except Exception as e:
            self._notify_status("boundary_detection_error", {
                "message": f"边界检测停止错误: {str(e)}"
            })
            return False
    
    def get_device_status(self) -> Dict[str, Any]:
        """获取设备状态信息"""
        return {
            "type": "joystick_status",
            "timestamp": time.time(),
            "device_status": self.device_status,
            "connected": self.device_status == "connected",
            "boundary_detection_active": self.joystick.boundary_detection_mode if hasattr(self.joystick, 'boundary_detection_mode') else False,
            "last_data_time": self.last_data_time,
            "boundaries": self.joystick.axis_boundaries.copy(),
            "center_values": self.joystick.center_values.copy()
        }
    
    def get_latest_data(self) -> Optional[Dict[str, Any]]:
        """获取最新的操纵杆数据"""
        with self.data_lock:
            return self.last_joystick_data.copy() if self.last_joystick_data else None
    
    def _notify_status(self, event: str, data: Dict[str, Any]) -> None:
        """通知状态变化"""
        if self.status_callback:
            status_data = {
                "type": "joystick_status",
                "event": event,
                "timestamp": time.time(),
                "data": data
            }
            self.status_callback(event, status_data)
    
    def is_connected(self) -> bool:
        """检查设备是否已连接"""
        return self.device_status == "connected"
    
    def cleanup(self) -> None:
        """清理资源"""
        try:
            self.disconnect_device()
        except Exception as e:
            print(f"清理资源时出错: {e}")