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
    _normalize_control_mode,
    peek_pending_include_ai,
    consume_pending_for_task_start,
    get_active_overlay_for_task,
    get_progress_key_for_task,
)
from models.threat_models import RadarConfig
from network.message_protocol import message_protocol
from services.ai_accuracy import (
    AIAccuracyConfigError,
    SELECTION_PROTOCOL_VERSION,
    bind_task_decision_selection,
    build_group_accuracy,
    build_task_decision,
    group_accuracy_from_row,
)

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

    def _prepare_ai_accuracy(
        self,
        session_state: Dict[str, Any],
        *,
        current_scenario: Dict[str, Any],
        user_id: str,
        task_type: str,
        task_group_id: Optional[int],
        task_id: int,
        task_seq: Optional[int],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Create or reload the group sample, then derive this task's decision."""
        if not current_scenario.get("is_ai_active"):
            return None, None
        if task_group_id is None:
            raise AIAccuracyConfigError("AI task is missing task_group_id")
        ai_level = str(current_scenario.get("ai_level_name") or "").strip()
        difficulty = str(current_scenario.get("difficulty_name") or "").strip().lower()
        group_accuracy = None
        if session_state.get("is_practice", False):
            practice_contexts = session_state.setdefault("practice_ai_accuracy_contexts", {})
            group_accuracy = practice_contexts.get(str(task_group_id))
            if group_accuracy is None:
                group_accuracy = build_group_accuracy(
                    config_manager.get_config(),
                    user_id=user_id,
                    task_type=task_type,
                    task_group_id=int(task_group_id),
                    ai_level=ai_level,
                    difficulty=difficulty,
                )
                practice_contexts[str(task_group_id)] = group_accuracy
        else:
            group = db_manager.get_task_group(int(task_group_id))
            group_accuracy = group_accuracy_from_row(group or {})
        if group_accuracy is None:
            proposed = build_group_accuracy(
                config_manager.get_config(),
                user_id=user_id,
                task_type=task_type,
                task_group_id=int(task_group_id),
                ai_level=ai_level,
                difficulty=difficulty,
            )
            group = db_manager.save_task_group_ai_accuracy(int(task_group_id), proposed)
            group_accuracy = group_accuracy_from_row(group)
        if group_accuracy is None:
            raise AIAccuracyConfigError("persisted AI accuracy context is incomplete")
        normalized_task_seq = int(task_seq or 1)
        decision = build_task_decision(
            group_accuracy,
            task_id=int(task_id),
            task_seq=normalized_task_seq,
            task_type=task_type,
        )
        contexts = session_state.setdefault("ai_decision_contexts", {})
        contexts[str(task_id)] = {
            "ai_accuracy": group_accuracy,
            "ai_decision": decision,
            "task_type": task_type,
        }
        return group_accuracy, decision

    def _get_ai_decision_context(
        self, session_state: Dict[str, Any], task_id: Any, task_type: str
    ) -> Optional[Dict[str, Any]]:
        context = (session_state.get("ai_decision_contexts") or {}).get(str(task_id))
        if isinstance(context, dict) and context.get("task_type") == task_type:
            return context
        return None

    def _bind_ai_decision_selection(
        self,
        session_state: Dict[str, Any],
        task_id: Any,
        task_type: str,
        *,
        correct_pool: List[Any],
        incorrect_pool: List[Any],
        correct_pool_empty_reason: str,
        incorrect_pool_empty_reason: str,
    ) -> Optional[Dict[str, Any]]:
        context = self._get_ai_decision_context(session_state, task_id, task_type)
        if not context:
            return None
        bound = bind_task_decision_selection(
            context.get("ai_decision") or {},
            correct_pool=correct_pool,
            incorrect_pool=incorrect_pool,
            correct_pool_empty_reason=correct_pool_empty_reason,
            incorrect_pool_empty_reason=incorrect_pool_empty_reason,
        )
        context["ai_decision"] = bound
        return bound

    @staticmethod
    def _validate_ai_selection_submission(
        decision_context: Dict[str, Any],
        message: Dict[str, Any],
        selected_id: Any,
    ) -> Optional[Tuple[str, str, Optional[str]]]:
        decision = decision_context.get("ai_decision") or {}
        expected_id = decision.get("expected_target_id")
        expected_text = str(expected_id) if expected_id is not None else None
        if not expected_text:
            return (
                "ai_decision_target_unavailable",
                "The server has no authoritative target for this task.",
                None,
            )
        outcome = message.get("ai_decision_outcome")
        if not isinstance(outcome, dict) or outcome.get("selection_protocol") != SELECTION_PROTOCOL_VERSION:
            return (
                "ai_decision_protocol_mismatch",
                "The frontend AI-selection protocol is missing or outdated. Refresh the task page.",
                expected_text,
            )
        if str(outcome.get("expected_target_id")) != expected_text:
            return (
                "ai_decision_protocol_mismatch",
                "The frontend AI decision does not match the current server decision.",
                expected_text,
            )
        if str(selected_id) != expected_text:
            return (
                "ai_decision_target_mismatch",
                "The submitted AI target does not match the authoritative server target.",
                expected_text,
            )
        return None

    def _build_ai_decision_audit(
        self,
        context: Optional[Dict[str, Any]],
        message: Dict[str, Any],
        *,
        selected_id: Any,
        is_correct: bool,
        selected_pool: Optional[List[Any]] = None,
        fallback_reason: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if not context:
            return None
        group = dict(context.get("ai_accuracy") or {})
        decision = dict(context.get("ai_decision") or {})
        outcome = message.get("ai_decision_outcome")
        if not isinstance(outcome, dict):
            outcome = {}
        use_client_outcome = selected_pool is None
        if use_client_outcome:
            selected_pool = outcome.get("selected_pool")
        if not isinstance(selected_pool, list):
            selected_pool = []
        selected_pool = [str(item) for item in selected_pool if item is not None]
        if fallback_reason is None and use_client_outcome:
            fallback_reason = outcome.get("fallback_reason")
        audit = {
            **group,
            **decision,
            "selected_pool": selected_pool,
            "fallback_reason": str(fallback_reason) if fallback_reason else None,
            "actual_selection": str(selected_id) if selected_id is not None else None,
            "is_correct": bool(is_correct),
        }
        return audit

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

        platform_overall_task_id = (
            (platform_meta or {}).get("normalized", {}).get("overall_task_id")
            if isinstance((platform_meta or {}).get("normalized"), dict)
            else None
        )
        task_group_id = (
            platform_overall_task_id
            or current_scenario.get("task_group_id")
            or repetition_info.get("task_group_id")
        )
        difficulty = current_scenario.get("external_difficulty_display") or current_scenario.get("difficulty_name")
        autonomy_level = current_scenario.get("autonomy_level") or current_scenario.get("ai_level_name")
        if platform_overall_task_id:
            current_scenario["task_group_id"] = task_group_id
            repetition_info["task_group_id"] = task_group_id
            current_scenario["repetition_info"] = repetition_info
        if not task_group_id:
            try:
                active_group = db_manager.find_active_task_group(
                    user_id=user_id or "",
                    task_type=task_type,
                    progress_key=progress_key,
                    difficulty=difficulty,
                    autonomy_level=autonomy_level,
                )
                task_group_id = active_group.get("group_id") if active_group else None
            except Exception as e:
                self.logger.warning(
                    "find active task_group failed: task_type=%s user=%s error=%s",
                    task_type, user_id, e,
                    exc_info=True,
                )
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
                difficulty=difficulty,
                autonomy_level=autonomy_level,
                control_mode=current_scenario.get("control_mode"),
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

    @staticmethod
    def _set_control_mode_session(
        session_state: Dict[str, Any],
        message: Dict[str, Any],
        normalized_meta: Dict[str, Any],
    ) -> Tuple[str, bool]:
        raw_mode = normalized_meta.get('control_mode')
        if raw_mode is None:
            raw_mode = normalized_meta.get('default_control_mode')
        if raw_mode is None:
            raw_mode = message.get('control_mode')
        if raw_mode is None:
            raw_mode = '2' if message.get('manual_control_disabled') else ('1' if message.get('include_ai') or message.get('is_ai_active') else '0')
        control_mode = _normalize_control_mode(raw_mode)
        manual_control_disabled = control_mode == '2'
        session_state['control_mode'] = control_mode
        session_state['manual_control_disabled'] = manual_control_disabled
        return control_mode, manual_control_disabled

    @staticmethod
    def _apply_control_mode_to_scenario(
        current_scenario: Dict[str, Any],
        control_mode: str,
        manual_control_disabled: bool,
    ) -> None:
        current_scenario['control_mode'] = control_mode
        current_scenario['manual_control_disabled'] = manual_control_disabled
        repetition_info = current_scenario.get('repetition_info') or {}
        repetition_info['control_mode'] = control_mode
        repetition_info['manual_control_disabled'] = manual_control_disabled
        current_scenario['repetition_info'] = repetition_info

    @staticmethod
    def _manual_operation_rejection(
        message_type: str,
        client_event_owner: str,
        session_state: Dict[str, Any],
    ) -> Optional[List[Dict[str, Any]]]:
        controlled_messages = {
            'settings_update', 'antenna_adjusted', 'target_selected', 'threat_clicked',
            'record_operation', 'record_bulk_operations', 'ResetSA',
            'user_take_control',
        }
        if not session_state.get('manual_control_disabled') or message_type not in controlled_messages:
            return None
        if message_type == 'ResetSA' and str(client_event_owner or '').strip().lower() == 'confirmation':
            return None
        if str(client_event_owner or '').strip().lower() == 'ai':
            return None
        return [{
            'type': 'operation_rejected',
            'status': 'forbidden',
            'reason': 'pure_ai_mode',
            'operation_type': message_type,
            'message': 'Manual operation is disabled while DefaultControlMode is 2.',
        }]
    
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

            rejection = self._manual_operation_rejection(message_type, client_event_owner, session_state)
            if rejection is not None:
                self.logger.warning('Rejected manual operation in pure AI mode: type=%s', message_type)
                return rejection

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
        control_mode, manual_control_disabled = self._set_control_mode_session(session_state, message, normalized_meta)
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
                "entry_completed": True,
                "message": "所有传感器任务已完成。",
                "is_ai_active": bool(is_ai_active_request),
                "is_practice": bool(is_practice),
            }]
        if not current_scenario:
            return [{
                "type": "all_tasks_completed",
                "task_type": task_type,
                "entry_completed": True,
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
        self._apply_control_mode_to_scenario(current_scenario, control_mode, manual_control_disabled)
        
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
        try:
            ai_accuracy, ai_decision = self._prepare_ai_accuracy(
                session_state,
                current_scenario=current_scenario,
                user_id=user_id,
                task_type=task_type,
                task_group_id=task_group_id,
                task_id=task_id,
                task_seq=task_seq,
            )
        except AIAccuracyConfigError as exc:
            self.logger.error("Invalid AI accuracy configuration: %s", exc)
            return [{
                "type": "ai_accuracy_config_invalid",
                "task_type": task_type,
                "task_group_id": task_group_id,
                "message": str(exc),
                "timestamp": int(time.time() * 1000),
            }]
        self._set_current_task(task_type, task_id, task_started_at_ms)
        session_state['radar_ai_selection'] = None
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
        if ai_decision:
            radar_targets = target_manager.get_targets()
            ai_decision = self._bind_ai_decision_selection(
                session_state,
                task_id,
                task_type,
                correct_pool=[
                    target.get('id') for target in radar_targets
                    if target.get('type') == 'army'
                ],
                incorrect_pool=[
                    target.get('id') for target in radar_targets
                    if target.get('type') != 'army'
                ],
                correct_pool_empty_reason='enemy_pool_empty',
                incorrect_pool_empty_reason='friendly_pool_empty',
            )

        # 启动眼动追踪（有 Tobii 时生效，否则静默跳过）
        self._gaze_start(task_id, user_id=user_id, task_name=task_type, task_source=event_owner)
        self._physio_start_task(task_type, user_id, task_id, event_owner, current_scenario, session_state)

        init_response = {
            "type": "init_settings",
            "task_id": task_id,
            "timestamp": time.time() * 1000,
            "settings": {"range": 80, "scanAngle": 30},
            "is_ai_active": current_scenario['is_ai_active'],
            "control_mode": control_mode,
            "manual_control_disabled": manual_control_disabled,
            "ai_level": current_scenario.get('ai_level_name'),
            "ai_configs": config_manager.get_ai_levels(),
            "audio_enabled": current_scenario['audio_enabled'],
            "trust_calibration": config_manager.get_trust_calibration_config(),
            "repetition_info": current_scenario['repetition_info'],
            "task_type": task_type
        }
        if ai_accuracy and ai_decision:
            init_response["ai_accuracy"] = ai_accuracy
            init_response["ai_decision"] = ai_decision
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

        current_task_id = self._get_current_task_id('RADAR_TARGETING')
        message_task_id = message.get('task_id')
        if (
            message_task_id is not None
            and current_task_id is not None
            and str(message_task_id) != str(current_task_id)
        ):
            self.logger.info(
                "ignore stale settings_update message_task_id=%s current_task_id=%s",
                message_task_id,
                current_task_id,
            )
            return [{
                "type": "settings_validation",
                "status": "ignored",
                "task_id": message_task_id,
                "message": "Ignored stale radar settings update.",
            }]
        
        # 验证雷达参数是否与init_settings一致
        client_range = message.get('range')
        client_scan_angle = message.get('scanAngle')
        required_range = 80
        required_scan_angle = 30

        if client_range == required_range and client_scan_angle == required_scan_angle:
            # 参数正确，进入天线调整阶段
            print("雷达参数验证成功，发送天线调整指令。")
            
            task_id = current_task_id
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

            validation_response = {
                "type": "settings_validation",
                "status": "success",
                "task_id": current_task_id,
                "message": "雷达参数设置正确，请继续进行天线高度调整",
            }
            antenna_command = self._generate_antenna_adjustment()
            return [validation_response, antenna_command]
        else:
            # 参数不正确
            print(f"雷达参数验证失败。需要: range={required_range}, scanAngle={required_scan_angle}。收到: range={client_range}, scanAngle={client_scan_angle}")
            validation_response = {
                "type": "settings_validation",
                "status": "error",
                "task_id": current_task_id,
                "message": "雷达参数设置不正确，请调整参数",
            }
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
        if message.get('action', 'select') == 'reset' or not target_id:
            return []
        task_id = self._get_current_task_id('RADAR_TARGETING')
        message_task_id = message.get('task_id')
        response_timestamp = int(time.time() * 1000)

        def failed(
            reason: str,
            detail: str = '',
            expected_target_id: Optional[str] = None,
        ) -> List[Dict[str, Any]]:
            response = {
                'type': 'target_selected_record_failed',
                'task_id': message_task_id if message_task_id is not None else task_id,
                'target_id': target_id,
                'reason': reason,
                'message': detail,
                'timestamp': response_timestamp,
            }
            if expected_target_id is not None:
                response['expected_target_id'] = expected_target_id
            return [response]

        if not task_id:
            return failed('missing_active_task', 'No active radar task is available.')
        if message_task_id is not None and str(message_task_id) != str(task_id):
            return failed('stale_task', 'The target selection belongs to another radar task.')

        targets = target_manager.get_targets()
        selected_target = next((target for target in targets if target.get('id') == target_id), None)
        if not selected_target:
            return failed('invalid_target', 'The selected target is not part of the current radar task.')
        is_enemy = selected_target.get('type') == 'army'
        is_ai_selection = str(client_event_owner or '').strip().lower() == 'ai'
        decision_context = self._get_ai_decision_context(session_state, task_id, 'RADAR_TARGETING')
        if is_ai_selection and not decision_context:
            return failed('missing_ai_decision_context', 'The server has no AI decision for this task.')
        if is_ai_selection:
            validation_error = self._validate_ai_selection_submission(
                decision_context,
                message,
                target_id,
            )
            if validation_error:
                return failed(*validation_error)
        audit_pool = []
        audit_fallback_reason = None
        if decision_context:
            decision = decision_context.get('ai_decision') or {}
            audit_pool = list(decision.get('selected_pool') or [])
            audit_fallback_reason = decision.get('fallback_reason')

        existing_selection = session_state.get('radar_ai_selection')
        if is_ai_selection and isinstance(existing_selection, dict) and str(existing_selection.get('task_id')) == str(task_id):
            if existing_selection.get('target_id') != target_id:
                return failed('selection_conflict', 'Another AI target has already been recorded for this task.')
            return [{
                'type': 'target_selected_recorded',
                'task_id': task_id,
                'target_id': target_id,
                'persisted': bool(existing_selection.get('persisted')),
                'duplicate': True,
                'timestamp': response_timestamp,
            }]

        persisted = not session_state.get('is_practice', False)
        is_correct = bool(is_enemy and not iff_mode)
        parameters = {
            'target_id': target_id,
            'action': message.get('action', 'select'),
            'iff_mode': iff_mode,
            'is_enemy': is_enemy,
            'is_correct': is_correct,
            'extra': message.get('extra', {})
        }
        ai_decision_audit = self._build_ai_decision_audit(
            decision_context,
            message,
            selected_id=target_id,
            is_correct=is_correct,
            selected_pool=audit_pool,
            fallback_reason=audit_fallback_reason,
        ) if is_ai_selection else None
        if ai_decision_audit:
            parameters['ai_decision'] = ai_decision_audit
        operation = {
            'task_id': task_id,
            'operationType': 'target_selected',
            'timestamp': message.get('timestamp', response_timestamp),
            'receive_timestamp': message.get('receive_timestamp'),
            'isActive': not iff_mode,
            'parameters': parameters,
            'user_id': message.get('user_id') or self.current_session.get('user_id', ''),
            'event_owner': client_event_owner
        }
        try:
            db_manager.record_operation(
                operation,
                session_state.get('is_practice', False),
                wait_for_commit=persisted,
            )
        except Exception as exc:
            self.logger.error(
                'Failed to persist target_selected: task_id=%s target_id=%s error=%s',
                task_id,
                target_id,
                exc,
                exc_info=True,
            )
            return failed('database_write_failed', str(exc))

        if is_ai_selection:
            session_state['radar_ai_selection'] = {
                'task_id': task_id,
                'target_id': target_id,
                'event_owner': 'AI',
                'persisted': persisted,
                'timestamp': operation['timestamp'],
            }

        self._physio_marker("target_selected", message, session_state, {
            "operation": "target_selected",
            "task_type": "RADAR_TARGETING",
            "target_id": target_id,
            "iff_mode": iff_mode,
            "is_enemy": is_enemy,
            "is_correct": is_correct,
        })
        
        if is_ai_selection:
            return [{
                'type': 'target_selected_recorded',
                'task_id': task_id,
                'target_id': target_id,
                'persisted': persisted,
                'duplicate': False,
                'timestamp': response_timestamp,
            }]
        return []
    
    async def _handle_threat_clicked(self, message: Dict[str, Any], session_state: Dict[str, Any],
                                   client_event_owner: str) -> List[Dict[str, Any]]:
        """Record an SA selection with server-owned truth and AI audit context."""
        task_id = self._get_current_task_id('SA_THREAT_RESPONSE')
        threat_id = message.get('threat_id')
        message_task_id = message.get('task_id')
        is_ai_selection = str(client_event_owner or '').strip().lower() == 'ai'
        response_timestamp = int(time.time() * 1000)

        def failed(
            reason: str,
            detail: str = '',
            expected_target_id: Optional[str] = None,
        ) -> List[Dict[str, Any]]:
            response = {
                'type': 'threat_clicked_record_failed',
                'task_id': message_task_id if message_task_id is not None else task_id,
                'threat_id': threat_id,
                'reason': reason,
                'message': detail,
                'timestamp': response_timestamp,
            }
            if expected_target_id is not None:
                response['expected_target_id'] = expected_target_id
            return [response]

        if not task_id or not threat_id:
            return failed('missing_active_task_or_threat') if is_ai_selection else []
        if message_task_id is not None and str(message_task_id) != str(task_id):
            return failed('stale_task', 'The selection belongs to another SA task.')
        truth = session_state.get('sa_threat_truth') or {}
        valid_ids = truth.get('threat_ids') or []
        if valid_ids and threat_id not in valid_ids:
            return failed('invalid_threat', 'The selected threat is not part of the current SA task.')
        highest_id = truth.get('highest_priority_threat_id')
        is_correct = (
            str(threat_id) == str(highest_id)
            if highest_id is not None
            else bool(message.get('is_highest_priority', False))
        )
        decision_context = self._get_ai_decision_context(session_state, task_id, 'SA_THREAT_RESPONSE')
        if is_ai_selection and not decision_context:
            return failed('missing_ai_decision_context', 'The server has no AI decision for this task.')
        if is_ai_selection:
            validation_error = self._validate_ai_selection_submission(
                decision_context,
                message,
                threat_id,
            )
            if validation_error:
                return failed(*validation_error)
        audit_pool = []
        audit_fallback_reason = None
        if decision_context:
            decision = decision_context.get('ai_decision') or {}
            audit_pool = list(decision.get('selected_pool') or [])
            audit_fallback_reason = decision.get('fallback_reason')

        existing_selection = session_state.get('sa_ai_selection')
        if is_ai_selection and isinstance(existing_selection, dict) and str(existing_selection.get('task_id')) == str(task_id):
            if existing_selection.get('threat_id') != threat_id:
                return failed('selection_conflict', 'Another AI threat has already been recorded for this task.')
            return [{
                'type': 'threat_clicked_recorded',
                'task_id': task_id,
                'threat_id': threat_id,
                'persisted': bool(existing_selection.get('persisted')),
                'duplicate': True,
                'timestamp': response_timestamp,
            }]

        parameters = {
            'threat_id': threat_id,
            'label': message.get('label'),
            'priority': message.get('priority'),
            'is_highest_priority': is_correct,
            'is_correct': is_correct,
            'correct_answer': highest_id or message.get('correct_answer'),
            'extra': message.get('extra', {})
        }
        ai_decision_audit = self._build_ai_decision_audit(
            decision_context,
            message,
            selected_id=threat_id,
            is_correct=is_correct,
            selected_pool=audit_pool,
            fallback_reason=audit_fallback_reason,
        ) if is_ai_selection else None
        if ai_decision_audit:
            parameters['ai_decision'] = ai_decision_audit
        operation = {
            'task_id': task_id,
            'operationType': 'threat_clicked',
            'timestamp': message.get('timestamp', response_timestamp),
            'isActive': True,
            'receive_timestamp': message.get('receive_timestamp'),
            'parameters': parameters,
            'user_id': message.get('user_id') or self.current_session.get('user_id', ''),
            'event_owner': client_event_owner
        }
        persisted = not session_state.get('is_practice', False)
        try:
            db_manager.record_operation(
                operation,
                session_state.get('is_practice', False),
                wait_for_commit=persisted and is_ai_selection,
            )
        except Exception as exc:
            self.logger.error(
                'Failed to persist threat_clicked: task_id=%s threat_id=%s error=%s',
                task_id, threat_id, exc, exc_info=True,
            )
            return failed('database_write_failed', str(exc))

        if is_ai_selection:
            session_state['sa_ai_selection'] = {
                'task_id': task_id,
                'threat_id': threat_id,
                'persisted': persisted,
                'timestamp': operation['timestamp'],
            }

        self._physio_marker("threat_clicked", message, session_state, {
            "operation": "threat_clicked",
            "task_type": "SA_THREAT_RESPONSE",
            "threat_id": threat_id,
            "is_highest_priority": is_correct,
        })
        if is_ai_selection:
            return [{
                'type': 'threat_clicked_recorded',
                'task_id': task_id,
                'threat_id': threat_id,
                'persisted': persisted,
                'duplicate': False,
                'timestamp': response_timestamp,
            }]
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

        if task_type == 'RADAR_TARGETING' and session_state.get('manual_control_disabled'):
            selection = session_state.get('radar_ai_selection')
            has_current_ai_selection = (
                isinstance(selection, dict)
                and str(selection.get('task_id')) == str(current_task_id)
                and str(selection.get('event_owner') or '').strip().lower() == 'ai'
                and bool(selection.get('target_id'))
            )
            if not has_current_ai_selection:
                self.logger.warning(
                    'Rejected radar result confirmation without recorded AI selection: task_id=%s',
                    current_task_id,
                )
                return [{
                    'type': 'task_result_confirmation_rejected',
                    'task_type': task_type,
                    'task_id': current_task_id,
                    'reason': 'missing_target_selected',
                    'message': 'AI target selection has not been recorded for the current radar task.',
                    'timestamp': int(time.time() * 1000),
                }]

        if task_type == 'SA_THREAT_RESPONSE' and session_state.get('manual_control_disabled'):
            selection = session_state.get('sa_ai_selection')
            has_current_ai_selection = (
                isinstance(selection, dict)
                and str(selection.get('task_id')) == str(current_task_id)
                and bool(selection.get('threat_id'))
            )
            if not has_current_ai_selection:
                self.logger.warning(
                    'Rejected SA result confirmation without recorded AI selection: task_id=%s',
                    current_task_id,
                )
                return [{
                    'type': 'task_result_confirmation_rejected',
                    'task_type': task_type,
                    'task_id': current_task_id,
                    'reason': 'missing_threat_clicked',
                    'message': 'AI threat selection has not been recorded for the current SA task.',
                    'timestamp': int(time.time() * 1000),
                }]

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
        control_mode, manual_control_disabled = self._set_control_mode_session(session_state, message, normalized_meta)
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
                "entry_completed": True,
                "message": "所有威胁排序任务已完成。",
                "is_ai_active": bool(is_ai_active_request),
                "is_practice": bool(is_practice),
            }]
        if not current_scenario:
            return [{
                "type": "all_tasks_completed",
                "task_type": task_type,
                "entry_completed": True,
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
        self._apply_control_mode_to_scenario(current_scenario, control_mode, manual_control_disabled)

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
        try:
            ai_accuracy, ai_decision = self._prepare_ai_accuracy(
                session_state,
                current_scenario=current_scenario,
                user_id=user_id,
                task_type=task_type,
                task_group_id=task_group_id,
                task_id=task_id,
                task_seq=task_seq,
            )
        except AIAccuracyConfigError as exc:
            self.logger.error("Invalid AI accuracy configuration: %s", exc)
            return [{
                "type": "ai_accuracy_config_invalid",
                "task_type": task_type,
                "task_group_id": task_group_id,
                "message": str(exc),
                "timestamp": int(time.time() * 1000),
            }]
        self._set_current_task(task_type, task_id, task_started_at_ms)
        session_state['sa_ai_selection'] = None
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
            session_state['sa_threat_truth'] = {
                'task_id': task_id,
                'threat_ids': [threat.id for threat in threat_result.threats],
                'highest_priority_threat_id': threat_result.highest_priority_threat_id,
            }
            if ai_decision:
                threat_ids = session_state['sa_threat_truth']['threat_ids']
                highest_id = session_state['sa_threat_truth']['highest_priority_threat_id']
                ai_decision = self._bind_ai_decision_selection(
                    session_state,
                    task_id,
                    task_type,
                    correct_pool=[highest_id] if highest_id is not None else [],
                    incorrect_pool=[
                        threat_id for threat_id in threat_ids
                        if str(threat_id) != str(highest_id)
                    ],
                    correct_pool_empty_reason='highest_priority_pool_empty',
                    incorrect_pool_empty_reason='single_threat_no_incorrect_pool',
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
            enhanced_response['control_mode'] = control_mode
            enhanced_response['manual_control_disabled'] = manual_control_disabled
            if ai_accuracy and ai_decision:
                enhanced_response['ai_accuracy'] = ai_accuracy
                enhanced_response['ai_decision'] = ai_decision
            if platform_meta:
                enhanced_response['platform_task'] = platform_meta
            
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
            highest_id = threats[0].get('id') if threats else None
            session_state['sa_threat_truth'] = {
                'task_id': task_id,
                'threat_ids': [threat.get('id') for threat in threats],
                'highest_priority_threat_id': highest_id,
            }
            if ai_decision:
                threat_ids = session_state['sa_threat_truth']['threat_ids']
                ai_decision = self._bind_ai_decision_selection(
                    session_state,
                    task_id,
                    task_type,
                    correct_pool=[highest_id] if highest_id is not None else [],
                    incorrect_pool=[
                        threat_id for threat_id in threat_ids
                        if str(threat_id) != str(highest_id)
                    ],
                    correct_pool_empty_reason='highest_priority_pool_empty',
                    incorrect_pool_empty_reason='single_threat_no_incorrect_pool',
                )
            
            response = {
                'type': 'sa_task_updated',
                'task_id': task_id,
                'saThreats': threats,
                'repetition_info': current_scenario['repetition_info'],
                'task_type': task_type,
                'is_ai_active': current_scenario['is_ai_active'],
                'control_mode': control_mode,
                'manual_control_disabled': manual_control_disabled,
                'ai_level': current_scenario.get('ai_level_name'),
                'ai_configs': config_manager.get_ai_levels(),
                'audio_enabled': current_scenario['audio_enabled'],
                'trust_calibration': config_manager.get_trust_calibration_config()
            }
            if ai_accuracy and ai_decision:
                response['ai_accuracy'] = ai_accuracy
                response['ai_decision'] = ai_decision
            if platform_meta:
                response['platform_task'] = platform_meta

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
                    "task_id": message_task_id,
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
                        "task_id": message_task_id or current_task_id,
                        "message": "Ignored antenna adjustment confirmation without a pending target.",
                    }, False

            if client_target_elevation is not None and abs(client_target_elevation - target_elevation) > 0.1:
                return {
                    "type": "settings_validation",
                    "status": "error",
                    "task_id": current_task_id,
                    "message": f"天线目标高度已更新，请按最新提示调整。当前提示目标为{client_target_elevation}°，服务端目标为{target_elevation}°"
                }, False
            
            if abs(client_elevation - target_elevation) <= 0.1:
                # 高度设置正确
                self.current_session['stage'] = 'target_identification'
                print('【调试】天线高度设置正确，开始发送目标数据')
                return {
                    "type": "settings_validation",
                    "status": "success",
                    "task_id": current_task_id,
                    "message": "天线高度设置正确，开始发送目标数据"
                }, True
            else:
                # 高度设置不正确
                return {
                    "type": "settings_validation",
                    "status": "error",
                    "task_id": current_task_id,
                    "message": f"天线高度设置不正确，目标为{target_elevation}°，当前为{client_elevation}°"
                }, False
        except Exception as e:
            print(f"天线调整出错: {e}")
            return {"type": "ERROR", "message": f"处理天线调整时出错: {e}"}, False

# 全局消息处理器实例
message_handler = MessageHandler() 
