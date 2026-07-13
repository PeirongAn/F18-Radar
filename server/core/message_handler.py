import json
import time
import random
import asyncio
from typing import Dict, Any, List, Tuple, Optional, Union

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from managers import config_manager, db_manager, TaskScenarioManager, generate_task_id, target_manager, threat_manager, get_logger
from network.platform_task_bridge import (
    peek_pending_include_ai,
    consume_pending_for_task_start,
    get_active_overlay_for_task,
    get_progress_key_for_task,
)
from models.threat_models import RadarConfig
from network.message_protocol import message_protocol

class MessageHandler:
    """消息处理器，负责处理客户端消息和业务逻辑"""
    
    def __init__(self):
        self.current_session = {
            'task_id': None,
            'task_ids': {},
            'task_started_at_ms': None,
            'task_started_at_ms_by_type': {},
            'stage': 'init',
            'target_elevation': None,
            'operations': []
        }
        # 协议配置
        self.use_enhanced_protocol = True  # 默认使用增强协议
        # 眼动追踪服务（由 main.py 的 initialize_system 注入，可为 None）
        self._gaze_svc = None
        self._physio_svc = None
        self._external_collectors = None
        self.logger = get_logger("message_handler")

    def _set_current_task(self, task_type: str, task_id, started_at_ms: int) -> None:
        self.current_session['task_id'] = task_id
        self.current_session.setdefault('task_ids', {})[task_type] = task_id
        self.current_session['task_started_at_ms'] = started_at_ms
        self.current_session.setdefault('task_started_at_ms_by_type', {})[task_type] = started_at_ms

    def _get_current_task_id(self, task_type: str = ''):
        if task_type:
            task_ids = self.current_session.get('task_ids') or {}
            if task_type in task_ids:
                return task_ids.get(task_type)
        return self.current_session.get('task_id')

    def _get_task_started_at_ms(self, task_type: str = ''):
        if task_type:
            started_by_type = self.current_session.get('task_started_at_ms_by_type') or {}
            if task_type in started_by_type:
                return started_by_type.get(task_type)
        return self.current_session.get('task_started_at_ms')

    def _task_run_config(
        self,
        current_scenario: Optional[Dict[str, Any]],
        event_owner: str,
        trust_state: str = "",
        platform_meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        scenario = current_scenario or {}
        return json.dumps({
            "event_owner": event_owner,
            "trust_state": trust_state,
            "repetition_info": scenario.get("repetition_info"),
            "difficulty_name": scenario.get("difficulty_name"),
            "difficulty_config": scenario.get("difficulty_config"),
            "is_ai_active": scenario.get("is_ai_active"),
            "ai_level_name": scenario.get("ai_level_name"),
            "audio_enabled": scenario.get("audio_enabled"),
            "platform_task": platform_meta,
        }, ensure_ascii=False)

    def _ensure_unified_task_run(
        self,
        task_id,
        task_type: str,
        user_id: str,
        current_scenario: Optional[Dict[str, Any]],
        event_owner: str,
        trust_state: str,
        message: Dict[str, Any],
        started_at_ms: int,
        platform_meta: Optional[Dict[str, Any]] = None,
        group_id: Optional[int] = None,
        task_seq: Optional[int] = None,
        reactivate: bool = False,
    ) -> None:
        if not task_id:
            return
        try:
            db_manager.ensure_task_run(
                task_id=int(task_id),
                task_type=task_type,
                user_id=user_id or "",
                expected_subtasks=1,
                started_at_ms=started_at_ms,
                config_json=self._task_run_config(current_scenario, event_owner, trust_state, platform_meta),
                raw_message_json=json.dumps(message or {}, ensure_ascii=False),
                group_id=group_id,
                task_seq=task_seq,
                reactivate=reactivate,
            )
            db_manager.record_task_event(
                task_id=int(task_id),
                task_type=task_type,
                user_id=user_id or "",
                event_type="task_start",
                timestamp_ms=started_at_ms,
                payload_json=self._task_run_config(current_scenario, event_owner, trust_state, platform_meta),
                raw_message_json=json.dumps(message or {}, ensure_ascii=False),
            )
        except Exception as e:
            self.logger.warning("ensure unified task_run failed: task_id=%s task_type=%s error=%s", task_id, task_type, e, exc_info=True)

    def _ensure_current_task_group(
        self,
        task_manager: TaskScenarioManager,
        task_type: str,
        user_id: str,
        current_scenario: Dict[str, Any],
        event_owner: str,
        trust_state: str,
        message: Dict[str, Any],
        started_at_ms: int,
        progress_key: str,
        platform_meta: Optional[Dict[str, Any]] = None,
        force_new_group: bool = False,
    ) -> Tuple[Optional[int], Optional[int]]:
        if not current_scenario:
            return None, None
        repetition_info = current_scenario.get("repetition_info") or {}
        task_seq = repetition_info.get("current")
        try:
            task_seq = int(task_seq)
        except (TypeError, ValueError):
            task_seq = None
        # A newly consumed platform task represents a new task group even when
        # its difficulty/autonomy combination restores a previously persisted
        # scenario.  Never carry that scenario's old group id into the new run.
        if force_new_group:
            current_scenario.pop("task_group_id", None)
            repetition_info.pop("task_group_id", None)

        task_group_id = current_scenario.get("task_group_id") or repetition_info.get("task_group_id")
        if not task_group_id:
            task_group_id = generate_task_id()
            current_scenario["task_group_id"] = task_group_id
            repetition_info["task_group_id"] = task_group_id
            current_scenario["repetition_info"] = repetition_info
            try:
                if getattr(task_manager, "is_practice", False):
                    task_manager._save_to_memory()
                else:
                    task_manager._save_to_db()
            except Exception as e:
                self.logger.warning("persist task_group_id failed: task_type=%s group_id=%s error=%s", task_type, task_group_id, e, exc_info=True)
        try:
            db_manager.ensure_task_group(
                group_id=int(task_group_id),
                task_type=task_type,
                user_id=user_id or "",
                expected_task_count=int(repetition_info.get("total") or 1),
                started_at_ms=started_at_ms,
                config_json=self._task_run_config(current_scenario, event_owner, trust_state, platform_meta),
                raw_message_json=json.dumps(message or {}, ensure_ascii=False),
                difficulty=current_scenario.get("external_difficulty_display") or current_scenario.get("difficulty_name"),
                autonomy_level=current_scenario.get("autonomy_level") or current_scenario.get("ai_level_name"),
                is_ai_active=current_scenario.get("is_ai_active"),
                is_practice=getattr(task_manager, "is_practice", False),
                progress_key=progress_key,
            )
        except Exception as e:
            self.logger.warning("ensure task_group failed: task_type=%s group_id=%s error=%s", task_type, task_group_id, e, exc_info=True)
        return int(task_group_id), task_seq

    def _get_task_trust_state(self, task_type: str) -> str:
        """Return the configured trust state for the task type stored in task_settings."""
        trust_config = config_manager.get_trust_calibration_config()
        state_config = trust_config.get('state') if isinstance(trust_config, dict) else None
        if isinstance(state_config, str):
            return state_config
        if not isinstance(state_config, dict):
            return ''
        state_key = 'threat' if task_type == 'SA_THREAT_RESPONSE' else 'sensor'
        state = state_config.get(state_key)
        return state if isinstance(state, str) else ''

    def set_gaze_service(self, gaze_svc) -> None:
        """注入眼动追踪服务（由 server/main.py 的 initialize_system 调用）。"""
        self._gaze_svc = gaze_svc

    def set_physio_service(self, physio_svc) -> None:
        """注入手环/指环生理记录服务（可为 None）。"""
        self._physio_svc = physio_svc

    def set_external_collector_manager(self, external_collectors) -> None:
        """Inject optional external physiological collector integrations."""
        self._external_collectors = external_collectors

    def _gaze_start(self, task_id, user_id: str = "", task_name: str = "", task_source: str = "") -> None:
        """任务开始时启动 gaze 追踪（无 Tobii 设备时静默跳过）。"""
        if self._gaze_svc is None:
            return
        try:
            # bbox 为空列表：主服务器阶段不知道目标框像素坐标，
            # 前端后续通过 /tobii/hand 调用 set_task_bbox() 更新。
            self._gaze_svc.start_task(
                bbox=[],
                screen_size=(1, 1),
                task_id=task_id,
                user_id=user_id,
                task_source=task_source,
                task_name=task_name,
                start_trigger="task_start",
            )
        except Exception as e:
            print(f"[MessageHandler] gaze start_task 失败（已跳过）: {e}")

    def _gaze_stop(self, task_id=None) -> None:
        """任务结束时停止 gaze 追踪（无 Tobii 设备时静默跳过）。"""
        if self._gaze_svc is None:
            return
        try:
            resolved = task_id or self._gaze_svc.get_active_task_id()
            if resolved:
                self._gaze_svc.stop_task(task_id=str(resolved), end_trigger="task_result_confirmed")
        except Exception as e:
            print(f"[MessageHandler] gaze stop_task 失败（已跳过）: {e}")

    def _physio_should_record(self, session_state: Dict[str, Any]) -> bool:
        return self._physio_svc is not None and not session_state.get('is_practice', False)

    def _external_collectors_should_record(self, session_state: Dict[str, Any]) -> bool:
        return self._external_collectors is not None and not session_state.get('is_practice', False)

    def _physio_task_metadata(
        self,
        task_type: str,
        user_id: str,
        task_id,
        event_owner: str,
        current_scenario: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        scenario = current_scenario or {}
        return {
            "source": "F18-Radar",
            "f18_task_id": task_id,
            "task_type": task_type,
            "user_id": user_id,
            "event_owner": event_owner,
            "is_ai_active": bool(scenario.get("is_ai_active")),
            "difficulty_config": scenario.get("difficulty_config"),
            "ai_level": scenario.get("ai_level_name"),
            "audio_enabled": scenario.get("audio_enabled"),
            "repetition_info": scenario.get("repetition_info"),
        }

    def _physio_start_task(
        self,
        task_type: str,
        user_id: str,
        task_id,
        event_owner: str,
        current_scenario: Optional[Dict[str, Any]],
        session_state: Dict[str, Any],
    ) -> None:
        if not self._physio_should_record(session_state) and not self._external_collectors_should_record(session_state):
            return
        try:
            metadata = self._physio_task_metadata(task_type, user_id, task_id, event_owner, current_scenario)
            if self._physio_should_record(session_state):
                self._physio_svc.set_subject(user_id, {"source": "F18-Radar", "last_task_type": task_type})
                self._physio_svc.start_task(task_type, metadata, run_id=str(task_id))
                self._physio_svc.marker("task_start", metadata)
            if self._external_collectors_should_record(session_state):
                self._external_collectors.start_task(task_type, user_id, str(task_id), metadata)
                self._external_collectors.marker("task_start", metadata)
        except Exception as e:
            self.logger.warning("physio start_task failed: %s", e, exc_info=True)

    def _physio_marker(
        self,
        name: str,
        message: Dict[str, Any],
        session_state: Dict[str, Any],
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self._physio_should_record(session_state) and not self._external_collectors_should_record(session_state):
            return
        try:
            payload_task_type = (extra or {}).get("task_type") or message.get("task_type") or ""
            payload = {
                "source": "F18-Radar",
                "f18_task_id": self._get_current_task_id(payload_task_type),
                "task_type": payload_task_type or message.get("task_type"),
                "user_id": message.get("user_id") or self.current_session.get("user_id", ""),
                "event_owner": message.get("event_owner", ""),
                "timestamp": message.get("timestamp"),
                "receive_timestamp": message.get("receive_timestamp"),
                "message": message,
            }
            if extra:
                payload.update(extra)
            if self._physio_should_record(session_state):
                self._physio_svc.marker(name, payload)
            if self._external_collectors_should_record(session_state):
                self._external_collectors.marker(name, payload)
        except Exception as e:
            self.logger.warning("physio marker failed: name=%s error=%s", name, e, exc_info=True)

    def _physio_stop_task(
        self,
        task_type: str,
        user_id: str,
        task_id,
        event_owner: str,
        repetition_info: Dict[str, Any],
        message: Dict[str, Any],
        session_state: Dict[str, Any],
    ) -> None:
        if not self._physio_should_record(session_state) and not self._external_collectors_should_record(session_state):
            return
        try:
            payload = {
                "source": "F18-Radar",
                "f18_task_id": task_id,
                "task_type": task_type,
                "user_id": user_id,
                "event_owner": event_owner,
                "repetition_info": repetition_info,
                "message": message,
            }
            if self._physio_should_record(session_state):
                self._physio_svc.marker("task_result_confirmed", payload)
                self._physio_svc.stop_task()
                self._physio_svc.clear_subject()
            if self._external_collectors_should_record(session_state):
                self._external_collectors.marker("task_result_confirmed", payload)
                self._external_collectors.stop_task(str(task_id))
                self._external_collectors.clear_subject()
        except Exception as e:
            self.logger.warning("physio stop_task failed: %s", e, exc_info=True)

    def _log_task_count_notice(
        self,
        phase: str,
        task_type: str,
        user_id: str,
        task_id,
        repetition_info: Dict[str, Any],
        event_owner: str = "",
        platform_id: str = "",
    ) -> None:
        """打印醒目的远端任务计数日志。"""
        rep_info = repetition_info or {}
        current = rep_info.get("current")
        total = rep_info.get("total")
        if current is None and total is None:
            count_text = "任务次数未知"
        elif current is None:
            count_text = f"共{total}次任务"
        elif total is None:
            count_text = f"第{current}次任务{phase}"
        else:
            count_text = f"共{total}次任务；第{current}次任务{phase}"
        self.logger.warning(
            "[REMOTE_TASK_COUNT] ===== %s ===== task_type=%s user=%s task_id=%s "
            "event_owner=%s platform_id=%s rep_info=%s",
            count_text,
            task_type,
            user_id,
            task_id,
            event_owner,
            platform_id,
            rep_info,
        )

    def _extract_repetition_override(self, message: Dict[str, Any]) -> Optional[int]:
        """读取前端初始化弹窗或平台消息传入的任务次数。"""
        for key in ('repetition_total_override', 'task_number', 'taskNumber', 'TaskNumber'):
            value = message.get(key)
            if value is None or value == '':
                continue
            try:
                return max(1, int(value))
            except (TypeError, ValueError):
                continue
        return None
    
    async def handle_client_message(self, message_str: str, session_state: Dict[str, Any], 
                                  websocket=None) -> Union[List[Dict[str, Any]], Tuple[Dict[str, Any], bool], bool]:
        """处理客户端消息"""
        try:
            print("\n===== 接收到客户端消息 =====")
            print(f"原始消息: {message_str}")
            
            message = json.loads(message_str)
            print(f"解析后的消息: {message}")
            
            message_type = message.get('type', '')
            client_event_owner = message.get('event_owner', '')

            # 路由到具体的处理方法
            if message_type == 'task_start':
                return await self._handle_task_start(message, session_state)
            elif message_type == 'settings_update':
                return await self._handle_settings_update(message, session_state, client_event_owner)
            elif message_type == 'antenna_adjusted':
                return await self._handle_antenna_adjusted(message, session_state, client_event_owner)
            elif message_type == 'target_selected':
                return await self._handle_target_selected(message, session_state, client_event_owner)
            elif message_type == 'threat_clicked':
                return await self._handle_threat_clicked(message, session_state, client_event_owner)
            elif message_type == 'task_result_confirmed':
                return await self._handle_task_result_confirmed(message, session_state)
            elif message_type == 'task_exit_request':
                return await self._handle_task_exit_request(message)
            elif message_type == 'record_operation':
                return await self._handle_record_operation(message, session_state, client_event_owner)
            elif message_type == 'record_bulk_operations':
                return await self._handle_record_bulk_operations(message, session_state, client_event_owner)
            elif message_type in ['SwitchSA', 'ResetSA']:
                return await self._handle_sa_operations(message, session_state, websocket)
            elif message_type.startswith('joystick_'):
                return await self._handle_joystick_message(message, session_state, websocket)
            # elif message_type == 'reset_targets':
            #     return await self._handle_reset_targets(message, session_state)
            else:
                print(f"未知消息类型: {message_type}")
                return []
                
        except json.JSONDecodeError as e:
            print(f"解析JSON时出错: {e}")
        except Exception as e:
            print(f"处理客户端消息时出错: {e}")
        
        print("===== 客户端消息处理失败 =====\n")
        return []
    
    async def _handle_task_start(self, message: Dict[str, Any], session_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """处理任务开始消息"""
        self.logger.info(
            "TASK_START WebSocket fields: %s",
            json.dumps(message, ensure_ascii=False, sort_keys=True),
        )
        print("消息类型: task_start", message.get('user_id', ''))
        user_id = message.get('user_id', '')
        task_type = 'RADAR_TARGETING'
        is_ai_active_request = message.get('include_ai', False)
        pending_ai = peek_pending_include_ai(user_id, task_type)
        if pending_ai is not None:
            is_ai_active_request = bool(pending_ai)
        event_owner = 'AI' if is_ai_active_request else 'manual'
        is_practice = message.get('is_practice', False)
        session_state['is_practice'] = is_practice

        if not user_id:
            return [{"type": "error", "message": "user_id is required for task_start"}]
        
        # 将 user_id 保存到全局会话，以便后续操作使用
        self.current_session['user_id'] = user_id
        self.current_session['target_elevation'] = None
        self.current_session['stage'] = 'init'
        
        progress_key = get_progress_key_for_task(user_id, task_type)
        
        # 创建或加载与用户绑定的持久化任务管理器
        task_manager = TaskScenarioManager(
            config_manager.get_config(),
            user_id,
            task_type,
            is_practice=is_practice,
            is_ai_active_request=is_ai_active_request,
            progress_key=progress_key,
        )
        repetition_override = self._extract_repetition_override(message)
        if repetition_override is not None:
            task_manager.max_repetitions = repetition_override
            task_manager.apply_repetition_override(repetition_override, overwrite=True)
        session_state['task_manager'] = task_manager

        overlay_source = "pending"
        overlay, platform_meta = consume_pending_for_task_start(user_id, task_type)
        if not overlay:
            overlay_source = "active"
            overlay, platform_meta = get_active_overlay_for_task(user_id, task_type)
        normalized_meta = (platform_meta or {}).get("normalized") or {}
        if overlay and task_manager.current_scenario:
            task_manager.apply_platform_overlay(overlay)
        
        # 从管理器获取下一个任务场景
        current_scenario = task_manager.get_next_task_parameters(is_ai_active_request)
        self.logger.info(
            "[REMOTE_TASK_COUNT] radar get_next returned user=%s progress=%s "
            "scenario=%s rep_info=%s",
            user_id,
            progress_key,
            bool(current_scenario),
            (current_scenario or {}).get('repetition_info') if isinstance(current_scenario, dict) else current_scenario,
        )

        if current_scenario == "ALL_COMPLETED":
            return [{
                "type": "all_tasks_completed",
                "task_type": task_type,
                "message": "所有传感器任务已完成。",
                "is_ai_active": bool(is_ai_active_request),
                "is_practice": bool(is_practice),
            }]
        if not current_scenario:
            return [{
                "type": "all_tasks_completed",
                "task_type": task_type,
                "message": f"当前模式的{task_type}任务已完成。",
                "is_ai_active": bool(is_ai_active_request),
                "is_practice": bool(is_practice),
            }]

        self.logger.info(
            "[REMOTE_TASK_COUNT] radar overlay resolved user=%s task_type=%s progress=%s "
            "source=%s has_overlay=%s id=%s raw_TaskNumber=%s rep_override=%s "
            "scenario_rep_before=%s",
            user_id,
            task_type,
            progress_key,
            overlay_source,
            bool(overlay),
            normalized_meta.get("platform_task_id"),
            normalized_meta.get("task_number"),
            normalized_meta.get("repetition_total_override"),
            current_scenario.get('repetition_info') if isinstance(current_scenario, dict) else current_scenario,
        )
        if overlay:
            task_manager.apply_platform_overlay(overlay)
            current_scenario = task_manager.current_scenario
            event_owner = 'AI' if current_scenario['is_ai_active'] else 'manual'
            self.logger.info(
                "[REMOTE_TASK_COUNT] radar overlay applied user=%s task_type=%s progress=%s "
                "event_owner=%s rep_info=%s override=%s",
                user_id,
                task_type,
                progress_key,
                event_owner,
                current_scenario.get('repetition_info'),
                current_scenario.get('max_repetitions_override'),
            )
        if repetition_override is not None:
            task_manager.apply_repetition_override(repetition_override, overwrite=True)
            current_scenario = task_manager.current_scenario
        
        self.current_session[f'{task_type}_scenario'] = current_scenario
        trust_state = self._get_task_trust_state(task_type)
        existing_task_id = db_manager.find_existing_task_setting_id(
            current_scenario,
            user_id,
            event_owner,
            task_type,
            trust_state,
        )
        is_retrying_incomplete_task = bool(
            existing_task_id and
            current_scenario.get('repetition_info', {}).get('previous_task_completed') is False
        )
        if is_retrying_incomplete_task:
            db_manager.clear_task_operations(existing_task_id)
        task_started_at_ms = int(time.time() * 1000)
        task_group_id, task_seq = self._ensure_current_task_group(
            task_manager,
            task_type,
            user_id,
            current_scenario,
            event_owner,
            trust_state,
            message,
            task_started_at_ms,
            progress_key,
            platform_meta=platform_meta,
            force_new_group=overlay_source == "pending" and bool(platform_meta),
        )
        task_id = existing_task_id or generate_task_id()
        self._set_current_task(task_type, task_id, task_started_at_ms)
        self._ensure_unified_task_run(
            task_id,
            task_type,
            user_id,
            current_scenario,
            event_owner,
            trust_state,
            message,
            task_started_at_ms,
            platform_meta=platform_meta,
            group_id=task_group_id,
            task_seq=task_seq,
            reactivate=is_retrying_incomplete_task,
        )
        
        # 记录操作
        should_record_task_start = (not existing_task_id) or is_retrying_incomplete_task
        if not session_state.get('is_practice', False) and should_record_task_start:
            operation = {
                'task_id': task_id,
                'operationType': 'task_start',
                'timestamp': message.get('timestamp', int(time.time() * 1000)),
                'isActive': True,
                'parameters': {'include_ai': current_scenario['is_ai_active']},
                'user_id': user_id,
                'event_owner': event_owner
            }
            db_manager.record_operation(operation, session_state.get('is_practice', False))
        else:
            print("练习模式或重复启动，跳过 task_start 数据库记录。")

        db_manager.record_task_settings(
            task_id,
            current_scenario,
            user_id,
            event_owner,
            session_state.get('is_practice', False),
            task_type,
            trust_state,
        )
        target_manager.initialize_targets(current_scenario['difficulty_config'])

        # 启动眼动追踪（有 Tobii 时生效，否则静默跳过）
        self._gaze_start(task_id, user_id=user_id, task_name=task_type, task_source=event_owner)
        self._physio_start_task(task_type, user_id, task_id, event_owner, current_scenario, session_state)

        init_response = {
            "type": "init_settings",
            "task_id": task_id,
            "timestamp": time.time() * 1000,
            "settings": {"range": 80, "scanAngle": 30},
            "is_ai_active": current_scenario['is_ai_active'],
            "ai_level": current_scenario.get('ai_level_name'),
            "ai_configs": config_manager.get_ai_levels(),
            "audio_enabled": current_scenario['audio_enabled'],
            "trust_calibration": config_manager.get_trust_calibration_config(),
            "repetition_info": current_scenario['repetition_info'],
            "task_type": task_type
        }
        if platform_meta:
            init_response["platform_task"] = platform_meta
        self._log_task_count_notice(
            "开始",
            task_type,
            user_id,
            task_id,
            init_response.get("repetition_info"),
            event_owner=event_owner,
            platform_id=normalized_meta.get("platform_task_id"),
        )
        self.logger.info(
            "[REMOTE_TASK_COUNT] radar init_response user=%s task_id=%s progress=%s "
            "event_owner=%s rep_info=%s platform_id=%s",
            user_id,
            task_id,
            progress_key,
            event_owner,
            init_response.get("repetition_info"),
            normalized_meta.get("platform_task_id"),
        )
        initial_radar_data = target_manager.get_radar_data(include_targets=False)
        initial_radar_data.update({
            "type": "radar_data",
            "task_id": task_id,
            "task_type": task_type,
        })
        return [init_response, initial_radar_data]
    
    async def _handle_settings_update(self, message: Dict[str, Any], session_state: Dict[str, Any], 
                                    client_event_owner: str) -> List[Dict[str, Any]]:
        """处理设置更新消息"""
        print("消息类型: settings_update")
        
        # 验证雷达参数是否与init_settings一致
        client_range = message.get('range')
        client_scan_angle = message.get('scanAngle')
        required_range = 80
        required_scan_angle = 30

        if client_range == required_range and client_scan_angle == required_scan_angle:
            # 参数正确，进入天线调整阶段
            print("雷达参数验证成功，发送天线调整指令。")
            
            task_id = self._get_current_task_id('RADAR_TARGETING')
            if not session_state.get('is_practice', False) and task_id:
                operation = {
                    'task_id': task_id,
                    'operationType': 'settings_update',
                    'timestamp': message.get('timestamp', int(time.time() * 1000)),
                    'receive_timestamp': message.get('receive_timestamp'),
                    'isActive': True,
                    'parameters': message,
                    'user_id': message.get('user_id', ''),
                    'event_owner': client_event_owner
                }
                db_manager.record_operation(operation, session_state.get('is_practice', False))
            else:
                print("练习模式，跳过 settings_update 数据库记录。")

            self._physio_marker("settings_update", message, session_state, {
                "operation": "settings_update",
                "task_type": "RADAR_TARGETING",
                "range": client_range,
                "scanAngle": client_scan_angle,
            })

            validation_response = {"type": "settings_validation", "status": "success", "message": "雷达参数设置正确，请继续进行天线高度调整"}
            antenna_command = self._generate_antenna_adjustment()
            return [validation_response, antenna_command]
        else:
            # 参数不正确
            print(f"雷达参数验证失败。需要: range={required_range}, scanAngle={required_scan_angle}。收到: range={client_range}, scanAngle={client_scan_angle}")
            validation_response = {"type": "settings_validation", "status": "error", "message": "雷达参数设置不正确，请调整参数"}
            return [validation_response]
    
    async def _handle_antenna_adjusted(self, message: Dict[str, Any], session_state: Dict[str, Any], 
                                     client_event_owner: str) -> Union[Tuple[Dict[str, Any], bool], List[Dict[str, Any]]]:
        """处理天线调整消息"""
        print("消息类型: antenna_adjusted")
        
        validation_response, is_valid = self._handle_antenna_adjustment(message)
        if validation_response.get("status") == "ignored":
            return []
        if is_valid:
            task_id = self._get_current_task_id('RADAR_TARGETING')
            if not session_state.get('is_practice', False) and task_id:
                operation = {
                    'task_id': task_id,
                    'operationType': 'antenna_adjusted',
                    'timestamp': message.get('timestamp', int(time.time() * 1000)),
                    'receive_timestamp': message.get('receive_timestamp'),
                    'isActive': True,
                    'parameters': {'elevation': message.get('elevation')},
                    'user_id': message.get('user_id', ''),
                    'event_owner': client_event_owner
                }
                db_manager.record_operation(operation, session_state.get('is_practice', False))
            else:
                print("练习模式，跳过 antenna_adjusted 数据库记录。")

            self._physio_marker("antenna_adjusted", message, session_state, {
                "operation": "antenna_adjusted",
                "task_type": "RADAR_TARGETING",
                "elevation": message.get("elevation"),
            })

            return validation_response, True
        else:
            return [validation_response]
    
    async def _handle_target_selected(self, message: Dict[str, Any], session_state: Dict[str, Any], 
                                    client_event_owner: str) -> List[Dict[str, Any]]:
        """处理目标选择消息"""
        print("消息类型: target_selected")
        target_id = message.get('target_id')
        iff_mode = message.get('iff_mode', False)
        
        targets = target_manager.get_targets()
        is_enemy = any(target['id'] == target_id and target['type'] == 'army' for target in targets)
        
        task_id = self._get_current_task_id('RADAR_TARGETING')
        if not session_state.get('is_practice', False) and task_id:
            operation = {
                'task_id': task_id,
                'operationType': 'target_selected',
                'timestamp': message.get('timestamp', int(time.time() * 1000)),
                'receive_timestamp': message.get('receive_timestamp'),
                'isActive': not iff_mode,
                'parameters': {
                    'target_id': target_id,
                    'action': message.get('action', 'select'),
                    'iff_mode': iff_mode,
                    'is_enemy': is_enemy,
                    'is_correct': (is_enemy and not iff_mode) or False,
                    'extra': message.get('extra', {})
                },
                'user_id': message.get('user_id', ''),
                'event_owner': client_event_owner
            }
            db_manager.record_operation(operation, session_state.get('is_practice', False))
        else:
            print("练习模式，跳过 target_selected 数据库记录。")

        self._physio_marker("target_selected", message, session_state, {
            "operation": "target_selected",
            "task_type": "RADAR_TARGETING",
            "target_id": target_id,
            "iff_mode": iff_mode,
            "is_enemy": is_enemy,
            "is_correct": (is_enemy and not iff_mode) or False,
        })
        
        return []
    
    async def _handle_threat_clicked(self, message: Dict[str, Any], session_state: Dict[str, Any], 
                                   client_event_owner: str) -> List[Dict[str, Any]]:
        """处理威胁点击消息"""
        print("消息类型: threat_clicked")

        task_id = self._get_current_task_id('SA_THREAT_RESPONSE')
        if not session_state.get('is_practice', False) and task_id:
            operation = {
                'task_id': task_id,
                'operationType': 'threat_clicked',
                'timestamp': message.get('timestamp', int(time.time() * 1000)),
                'isActive': True,
                'receive_timestamp': message.get('receive_timestamp'),
                'parameters': {
                    'threat_id': message.get('threat_id'),
                    'label': message.get('label'),
                    'priority': message.get('priority'),
                    'is_highest_priority': message.get('is_highest_priority'),
                    'is_correct': message.get('is_highest_priority', False),
                    'correct_answer': message.get('correct_answer'),
                    'extra': message.get('extra', {})
                },
                'user_id': message.get('user_id', ''),
                'event_owner': client_event_owner
            }
            db_manager.record_operation(operation, session_state.get('is_practice', False))
        else:
            print("练习模式，跳过 threat_clicked 数据库记录。")

        self._physio_marker("threat_clicked", message, session_state, {
            "operation": "threat_clicked",
            "task_type": "SA_THREAT_RESPONSE",
            "threat_id": message.get("threat_id"),
            "is_highest_priority": message.get("is_highest_priority"),
        })
        
        return []

    async def _handle_task_exit_request(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Notify external hosts, such as UE Web Engine containers, to close this task UI."""
        timestamp = message.get('timestamp', int(time.time() * 1000))
        return [{
            'type': 'task_exit_requested',
            'reason': message.get('reason', 'task_completed'),
            'task_type': message.get('task_type'),
            'task_id': message.get('task_id') or self._get_current_task_id(message.get('task_type') or ""),
            'user_id': message.get('user_id') or self.current_session.get('user_id', ''),
            'timestamp': timestamp,
        }]

    async def _handle_task_result_confirmed(self, message: Dict[str, Any], session_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """处理任务结果确认：传感器任务按 IFF，威胁排序按查看结果，才视为任务结束。"""
        task_type = message.get('task_type')
        current_task_id = self._get_current_task_id(task_type or "")
        message_task_id = message.get('task_id')
        if message_task_id is not None and current_task_id is not None and str(message_task_id) != str(current_task_id):
            self.logger.warning(
                "[REMOTE_TASK_COUNT] ignore stale task_result_confirmed task_type=%s "
                "user=%s message_task_id=%s current_task_id=%s timestamp=%s",
                task_type or "",
                message.get('user_id') or self.current_session.get('user_id', ''),
                message_task_id,
                current_task_id,
                message.get('timestamp'),
            )
            return []

        if message_task_id is None:
            started_at = self._get_task_started_at_ms(task_type or "")
            if started_at:
                try:
                    age_ms = int(time.time() * 1000) - int(started_at)
                except (TypeError, ValueError):
                    age_ms = None
                if age_ms is not None and age_ms < 1000:
                    self.logger.warning(
                        "[REMOTE_TASK_COUNT] ignore immediate task_result_confirmed without task_id "
                        "task_type=%s user=%s current_task_id=%s age_ms=%s timestamp=%s",
                        task_type or "",
                        message.get('user_id') or self.current_session.get('user_id', ''),
                        current_task_id,
                        age_ms,
                        message.get('timestamp'),
                    )
                    return []

        if task_type == 'RADAR_TARGETING':
            task_manager = session_state.get('task_manager')
        elif task_type == 'SA_THREAT_RESPONSE':
            task_manager = session_state.get('sa_task_manager')
        else:
            task_manager = None

        repetition_info = {}
        event_owner = ""
        user_id = message.get('user_id') or self.current_session.get('user_id', '')
        current_scenario = None
        if task_manager and task_manager.current_scenario:
            current_scenario = task_manager.current_scenario
            repetition_info = task_manager.current_scenario.get('repetition_info') or {}
            event_owner = 'AI' if task_manager.current_scenario.get('is_ai_active') else 'manual'
        else:
            current_scenario = self.current_session.get(f'{task_type}_scenario') if task_type else None
            if current_scenario:
                repetition_info = current_scenario.get('repetition_info') or {}
                event_owner = 'AI' if current_scenario.get('is_ai_active') else 'manual'

        self._log_task_count_notice(
            "结束",
            task_type or "",
            user_id,
            current_task_id,
            repetition_info,
            event_owner=event_owner,
        )
        if task_manager:
            task_manager.mark_task_completed()

        group_completed = False
        try:
            group_completed = (
                int(repetition_info.get("current") or 0) >=
                int(repetition_info.get("total") or 0) > 0
            )
        except (TypeError, ValueError):
            group_completed = False
        task_group_id = (
            (current_scenario or {}).get("task_group_id")
            or repetition_info.get("task_group_id")
        )

        task_id = current_task_id
        if not session_state.get('is_practice', False) and task_id:
            operation = {
                'task_id': task_id,
                'operationType': 'task_result_confirmed',
                'timestamp': message.get('timestamp', int(time.time() * 1000)),
                'isActive': True,
                'parameters': {
                    'task_type': task_type,
                    'extra': message.get('extra', {})
                },
                'user_id': message.get('user_id', ''),
                'event_owner': message.get('event_owner', 'manual')
            }
            db_manager.record_operation(operation, session_state.get('is_practice', False))
            try:
                completed_at_ms = int(message.get('timestamp') or time.time() * 1000)
                db_manager.update_task_run_progress(
                    task_id=int(task_id),
                    completed_subtasks=1,
                    status="completed",
                    completed_at_ms=completed_at_ms,
                    raw_message_json=json.dumps(message or {}, ensure_ascii=False),
                )
                if task_group_id is not None:
                    try:
                        completed_count = int(repetition_info.get("current") or 0)
                    except (TypeError, ValueError):
                        completed_count = None
                    db_manager.update_task_group_progress(
                        group_id=int(task_group_id),
                        completed_task_count=completed_count,
                        current_task_seq=completed_count,
                        status="completed" if group_completed else "active",
                        completed_at_ms=completed_at_ms if group_completed else None,
                        raw_message_json=json.dumps(message or {}, ensure_ascii=False),
                    )
                    task_group = db_manager.get_task_group(int(task_group_id))
                    if task_group:
                        expected_count = int(task_group.get("expected_task_count") or 0)
                        completed_count_from_db = int(task_group.get("completed_task_count") or 0)
                        group_completed = (
                            task_group.get("status") == "completed"
                            or expected_count > 0 and completed_count_from_db >= expected_count
                        )
                db_manager.record_task_event(
                    task_id=int(task_id),
                    task_type=task_type or "",
                    user_id=user_id,
                    event_type="task_result_confirmed",
                    timestamp_ms=completed_at_ms,
                    payload_json=json.dumps({
                        "event_owner": event_owner,
                        "repetition_info": repetition_info,
                    }, ensure_ascii=False),
                    raw_message_json=json.dumps(message or {}, ensure_ascii=False),
                )
            except Exception as e:
                self.logger.warning(
                    "complete unified task_run failed: task_id=%s task_type=%s error=%s",
                    task_id,
                    task_type,
                    e,
                    exc_info=True,
                )

        self._physio_stop_task(
            task_type or "",
            user_id,
            current_task_id,
            event_owner,
            repetition_info,
            message,
            session_state,
        )
        self._gaze_stop(current_task_id)
        if group_completed and task_type in ("RADAR_TARGETING", "SA_THREAT_RESPONSE"):
            return [{
                "type": "all_tasks_completed",
                "task_type": task_type,
                "task_id": current_task_id,
                "task_group_id": task_group_id,
                "repetition_info": repetition_info,
                "is_ai_active": bool(repetition_info.get("is_ai_active")),
                "is_practice": bool(repetition_info.get("is_practice")),
                "timestamp": int(time.time() * 1000),
            }]
        return []
    
    async def _handle_record_operation(self, message: Dict[str, Any], session_state: Dict[str, Any], 
                                     client_event_owner: str) -> List[Dict[str, Any]]:
        """处理记录操作消息"""
        print("消息类型: record_operation")
        operation = message.get('operation', {})
        if 'event_owner' not in operation:
            operation['event_owner'] = client_event_owner
        db_manager.record_operation(operation, session_state.get('is_practice', False))
        return []
    
    async def _handle_record_bulk_operations(self, message: Dict[str, Any], session_state: Dict[str, Any], 
                                           client_event_owner: str) -> List[Dict[str, Any]]:
        """处理批量记录操作消息"""
        print("消息类型: record_bulk_operations")
        operations = message.get('operations', [])
        for operation in operations:
            if 'event_owner' not in operation:
                operation['event_owner'] = client_event_owner
            db_manager.record_operation(operation, session_state.get('is_practice', False))
        return []
    
    async def _handle_sa_operations(self, message: Dict[str, Any], session_state: Dict[str, Any], 
                                  websocket) -> List[Dict[str, Any]]:
        """处理SA相关操作"""
        user_id = message.get('user_id')
        if not user_id:
            return [{"type": "error", "message": "Cannot switch SA without a user_id in the message."}]

        task_type = 'SA_THREAT_RESPONSE'
        is_practice = message.get('is_practice', False)
        session_state['is_practice'] = is_practice
        is_ai_active_request = bool(message.get('is_ai_active', False))
        progress_key = get_progress_key_for_task(user_id, task_type)
        # 为SA任务也创建一个持久化管理器
        task_manager = TaskScenarioManager(
            config_manager.get_config(),
            user_id,
            task_type,
            is_practice=is_practice,
            is_ai_active_request=is_ai_active_request,
            progress_key=progress_key,
        )
        repetition_override = self._extract_repetition_override(message)
        if repetition_override is not None:
            task_manager.max_repetitions = repetition_override
            task_manager.apply_repetition_override(repetition_override, overwrite=True)
        session_state['sa_task_manager'] = task_manager
        event_owner = message.get('event_owner') or ('AI' if is_ai_active_request else 'manual')

        overlay_source = "pending"
        overlay, platform_meta = consume_pending_for_task_start(user_id, task_type)
        if not overlay:
            overlay_source = "active"
            overlay, platform_meta = get_active_overlay_for_task(user_id, task_type)
        normalized_meta = (platform_meta or {}).get("normalized") or {}
        if overlay and task_manager.current_scenario:
            task_manager.apply_platform_overlay(overlay)
        
        current_scenario = task_manager.get_next_task_parameters(is_ai_active_request)
        self.logger.info(
            "[REMOTE_TASK_COUNT] sa get_next returned user=%s progress=%s "
            "scenario=%s rep_info=%s",
            user_id,
            progress_key,
            bool(current_scenario),
            (current_scenario or {}).get('repetition_info') if isinstance(current_scenario, dict) else current_scenario,
        )

        if current_scenario == "ALL_COMPLETED":
            return [{
                "type": "all_tasks_completed",
                "task_type": task_type,
                "message": "所有威胁排序任务已完成。",
                "is_ai_active": bool(is_ai_active_request),
                "is_practice": bool(is_practice),
            }]
        if not current_scenario:
            return [{
                "type": "all_tasks_completed",
                "task_type": task_type,
                "message": f"当前模式的{task_type}任务已完成。",
                "is_ai_active": bool(is_ai_active_request),
                "is_practice": bool(is_practice),
            }]

        # 与 _handle_task_start 保持一致：消费外部平台 task_start 留下的 overlay，
        # 把 difficulty/AI/audio 以及 TaskNumber→max_repetitions 灌到 scenario 上。
        self.logger.info(
            "[REMOTE_TASK_COUNT] sa overlay resolved user=%s task_type=%s progress=%s "
            "source=%s has_overlay=%s id=%s raw_TaskNumber=%s rep_override=%s "
            "scenario_rep_before=%s",
            user_id,
            task_type,
            progress_key,
            overlay_source,
            bool(overlay),
            normalized_meta.get("platform_task_id"),
            normalized_meta.get("task_number"),
            normalized_meta.get("repetition_total_override"),
            current_scenario.get('repetition_info') if isinstance(current_scenario, dict) else current_scenario,
        )
        if overlay:
            task_manager.apply_platform_overlay(overlay)
            current_scenario = task_manager.current_scenario
            event_owner = 'AI' if current_scenario['is_ai_active'] else 'manual'
            self.logger.info(
                "[REMOTE_TASK_COUNT] sa overlay applied user=%s task_type=%s progress=%s "
                "event_owner=%s rep_info=%s override=%s",
                user_id,
                task_type,
                progress_key,
                event_owner,
                current_scenario.get('repetition_info'),
                current_scenario.get('max_repetitions_override'),
            )
        if repetition_override is not None:
            task_manager.apply_repetition_override(repetition_override, overwrite=True)
            current_scenario = task_manager.current_scenario

        trust_state = self._get_task_trust_state(task_type)
        existing_task_id = db_manager.find_existing_task_setting_id(
            current_scenario,
            user_id,
            event_owner,
            task_type,
            trust_state,
        )
        is_retrying_incomplete_task = bool(
            existing_task_id and
            current_scenario.get('repetition_info', {}).get('previous_task_completed') is False
        )
        if is_retrying_incomplete_task:
            db_manager.clear_task_operations(existing_task_id)
        task_started_at_ms = int(time.time() * 1000)
        task_group_id, task_seq = self._ensure_current_task_group(
            task_manager,
            task_type,
            user_id,
            current_scenario,
            event_owner,
            trust_state,
            message,
            task_started_at_ms,
            progress_key,
            platform_meta=platform_meta,
            force_new_group=overlay_source == "pending" and bool(platform_meta),
        )
        task_id = existing_task_id or generate_task_id()
        self._set_current_task(task_type, task_id, task_started_at_ms)
        self.current_session[f'{task_type}_scenario'] = current_scenario
        self._ensure_unified_task_run(
            task_id,
            task_type,
            user_id,
            current_scenario,
            event_owner,
            trust_state,
            message,
            task_started_at_ms,
            platform_meta=platform_meta,
            group_id=task_group_id,
            task_seq=task_seq,
            reactivate=is_retrying_incomplete_task,
        )

        # 启动眼动追踪
        self._gaze_start(task_id, user_id=user_id, task_name=task_type, task_source=event_owner)
        self._physio_start_task(task_type, user_id, task_id, event_owner, current_scenario, session_state)

        # 记录操作
        should_record_task_start = (not existing_task_id) or is_retrying_incomplete_task
        if not session_state.get('is_practice', False) and should_record_task_start:
            operation = {
                'task_id': task_id,
                'operationType': message.get('type'),
                'timestamp': message.get('timestamp', int(time.time() * 1000)),
                'isActive': True,
                'parameters': {},
                'user_id': user_id,
                'event_owner': event_owner
            }
            db_manager.record_operation(operation, session_state.get('is_practice', False))
        db_manager.record_task_settings(
            task_id,
            current_scenario,
            user_id,
            event_owner,
            session_state.get('is_practice', False),
            task_type,
            trust_state,
        )
        if self.use_enhanced_protocol:
            # 使用增强协议生成完整威胁数据
            print("[MessageHandler] 使用增强协议生成威胁")
            
            # 创建雷达配置（基于SAPage.tsx的正确配置：width=800, height=600）
            radar_config = RadarConfig(
                center_x=400.0,       # width / 2 = 800 / 2
                center_y=360.0,       # height * 0.6 = 600 * 0.6  
                radius1=100.0,
                radius2=180.0,        # 底部线位置 - center_y = 540 - 360 = 180
                radius3=306.0,        # radius2 * 1.7 = 180 * 1.7
                canvas_width=800.0,
                canvas_height=600.0
            )
            
            # 生成增强威胁数据
            threat_result = threat_manager.generate_enhanced_sa_threats(
                current_scenario['difficulty_config'],
                radar_config
            )
            
            # 创建增强威胁消息
            enhanced_response = message_protocol.create_enhanced_threats_message(
                threat_result=threat_result,
                task_id=task_id,
                task_type=task_type,
                repetition_info=current_scenario['repetition_info'],
                is_ai_active=current_scenario['is_ai_active'],
                ai_level=current_scenario.get('ai_level_name'),
                ai_configs=config_manager.get_ai_levels(),
                audio_enabled=current_scenario['audio_enabled'],
                trust_calibration=config_manager.get_trust_calibration_config()
            )
            
            if websocket:
                # 设置当前任务ID到会话状态，供威胁管理器使用
                session_state['current_task_id'] = self._get_current_task_id(task_type)
                # 使用增强协议发送紧急事件
                asyncio.create_task(
                    threat_manager.auto_send_enhanced_sa_emergency(
                        websocket,
                        threat_result.threats,
                        radar_config,
                        user_id,
                        event_owner,
                        session_state,
                        use_enhanced_protocol=True
                    )
                )
            
            # 只返回增强消息，避免协议冲突
            print("[MessageHandler] 发送增强协议消息，威胁数量:", len(threat_result.threats))
            print("[MessageHandler] 增强消息类型:", enhanced_response.get('type'))
            print("[MessageHandler] 增强消息包含字段:", list(enhanced_response.keys()))
            print("[MessageHandler] 威胁详情:", [{'id': t.id, 'type': t.type, 'position': t.position.to_dict()} for t in threat_result.threats])
            self._log_task_count_notice(
                "开始",
                task_type,
                user_id,
                task_id,
                enhanced_response.get("repetition_info"),
                event_owner=event_owner,
                platform_id=normalized_meta.get("platform_task_id"),
            )
            self.logger.info(
                "[REMOTE_TASK_COUNT] sa enhanced_response user=%s task_id=%s progress=%s "
                "event_owner=%s rep_info=%s platform_id=%s",
                user_id,
                task_id,
                progress_key,
                event_owner,
                enhanced_response.get("repetition_info"),
                normalized_meta.get("platform_task_id"),
            )
            return [enhanced_response]
        else:
            # 使用传统协议
            print("[MessageHandler] 使用传统协议生成威胁")
            threats = threat_manager.generate_sa_threats(current_scenario['difficulty_config'])
            
            response = {
                'type': 'sa_task_updated',
                'task_id': task_id,
                'saThreats': threats,
                'repetition_info': current_scenario['repetition_info'],
                'task_type': task_type,
                'is_ai_active': current_scenario['is_ai_active'],
                'ai_level': current_scenario.get('ai_level_name'),
                'ai_configs': config_manager.get_ai_levels(),
                'audio_enabled': current_scenario['audio_enabled'],
                'trust_calibration': config_manager.get_trust_calibration_config()
            }

            if websocket:
                # 设置当前任务ID到会话状态，供威胁管理器使用
                session_state['current_task_id'] = self._get_current_task_id(task_type)
                asyncio.create_task(
                    threat_manager.auto_send_sa_emergency(
                        websocket,
                        threats,
                        user_id,
                        event_owner,
                        session_state
                    )
                )
            self._log_task_count_notice(
                "开始",
                task_type,
                user_id,
                task_id,
                response.get("repetition_info"),
                event_owner=event_owner,
                platform_id=normalized_meta.get("platform_task_id"),
            )
            self.logger.info(
                "[REMOTE_TASK_COUNT] sa legacy_response user=%s task_id=%s progress=%s "
                "event_owner=%s rep_info=%s platform_id=%s",
                user_id,
                task_id,
                progress_key,
                event_owner,
                response.get("repetition_info"),
                normalized_meta.get("platform_task_id"),
            )
            return [response]
    
    async def _handle_joystick_message(self, message: Dict[str, Any], session_state: Dict[str, Any], 
                                     websocket=None) -> List[Dict[str, Any]]:
        """处理操纵杆相关消息（备用处理器）"""
        print(f"消息类型: {message.get('type', 'unknown_joystick')}")
        
        # 这是一个备用处理器，主要处理应该由WebSocket服务器的joystick_handler处理的消息
        # 如果消息到达这里，说明joystick_handler可能未正确设置
        
        message_type = message.get('type', '')
        user_id = message.get('user_id', '')
        
        # 记录操纵杆相关操作到数据库
        if not session_state.get('is_practice', False):
            operation = {
                'task_id': self._get_current_task_id(message.get('task_type') or 'RADAR_TARGETING'),
                'operationType': message_type,
                'timestamp': message.get('timestamp', int(time.time() * 1000)),
                'isActive': True,
                'parameters': {
                    'joystick_data': message.get('data', {}),
                    'device_status': message.get('device_status', 'unknown')
                },
                'user_id': user_id,
                'event_owner': message.get('event_owner', 'manual')
            }
            db_manager.record_operation(operation, session_state.get('is_practice', False))
        else:
            print(f"练习模式，跳过 {message_type} 数据库记录。")
        
        # 根据消息类型返回适当的响应
        if message_type == 'joystick_connect':
            return [{
                'type': 'joystick_connect_response',
                'success': False,
                'message': '操纵杆连接请求已接收，但应由专用处理器处理'
            }]
        elif message_type == 'joystick_disconnect':
            return [{
                'type': 'joystick_disconnect_response',
                'success': False,
                'message': '操纵杆断开请求已接收，但应由专用处理器处理'
            }]
        elif message_type == 'joystick_data':
            # 操纵杆数据消息，通常用于广播，不需要响应
            return []
        else:
            return [{
                'type': 'joystick_message_response',
                'success': False,
                'message': f'操纵杆消息 {message_type} 已接收，但应由专用处理器处理'
            }]
    
    # async def _handle_reset_targets(self, message: Dict[str, Any], session_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    #     """处理重置目标消息"""
    #     print("消息类型: reset_targets ( advancing scenario counter )")
        
    #     user_id = self.current_session.get('user_id', '')
    #     if not user_id:
    #         return [{"type": "error", "message": "Cannot reset_targets without a user session."}]

    #     task_manager = session_state.get('task_manager')
    #     if not task_manager:
    #         return [{"type": "error", "message": "Task not started. Cannot reset targets."}]

    #     is_ai_active_request = self.current_session.get('RADAR_TARGETING_scenario', {}).get('is_ai_active', False)
    #     event_owner = 'AI' if is_ai_active_request else 'manual'

    #     current_scenario = task_manager.get_next_task_parameters(is_ai_active_request)
    #     if not current_scenario:
    #         return [{"type": "all_tasks_completed", "task_type": "RADAR_TARGETING", "message": "Congratulations! All Radar Targeting scenarios have been completed."}]

    #     self.current_session['RADAR_TARGETING_scenario'] = current_scenario
    #     task_id = generate_task_id()
    #     self.current_session['task_id'] = task_id
        
    #     db_manager.record_task_settings(task_id, current_scenario, user_id, event_owner, session_state.get('is_practice', False))

    #     # 根据新场景重新初始化目标
    #     target_manager.initialize_targets(current_scenario['difficulty_config'])
        
    #     # 构造一个init_settings消息，以便前端可以更新其状态（包括计数器）
    #     response_message = {
    #         "type": "init_settings",
    #         "task_id": task_id,
    #         "timestamp": time.time() * 1000,
    #         "settings": {"range": 80, "scanAngle": 30},
    #         "is_ai_active": current_scenario['is_ai_active'],
    #         "ai_level": current_scenario['ai_level_name'],
    #         "ai_configs": config_manager.get_ai_levels(),
    #         "audio_enabled": current_scenario['audio_enabled'],
    #         "repetition_info": current_scenario['repetition_info'],
    #         "task_type": "RADAR_TARGETING"
    #     }
    #     return [response_message]
    
    def _generate_antenna_adjustment(self) -> Dict[str, Any]:
        """生成随机天线高度指令"""
        task_id = self._get_current_task_id('RADAR_TARGETING')
        existing_target = self.current_session.get('target_elevation')
        if self.current_session.get('stage') == 'antenna_adjustment' and existing_target is not None:
            return {
                "type": "adjust_antenna",
                "task_id": task_id,
                "targetElevation": existing_target,
                "message": f"请将天线高度{'上移' if existing_target > 0 else '下移'} {abs(existing_target)}格"
            }

        # 从-3,-2,-1,1,2,3中随机选择一个调整值
        direction = random.choice([-3, -2, -1, 1, 2, 3])
        target_elevation = direction
        
        # 更新当前会话状态
        self.current_session['target_elevation'] = target_elevation
        self.current_session['stage'] = 'antenna_adjustment'
        
        return {
            "type": "adjust_antenna",
            "task_id": task_id,
            "targetElevation": target_elevation,
            "message": f"请将天线高度{'上移' if direction > 0 else '下移'} {abs(target_elevation)}格"
        }
    
    def _handle_antenna_adjustment(self, message: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """处理天线高度调整确认"""
        try:
            client_elevation = message.get('elevation')
            client_target_elevation = message.get('targetElevation')
            message_task_id = message.get('task_id')
            current_task_id = self._get_current_task_id('RADAR_TARGETING')
            if (
                message_task_id is not None
                and current_task_id is not None
                and str(message_task_id) != str(current_task_id)
            ):
                self.logger.info(
                    "ignore stale antenna_adjusted message_task_id=%s current_task_id=%s",
                    message_task_id,
                    current_task_id,
                )
                return {
                    "type": "settings_validation",
                    "status": "ignored",
                    "message": "Ignored stale antenna adjustment confirmation.",
                }, False
            
            # 检查是否在预期范围内（允许±0.1°的误差）
            target_elevation = self.current_session.get('target_elevation')
            if target_elevation is None:
                if client_target_elevation is not None:
                    target_elevation = client_target_elevation
                    self.current_session['target_elevation'] = target_elevation
                    self.current_session['stage'] = 'antenna_adjustment'
                    self.logger.warning(
                        "recovered missing antenna target from current task confirmation task_id=%s target=%s",
                        current_task_id,
                        target_elevation,
                    )
                else:
                    self.logger.info(
                        "ignore antenna_adjusted without a pending target task_id=%s",
                        message_task_id or current_task_id,
                    )
                    return {
                        "type": "settings_validation",
                        "status": "ignored",
                        "message": "Ignored antenna adjustment confirmation without a pending target.",
                    }, False

            if client_target_elevation is not None and abs(client_target_elevation - target_elevation) > 0.1:
                return {
                    "type": "settings_validation",
                    "status": "error",
                    "message": f"天线目标高度已更新，请按最新提示调整。当前提示目标为{client_target_elevation}°，服务端目标为{target_elevation}°"
                }, False
            
            if abs(client_elevation - target_elevation) <= 0.1:
                # 高度设置正确
                self.current_session['stage'] = 'target_identification'
                print('【调试】天线高度设置正确，开始发送目标数据')
                return {
                    "type": "settings_validation",
                    "status": "success",
                    "message": "天线高度设置正确，开始发送目标数据"
                }, True
            else:
                # 高度设置不正确
                return {
                    "type": "settings_validation",
                    "status": "error",
                    "message": f"天线高度设置不正确，目标为{target_elevation}°，当前为{client_elevation}°"
                }, False
        except Exception as e:
            print(f"天线调整出错: {e}")
            return {"type": "ERROR", "message": f"处理天线调整时出错: {e}"}, False

# 全局消息处理器实例
message_handler = MessageHandler() 
