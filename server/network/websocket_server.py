import asyncio
import websockets
import json
import time
from typing import Dict, Any, Optional, List
import uuid

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from managers import config_manager, target_manager, get_logger
from network.netlog import (
    duration_ms,
    log_ws_connect,
    log_ws_disconnect,
    log_ws_message,
    log_ws_send,
    now_ms,
    remote_from_websocket,
    should_log_ws_message,
)
# 延迟导入 message_handler 以避免循环导入

class WebSocketServer:
    """WebSocket服务器，负责处理客户端连接和消息传输"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.logger = get_logger("websocket")
        
        # 客户端连接管理
        self.clients: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.client_sessions: Dict[str, Dict[str, Any]] = {}
        
        # 操纵杆事件处理器（延迟初始化）
        self.joystick_handler = None

        # 眼动追踪服务（延迟注入）
        self._gaze_svc = None
        self._physio_svc = None
        self._external_collectors = None
    
    def set_joystick_handler(self, handler):
        """设置操纵杆事件处理器"""
        self.joystick_handler = handler
        handler.set_websocket_server(self)

    def set_gaze_service(self, gaze_svc) -> None:
        """注入 GazeService 实例，用于处理 tobii_hand 消息。"""
        self._gaze_svc = gaze_svc

    def set_physio_service(self, physio_svc) -> None:
        self._physio_svc = physio_svc

    def set_external_collector_manager(self, external_collectors) -> None:
        self._external_collectors = external_collectors
    
    def generate_client_id(self) -> str:
        """生成唯一的客户端ID"""
        return str(uuid.uuid4())
    
    def add_client(
        self,
        client_id: str,
        websocket: websockets.WebSocketServerProtocol,
        log_event: bool = True,
        endpoint: str = None,
        remote: str = None,
    ):
        """添加客户端连接"""
        self.clients[client_id] = websocket
        endpoint = endpoint or f"ws://{self.host}:{self.port}"
        remote = remote or remote_from_websocket(websocket)
        self.client_sessions[client_id] = {
            "_connected_at_ms": now_ms(),
            "_endpoint": endpoint,
            "_remote": remote,
        }
        if log_event:
            log_ws_connect(self.logger, client_id, endpoint, remote, self.get_client_count())
    
    def remove_client(self, client_id: str, log_event: bool = True):
        """移除客户端连接"""
        session = self.client_sessions.get(client_id, {})
        endpoint = session.get("_endpoint", f"ws://{self.host}:{self.port}")
        remote = session.get("_remote", "-")
        connected_at_ms = session.get("_connected_at_ms")
        if client_id in self.clients:
            del self.clients[client_id]
        if client_id in self.client_sessions:
            del self.client_sessions[client_id]
        
        # 通知操纵杆处理器移除客户端
        if self.joystick_handler:
            self.joystick_handler.remove_client(client_id)
        
        if log_event:
            elapsed_ms = duration_ms(connected_at_ms) if connected_at_ms is not None else None
            log_ws_disconnect(
                self.logger,
                client_id,
                endpoint,
                remote,
                elapsed_ms,
                self.get_client_count(),
            )
    
    async def send_to_client(self, client_id: str, message: Dict[str, Any]) -> bool:
        """向指定客户端发送消息"""
        if client_id not in self.clients:
            self.logger.warning(f"尝试向不存在的客户端发送消息: {client_id}")
            return False
        
        websocket = self.clients[client_id]
        return await self.send_message(websocket, message)
    
    async def broadcast_to_all(self, message: Dict[str, Any]):
        """向所有客户端广播消息"""
        if not self.clients:
            return
        
        disconnected_clients = []
        for client_id, websocket in self.clients.items():
            try:
                await self.send_message(websocket, message)
            except Exception as e:
                self.logger.warning(f"向客户端 {client_id} 广播失败: {e}")
                disconnected_clients.append(client_id)
        
        # 移除断开的客户端
        for client_id in disconnected_clients:
            self.remove_client(client_id)

    async def broadcast_to_clients_except(
        self, message: Dict[str, Any], exclude_client_id: Optional[str]
    ) -> int:
        """向所有已连接客户端广播消息，可选排除某一 client_id。返回成功送达的连接数。"""
        if not self.clients:
            return 0
        ok_count = 0
        disconnected: List[str] = []
        for cid, websocket in list(self.clients.items()):
            if exclude_client_id is not None and cid == exclude_client_id:
                continue
            try:
                if await self.send_message(websocket, message):
                    ok_count += 1
                else:
                    # send_message converts transport failures to False.
                    # Unregister that dead peer immediately (for example UE).
                    disconnected.append(cid)
            except Exception as e:
                self.logger.warning(f"向客户端 {cid} 广播失败: {e}")
                disconnected.append(cid)
        for cid in disconnected:
            self.remove_client(cid)
        return ok_count
    
    def get_client_count(self) -> int:
        """获取当前连接的客户端数量"""
        return len(self.clients)

    async def close_clients(self, timeout: float = 1.0) -> None:
        """Close registered websocket clients before service teardown."""
        for client_id, websocket in list(self.clients.items()):
            try:
                close_result = websocket.close()
                if asyncio.iscoroutine(close_result):
                    await asyncio.wait_for(close_result, timeout=timeout)
            except Exception as e:
                self.logger.debug("Error while closing websocket client %s: %s", client_id, e)
            finally:
                self.remove_client(client_id)
    
    async def _send_raw_message(self, websocket, json_str: str) -> bool:
        """发送原始JSON字符串到WebSocket"""
        # 先尝试标准的send方法
        try:
            await websocket.send(json_str)
            return True
        except AttributeError:
            # 如果send方法不存在，尝试send_str方法
            try:
                await websocket.send_str(json_str)
                return True
            except AttributeError:
                self.logger.error(f"WebSocket对象 {type(websocket)} 没有send或send_str方法")
                return False
            except Exception as e:
                self.logger.error(f"使用send_str发送消息失败: {e}", exc_info=True)
                return False
        except Exception as e:
            self.logger.error(f"使用send发送消息失败: {e}", exc_info=True)
            return False
    
    async def send_message(self, websocket, message: Dict[str, Any]) -> bool:
        """发送消息到客户端"""
        try:
            json_str = json.dumps(message)
            success = await self._send_raw_message(websocket, json_str)
            if success:
                self.logger.debug(f"发送消息: {message.get('type', '')}")
            return success
        except Exception as e:
            self.logger.error(f"发送消息失败: {e}", exc_info=True)
            return False

    def _log_ws_request(self, client_id: str, message: str, message_data=None) -> None:
        """记录收到的 WebSocket 请求摘要到统一日志。"""
        endpoint = self.client_sessions.get(client_id, {}).get("_endpoint", f"ws://{self.host}:{self.port}")
        log_ws_message(self.logger, client_id, endpoint, message, message_data)

    async def _send_platform_task_reply(self, websocket, client_id: str, reply: dict) -> bool:
        success = await self.send_message(websocket, reply)
        endpoint = self.client_sessions.get(client_id, {}).get(
            "_endpoint",
            f"ws://{self.host}:{self.port}",
        )
        log_ws_send(
            self.logger,
            client_id,
            endpoint,
            reply,
            success=success,
            error=None if success else "websocket send returned false",
        )
        return success
    
    async def handle_client(self, websocket) -> None:
        """处理单个客户端连接"""
        client_id = self.generate_client_id()
        self.add_client(client_id, websocket)

        # 首个客户端连接时自动触发系统初始化（包括眼动服务）
        from main import initialize_system, _initialized
        if not _initialized:
            try:
                await initialize_system()
            except Exception as e:
                self.logger.error(f"首次连接延迟初始化失败: {e}")

        try:
            # 接收并处理客户端消息
            while True:
                try:
                    # 等待消息，但设置超时以保持连接活跃
                    message = await asyncio.wait_for(websocket.recv(), timeout=60)

                    # 解析消息
                    try:
                        message_data = json.loads(message)
                    except json.JSONDecodeError:
                        self._log_ws_request(client_id, message, None)
                        self.logger.error(f"无效的JSON消息: {message}")
                        continue

                    # 检查是否为操纵杆相关消息
                    message_type = message_data.get('type', '')
                    if should_log_ws_message(message_data):
                        self.logger.info("RAW WebSocket message client=%s: %s", client_id, message)
                        self.logger.debug(
                            f"接收到消息: {message[:50]}..."
                            if len(message) > 50 else message
                        )
                        self._log_ws_request(client_id, message, message_data)

                    if message_type == 'ue_ping':
                        self.client_sessions.setdefault(client_id, {})['client_role'] = 'ue'
                        await self.send_message(websocket, {
                            'type': 'ue_pong',
                            'timestamp': int(time.time() * 1000),
                        })
                        continue

                    is_platform_packet = (
                        message_type == 'platform_task' or
                        (not message_type and
                         message_data.get('TaskName') and
                         str(message_data.get('ID', '')).strip())
                    )
                    if is_platform_packet:
                        from network.platform_task_bridge import handle_platform_task_ws
                        for reply in await handle_platform_task_ws(
                            self,
                            client_id,
                            message_data,
                            gaze_svc=self._gaze_svc,
                            physio_svc=self._physio_svc,
                            external_collectors=self._external_collectors,
                        ):
                            await self._send_platform_task_reply(websocket, client_id, reply)
                        continue

                    if message_type == 'platform_task_result':
                        from network.platform_task_bridge import handle_platform_task_result_ws
                        for reply in handle_platform_task_result_ws(
                            message_data,
                            gaze_svc=self._gaze_svc,
                            physio_svc=self._physio_svc,
                            external_collectors=self._external_collectors,
                        ):
                            await self._send_platform_task_reply(websocket, client_id, reply)
                        continue

                    # tobii_hand：更新眼动注意力区域（等价于 POST /tobii/hand）
                    if message_type in {'external_pose_record', 'external_pose_data'}:
                        from network.external_pose_storage import handle_external_pose_record
                        reply = await asyncio.to_thread(
                            handle_external_pose_record,
                            message_data,
                        )
                        await self._send_platform_task_reply(websocket, client_id, reply)
                        continue

                    if message_type == 'external_behavior_record':
                        from network.external_behavior_storage import handle_external_behavior_record
                        reply = await asyncio.to_thread(
                            handle_external_behavior_record,
                            message_data,
                        )
                        await self._send_platform_task_reply(websocket, client_id, reply)
                        continue

                    if message_type == 'tobii_hand':
                        reply = await self._handle_tobii_hand(message_data)
                        await self.send_message(websocket, reply)
                        continue

                    if message_type == 'tobii_aoi_snapshot':
                        reply = await self._handle_tobii_aoi_snapshot(message_data)
                        await self.send_message(websocket, reply)
                        continue

                    # 收到 joystick_connect 时触发延迟初始化
                    if message_type == 'tobii_marker':
                        reply = await self._handle_tobii_marker(message_data)
                        await self.send_message(websocket, reply)
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
                            await self.send_message(websocket, {"type": "config_update_result", "status": "ok", "changes": changes})
                        except Exception as e:
                            self.logger.error(f"配置更新失败: {e}", exc_info=True)
                            await self.send_message(websocket, {"type": "config_update_result", "status": "error", "message": str(e)})
                        continue

                    if message_type.startswith('joystick_') and self.joystick_handler:
                        try:
                            # 使用操纵杆处理器处理消息
                            joystick_result = await self.joystick_handler.handle_message(client_id, message_data)
                            await self.send_message(websocket, joystick_result)
                            continue
                        except Exception as e:
                            self.logger.error(f"操纵杆消息处理失败: {e}")
                            error_response = {
                                'type': 'error',
                                'message': f'操纵杆消息处理失败: {str(e)}'
                            }
                            await self.send_message(websocket, error_response)
                            continue
                    
                    # 获取客户端会话状态
                    session_state = self.client_sessions.get(client_id, {})
                    
                    # 使用原有的消息处理器处理非操纵杆消息（延迟导入避免循环依赖）
                    from core import message_handler
                    result = await message_handler.handle_client_message(message, session_state, websocket)

                    if message_type == 'task_exit_request' and isinstance(result, list):
                        for msg in result:
                            if isinstance(msg, dict) and msg.get('type') == 'task_exit_requested':
                                # The requester may also be the client responsible for closing
                                # the UE task UI, so broadcast the notification to every peer.
                                await self.broadcast_to_clients_except(msg, None)
                        continue
                    
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
                                await self._send_raw_message(websocket, json.dumps(settings_updated))

                            # 现在准备并发送主数据帧
                            data = target_manager.get_radar_data(include_targets=include_targets)
                            data["type"] = "radar_data"
                            if settings_updated.get("task_id") is not None:
                                data["task_id"] = settings_updated["task_id"]
                            data["_timestamp"] = time.time()
                            data_json = json.dumps(data)

                            if include_targets:
                                self.logger.debug(f"正在发送包含目标的数据，JSON长度: {len(data_json)}")
                                self.logger.debug(f"数据键: {list(data.keys())}")
                                if 'externalTargets' in data:
                                    self.logger.debug(f"externalTargets长度: {len(data['externalTargets'])}")
                            else:
                                self.logger.debug(f"正在发送不含目标的数据，JSON长度: {len(data_json)}")
                            
                            await self._send_raw_message(websocket, data_json)
                            
                            if include_targets:
                                self.logger.info("已发送更新后的数据（包含目标）")
                            else:
                                self.logger.info("已发送更新后的数据（不含目标）")
                                
                except asyncio.TimeoutError:
                    pass
                except websockets.exceptions.ConnectionClosed:
                    self.logger.debug("WebSocket connection closed by client")
                    break
                    
        except websockets.exceptions.ConnectionClosed:
            self.logger.debug("WebSocket client disconnected")
        except Exception as e:
            self.logger.error(f"WebSocket处理时出错: {e}", exc_info=True)
        finally:
            # 清理客户端连接
            self.remove_client(client_id)
    
    async def _handle_tobii_hand(self, data: dict) -> dict:
        """
        处理 tobii_hand 消息，逻辑与 POST /tobii/hand 一致。

        消息格式（目标出现）:
            {"type": "tobii_hand", "box_visible": true, "task_id": 123,
             "coordinate_space": "display_area_normalized",
             "regions": [{"shape": "rect", "left": x1, "top": y1, "right": x2, "bottom": y2}]}
        消息格式（目标消失）:
            {"type": "tobii_hand", "box_visible": false, "task_id": 123}

        Returns:
            响应 dict，含 ok / msg / task_id 字段。
        """
        if self._gaze_svc is None:
            return {"type": "tobii_hand_result", "ok": False, "msg": "眼动追踪服务未启动"}

        self.logger.warning(
            "[TOBII_HAND_REQUEST] WS tobii_hand payload=%s",
            json.dumps(data, ensure_ascii=False, default=str),
        )

        if "box_visible" not in data:
            return {"type": "tobii_hand_result", "ok": False, "msg": "缺少字段: box_visible"}

        box_visible = bool(data.get("box_visible"))
        task_id = data.get("task_id")
        task_name = data.get("task_name")
        effective_task_id = None if task_name == "WeaponLaunchMission" else task_id
        if task_name == "WeaponLaunchMission" and task_id is not None:
            self.logger.warning(
                "[TOBII_HAND_REQUEST] WS tobii_hand ignoring request task_id for WeaponLaunchMission; "
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
            return {
                "type": "tobii_hand_result",
                "ok": updated,
                "msg": "bbox 已更新" if updated else "无活动任务，bbox 未更新",
                "task_id": active_id,
            }
        else:
            updated = self._gaze_svc.set_task_bbox(
                bbox=[],
                screen_size=None,
                task_id=str(effective_task_id) if effective_task_id is not None else None,
            )
            return {
                "type": "tobii_hand_result",
                "ok": True,
                "msg": "目标框消失，bbox 已清空",
                "task_id": self._gaze_svc.get_active_task_id(),
            }

    async def _handle_tobii_aoi_snapshot(self, data: dict) -> dict:
        """Store analysis-only AOIs without touching attention regions."""
        if self._gaze_svc is None:
            return {
                "type": "tobii_aoi_snapshot_result",
                "ok": False,
                "msg": "gaze service is not available",
            }
        def optional_identifier(value: Any) -> Optional[str]:
            if value is None:
                return None
            text = str(value).strip()
            return text or None

        try:
            result = self._gaze_svc.set_analysis_aoi_snapshot(
                task_id=optional_identifier(data.get("task_id")),
                trial_id=optional_identifier(data.get("trial_id")),
                task_group_id=optional_identifier(data.get("task_group_id")),
                task_type=str(data.get("task_type") or "").strip(),
                client_snapshot_id=optional_identifier(data.get("client_snapshot_id")),
                client_captured_at_ms=(
                    int(data.get("captured_at_ms"))
                    if data.get("captured_at_ms") is not None else None
                ),
                change_reasons=(
                    data.get("change_reasons")
                    if isinstance(data.get("change_reasons"), list) else []
                ),
                coordinate_space=(
                    data.get("coordinate_space")
                    if isinstance(data.get("coordinate_space"), str) else None
                ),
                display=data.get("display") if isinstance(data.get("display"), dict) else {},
                regions=data.get("regions") if isinstance(data.get("regions"), list) else [],
            )
        except (TypeError, ValueError) as exc:
            return {
                "type": "tobii_aoi_snapshot_result",
                "ok": False,
                "msg": str(exc),
                "task_id": self._gaze_svc.get_active_task_id(),
                "client_snapshot_id": data.get("client_snapshot_id"),
            }
        return {
            "type": "tobii_aoi_snapshot_result",
            "client_snapshot_id": data.get("client_snapshot_id"),
            **result,
        }

    async def _handle_tobii_marker(self, data: dict) -> dict:
        """Handle a WebSocket Tobii marker message."""
        if self._gaze_svc is None:
            return {"type": "tobii_marker_result", "ok": False, "msg": "Tobii gaze service is not available"}

        try:
            marker = self._gaze_svc.record_marker(
                name=data.get("name") or data.get("marker") or data.get("event") or "",
                payload=data.get("payload") if isinstance(data.get("payload"), dict) else {},
                task_id=data.get("task_id"),
                user_id=data.get("user_id", ""),
                system_time=data.get("system_time"),
            )
        except ValueError as e:
            return {"type": "tobii_marker_result", "ok": False, "msg": str(e)}
        except Exception as e:
            self.logger.error(f"Tobii marker failed: {e}", exc_info=True)
            return {"type": "tobii_marker_result", "ok": False, "msg": str(e)}

        return {"type": "tobii_marker_result", "ok": True, "marker": marker}

    async def start_server(self) -> None:
        """启动WebSocket服务器"""
        self.logger.info(f"雷达服务器启动中... ws://{self.host}:{self.port}")
        
        async with websockets.serve(self.handle_client, self.host, self.port, subprotocols=["ws"]):
            self.logger.info(f"雷达服务器已启动于 ws://{self.host}:{self.port}")
            await asyncio.Future()  # 运行直到被取消

# 全局WebSocket服务器实例
websocket_server = WebSocketServer() 
