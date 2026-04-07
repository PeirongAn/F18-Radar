#!/usr/bin/env python3
"""
操纵杆WebSocket控制器
基于 pygame (DirectInput) 读取 Thrustmaster HOTAS Warthog 摇杆数据
"""

import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame
import time
import threading
from typing import Dict, Any, Callable, Optional
from threading import Lock


class JoystickWebSocketController:
    """
    基于 pygame/DirectInput 的操纵杆控制器。
    pygame 直接提供 -1~1 标准化轴值，无需手动校准/归一化。

    数据映射:
        main_x = Axis 0          (右 +1, 左 -1)
        main_y = -Axis 1         (前 +1, 后 -1, 原始值取反)
        sub_x  = Hat 0 X         (-1 / 0 / +1)
        sub_y  = Hat 0 Y         (-1 / 0 / +1)
        buttons = button0..button18
    """

    POLL_INTERVAL = 0.02  # 50Hz

    def __init__(self):
        self._pygame_inited = False
        self.joystick: Optional[pygame.joystick.JoystickType] = None

        self.data_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self.status_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None

        self.device_status = "disconnected"
        self.last_data_time = 0.0

        self.last_joystick_data: Dict[str, Any] = {}
        self.data_lock = Lock()

        self.previous_data: Optional[Dict[str, Any]] = None
        self.change_threshold = 0.005

        self._poll_thread: Optional[threading.Thread] = None
        self._poll_running = False

    # ─── pygame 初始化 ──────────────────────────────────

    def _ensure_pygame(self):
        if not self._pygame_inited:
            pygame.init()
            pygame.joystick.init()
            self._pygame_inited = True

    # ─── 连接 / 断开 ──────────────────────────────────

    def connect_device(self) -> bool:
        self._ensure_pygame()
        pygame.joystick.quit()
        pygame.joystick.init()

        count = pygame.joystick.get_count()
        if count == 0:
            self.device_status = "connection_failed"
            self._notify_status("device_connection_failed", {"message": "未检测到控制器"})
            return False

        # 优先选名称含 "joystick" 的设备，避免误选油门台（throttle）
        # HOTAS Warthog 套装会同时枚举 Throttle 和 Joystick 两个设备
        candidates = []
        for i in range(count):
            js = pygame.joystick.Joystick(i)
            js.init()
            name = js.get_name().lower()
            if "throttle" in name:
                priority = 2          # 油门台最低优先级
            elif "joystick" in name:
                priority = 0          # 摇杆最高优先级
            elif "warthog" in name or "thrustmaster" in name:
                priority = 1
            else:
                priority = 3
            candidates.append((priority, i, js))

        candidates.sort(key=lambda x: x[0])
        target = candidates[0][2] if candidates else None

        if target is None:
            target = pygame.joystick.Joystick(0)
            target.init()

        self.joystick = target
        self.device_status = "connected"
        self.previous_data = None

        info = {
            "message": "操纵杆已连接",
            "device_info": {
                "name": self.joystick.get_name(),
                "axes": self.joystick.get_numaxes(),
                "buttons": self.joystick.get_numbuttons(),
                "hats": self.joystick.get_numhats(),
            }
        }
        self._notify_status("device_connected", info)

        self._start_polling()
        return True

    def disconnect_device(self) -> None:
        self._stop_polling()
        self.joystick = None
        self.device_status = "disconnected"
        self._notify_status("device_disconnected", {"message": "操纵杆已断开连接"})

    # ─── 轮询线程 ──────────────────────────────────────

    def _start_polling(self):
        if self._poll_running:
            return
        self._poll_running = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _stop_polling(self):
        self._poll_running = False
        if self._poll_thread:
            self._poll_thread.join(timeout=2)
            self._poll_thread = None

    def pump_and_tick(self):
        """
        在主线程中调用，用于刷新 pygame 事件队列。
        部分 Windows 系统要求 pygame.event.pump() 必须在主线程执行；
        若摇杆无响应，请在主线程循环中定期调用此方法（约 20ms 一次）。
        """
        try:
            pygame.event.pump()
        except Exception:
            pass

    def _poll_loop(self):
        while self._poll_running and self.joystick is not None:
            try:
                # 优先尝试在子线程 pump；若平台不支持，请改为在主线程调用 pump_and_tick()
                pygame.event.pump()
                data = self._read_joystick()
                if data and self._has_significant_change(data):
                    self._send_websocket_data(data)
            except Exception as e:
                print(f"[JoystickController] 轮询异常: {e}")
            time.sleep(self.POLL_INTERVAL)

    # ─── 数据读取 ──────────────────────────────────────

    def _read_joystick(self) -> Optional[Dict[str, Any]]:
        js = self.joystick
        if js is None:
            return None

        num_axes = js.get_numaxes()
        num_buttons = js.get_numbuttons()
        num_hats = js.get_numhats()

        axis_0 = js.get_axis(0) if num_axes > 0 else 0.0
        axis_1 = js.get_axis(1) if num_axes > 1 else 0.0

        hat_x, hat_y = 0, 0
        if num_hats > 0:
            hat_x, hat_y = js.get_hat(0)

        buttons = {}
        for i in range(min(num_buttons, 19)):
            buttons[f"button{i}"] = bool(js.get_button(i))

        return {
            "main_x": round(axis_0, 4),
            "main_y": round(axis_1, 4),  # 取反
            "sub_x": hat_x,
            "sub_y": hat_y,
            "buttons": buttons,
        }

    # ─── 变化检测 ──────────────────────────────────────

    def _has_significant_change(self, current: Dict[str, Any]) -> bool:
        if self.previous_data is None:
            self.previous_data = current.copy()
            return True

        prev = self.previous_data

        # 按钮变化
        for key in current["buttons"]:
            if current["buttons"].get(key) != prev.get("buttons", {}).get(key):
                self.previous_data = current.copy()
                return True

        # Hat 变化（离散值，任何变化都发送）
        if current["sub_x"] != prev.get("sub_x") or current["sub_y"] != prev.get("sub_y"):
            self.previous_data = current.copy()
            return True

        # 轴变化
        if (abs(current["main_x"] - prev.get("main_x", 0)) > self.change_threshold or
                abs(current["main_y"] - prev.get("main_y", 0)) > self.change_threshold):
            self.previous_data = current.copy()
            return True

        return False

    # ─── 数据发送 ──────────────────────────────────────

    def _send_websocket_data(self, data: Dict[str, Any]) -> None:
        websocket_data = {
            "type": "joystick_data",
            "timestamp": time.time(),
            "device_status": self.device_status,
            "data": data,
        }

        with self.data_lock:
            self.last_joystick_data = websocket_data.copy()
            self.last_data_time = time.time()

        if self.data_callback:
            self.data_callback(websocket_data)

    # ─── 回调设置 ──────────────────────────────────────

    def set_data_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        self.data_callback = callback

    def set_status_callback(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        self.status_callback = callback

    # ─── 状态查询 ──────────────────────────────────────

    def get_device_status(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "type": "joystick_status",
            "timestamp": time.time(),
            "device_status": self.device_status,
            "connected": self.device_status == "connected",
            "last_data_time": self.last_data_time,
        }
        if self.joystick:
            info["device_info"] = {
                "name": self.joystick.get_name(),
                "axes": self.joystick.get_numaxes(),
                "buttons": self.joystick.get_numbuttons(),
                "hats": self.joystick.get_numhats(),
            }
        return info

    def get_latest_data(self) -> Optional[Dict[str, Any]]:
        with self.data_lock:
            return self.last_joystick_data.copy() if self.last_joystick_data else None

    def is_connected(self) -> bool:
        return self.device_status == "connected"

    def reset_center(self) -> bool:
        """pygame 已标准化，无需重置中心"""
        self._notify_status("center_reset", {"message": "pygame 模式下无需重置中心"})
        return True

    def start_boundary_detection(self) -> bool:
        """pygame 已标准化到 -1~1，无需边界检测"""
        self._notify_status("boundary_detection_started", {"message": "pygame 模式已自动标准化"})
        return True

    def stop_boundary_detection(self) -> bool:
        self._notify_status("boundary_detection_completed", {"message": "边界检测完成"})
        return True

    def cleanup(self) -> None:
        try:
            self.disconnect_device()
        except Exception as e:
            print(f"清理资源时出错: {e}")

    # ─── 内部工具 ──────────────────────────────────────

    def _notify_status(self, event: str, data: Dict[str, Any]) -> None:
        if self.status_callback:
            status_data = {
                "type": "joystick_status",
                "event": event,
                "timestamp": time.time(),
                "data": data,
            }
            self.status_callback(event, status_data)
