import asyncio
import importlib
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
logging.raiseExceptions = False

from core.message_handler import MessageHandler

message_handler_module = importlib.import_module("core.message_handler")


class FakeTaskManager:
    def __init__(self):
        self.completed = False
        self.current_scenario = {
            "repetition_info": {"current": 2, "total": 5},
            "is_ai_active": False,
        }

    def mark_task_completed(self):
        self.completed = True


class FakeGazeService:
    def __init__(self):
        self.stopped = []

    def stop_task(self, task_id, end_trigger=""):
        self.stopped.append((task_id, end_trigger))


def run_confirm(handler, message, task_manager):
    return asyncio.run(
        handler._handle_task_result_confirmed(
            message,
            {"task_manager": task_manager},
        )
    )


def test_stale_task_result_confirmed_is_ignored():
    handler = MessageHandler()
    task_manager = FakeTaskManager()
    gaze = FakeGazeService()
    handler.set_gaze_service(gaze)
    handler.current_session.update(
        {
            "task_id": 66,
            "task_started_at_ms": int(time.time() * 1000) - 5000,
            "user_id": "ANPEIRONG01",
        }
    )

    result = run_confirm(
        handler,
        {
            "type": "task_result_confirmed",
            "task_type": "RADAR_TARGETING",
            "task_id": 65,
            "user_id": "ANPEIRONG01",
            "timestamp": int(time.time() * 1000),
        },
        task_manager,
    )

    assert result == []
    assert task_manager.completed is False
    assert gaze.stopped == []


def test_matching_task_result_confirmed_completes_current_task():
    handler = MessageHandler()
    task_manager = FakeTaskManager()
    gaze = FakeGazeService()
    handler.set_gaze_service(gaze)
    handler.current_session.update(
        {
            "task_id": 66,
            "task_started_at_ms": int(time.time() * 1000) - 5000,
            "user_id": "ANPEIRONG01",
        }
    )

    result = run_confirm(
        handler,
        {
            "type": "task_result_confirmed",
            "task_type": "RADAR_TARGETING",
            "task_id": 66,
            "user_id": "ANPEIRONG01",
            "timestamp": int(time.time() * 1000),
        },
        task_manager,
    )

    assert result == []
    assert task_manager.completed is True
    assert gaze.stopped == [("66", "task_result_confirmed")]


def _ai_decision_context(task_id):
    return {
        str(task_id): {
            "task_type": "RADAR_TARGETING",
            "ai_accuracy": {
                "algorithm_version": "difficulty-group-range-v1",
                "task_group_id": 5,
                "ai_level": "L2",
                "difficulty": "high",
                "probability_range": [0.7, 0.8],
                "probability_seed": 10,
                "probability_random": 0.4,
                "sampled_probability": 0.74,
            },
            "ai_decision": {
                "task_id": task_id,
                "task_seq": 1,
                "decision_seed": 11,
                "decision_random": 0.2,
                "pool_random": 0.3,
                "intended_correct": True,
                "selection_protocol": "server-authoritative-target-v1",
                "selected_pool": ["enemy-1"],
                "fallback_reason": None,
                "pool_index": 0,
                "expected_target_id": "enemy-1",
            },
        }
    }


def test_pure_ai_target_selection_is_acknowledged_only_after_recording(monkeypatch):
    handler = MessageHandler()
    handler._set_current_task("RADAR_TARGETING", 66, int(time.time() * 1000))
    handler.current_session["user_id"] = "pure-ai-user"
    session_state = {
        "manual_control_disabled": True,
        "is_practice": False,
        "radar_ai_selection": None,
        "ai_decision_contexts": _ai_decision_context(66),
    }
    recorded = []

    monkeypatch.setattr(
        message_handler_module.target_manager,
        "get_targets",
        lambda: [{"id": "enemy-1", "type": "army"}],
    )

    def record_operation(operation, is_practice, wait_for_commit=False):
        recorded.append((operation, is_practice, wait_for_commit))
        return True

    monkeypatch.setattr(message_handler_module.db_manager, "record_operation", record_operation)

    message = {
        "type": "target_selected",
        "task_id": 66,
        "target_id": "enemy-1",
        "event_owner": "AI",
        "timestamp": int(time.time() * 1000),
        "ai_decision_outcome": {
            "selection_protocol": "server-authoritative-target-v1",
            "expected_target_id": "enemy-1",
        },
    }
    result = asyncio.run(handler._handle_target_selected(message, session_state, "AI"))

    assert result[0]["type"] == "target_selected_recorded"
    assert result[0]["task_id"] == 66
    assert result[0]["target_id"] == "enemy-1"
    assert result[0]["persisted"] is True
    assert recorded[0][2] is True
    assert session_state["radar_ai_selection"]["target_id"] == "enemy-1"

    duplicate = asyncio.run(handler._handle_target_selected(message, session_state, "AI"))
    assert duplicate[0]["duplicate"] is True
    assert len(recorded) == 1


def test_pure_ai_target_selection_failure_does_not_unlock_iff(monkeypatch):
    handler = MessageHandler()
    handler._set_current_task("RADAR_TARGETING", 67, int(time.time() * 1000))
    session_state = {
        "manual_control_disabled": True,
        "is_practice": False,
        "radar_ai_selection": None,
        "ai_decision_contexts": _ai_decision_context(67),
    }
    monkeypatch.setattr(
        message_handler_module.target_manager,
        "get_targets",
        lambda: [{"id": "enemy-1", "type": "army"}],
    )

    def fail_recording(*_args, **_kwargs):
        raise RuntimeError("disk unavailable")

    monkeypatch.setattr(message_handler_module.db_manager, "record_operation", fail_recording)
    result = asyncio.run(handler._handle_target_selected({
        "type": "target_selected",
        "task_id": 67,
        "target_id": "enemy-1",
        "event_owner": "AI",
        "ai_decision_outcome": {
            "selection_protocol": "server-authoritative-target-v1",
            "expected_target_id": "enemy-1",
        },
    }, session_state, "AI"))

    assert result[0]["type"] == "target_selected_record_failed"
    assert result[0]["reason"] == "database_write_failed"
    assert session_state["radar_ai_selection"] is None


def test_ai_target_selection_rejects_outdated_frontend_protocol(monkeypatch):
    handler = MessageHandler()
    handler._set_current_task("RADAR_TARGETING", 70, int(time.time() * 1000))
    session_state = {
        "is_practice": False,
        "radar_ai_selection": None,
        "ai_decision_contexts": _ai_decision_context(70),
    }
    monkeypatch.setattr(
        message_handler_module.target_manager,
        "get_targets",
        lambda: [{"id": "enemy-1", "type": "army"}],
    )
    result = asyncio.run(handler._handle_target_selected({
        "type": "target_selected",
        "task_id": 70,
        "target_id": "enemy-1",
        "event_owner": "AI",
    }, session_state, "AI"))

    assert result[0]["type"] == "target_selected_record_failed"
    assert result[0]["reason"] == "ai_decision_protocol_mismatch"
    assert result[0]["expected_target_id"] == "enemy-1"


def test_ai_target_selection_rejects_target_outside_server_decision(monkeypatch):
    handler = MessageHandler()
    handler._set_current_task("RADAR_TARGETING", 71, int(time.time() * 1000))
    session_state = {
        "is_practice": False,
        "radar_ai_selection": None,
        "ai_decision_contexts": _ai_decision_context(71),
    }
    monkeypatch.setattr(
        message_handler_module.target_manager,
        "get_targets",
        lambda: [
            {"id": "enemy-1", "type": "army"},
            {"id": "friend-1", "type": "friend"},
        ],
    )
    result = asyncio.run(handler._handle_target_selected({
        "type": "target_selected",
        "task_id": 71,
        "target_id": "friend-1",
        "event_owner": "AI",
        "ai_decision_outcome": {
            "selection_protocol": "server-authoritative-target-v1",
            "expected_target_id": "enemy-1",
        },
    }, session_state, "AI"))

    assert result[0]["type"] == "target_selected_record_failed"
    assert result[0]["reason"] == "ai_decision_target_mismatch"
    assert result[0]["expected_target_id"] == "enemy-1"


def test_pure_ai_result_confirmation_requires_current_ai_selection():
    handler = MessageHandler()
    task_manager = FakeTaskManager()
    task_manager.current_scenario["is_ai_active"] = True
    handler._set_current_task("RADAR_TARGETING", 68, int(time.time() * 1000) - 5000)
    session_state = {
        "task_manager": task_manager,
        "manual_control_disabled": True,
        "radar_ai_selection": None,
    }

    result = asyncio.run(handler._handle_task_result_confirmed({
        "type": "task_result_confirmed",
        "task_type": "RADAR_TARGETING",
        "task_id": 68,
        "timestamp": int(time.time() * 1000),
    }, session_state))

    assert result[0]["type"] == "task_result_confirmation_rejected"
    assert result[0]["reason"] == "missing_target_selected"
    assert task_manager.completed is False


def test_pure_ai_result_confirmation_accepts_current_ai_selection(monkeypatch):
    handler = MessageHandler()
    task_manager = FakeTaskManager()
    task_manager.current_scenario["is_ai_active"] = True
    handler._set_current_task("RADAR_TARGETING", 69, int(time.time() * 1000) - 5000)
    session_state = {
        "task_manager": task_manager,
        "manual_control_disabled": True,
        "is_practice": True,
        "radar_ai_selection": {
            "task_id": 69,
            "target_id": "enemy-1",
            "event_owner": "AI",
        },
    }
    monkeypatch.setattr(message_handler_module.db_manager, "record_operation", lambda *_args, **_kwargs: True)

    result = asyncio.run(handler._handle_task_result_confirmed({
        "type": "task_result_confirmed",
        "task_type": "RADAR_TARGETING",
        "task_id": 69,
        "timestamp": int(time.time() * 1000),
    }, session_state))

    assert result == []
    assert task_manager.completed is True


def test_task_group_completion_returns_its_group_id():
    handler = MessageHandler()
    task_manager = FakeTaskManager()
    task_manager.current_scenario = {
        "repetition_info": {
            "current": 3,
            "total": 3,
            "task_group_id": 901,
            "is_ai_active": True,
            "is_practice": False,
        },
        "task_group_id": 901,
        "is_ai_active": True,
    }
    handler.current_session.update(
        {
            "task_id": 66,
            "task_started_at_ms": int(time.time() * 1000) - 5000,
            "user_id": "ANPEIRONG01",
        }
    )

    result = run_confirm(
        handler,
        {
            "type": "task_result_confirmed",
            "task_type": "RADAR_TARGETING",
            "task_id": 66,
            "user_id": "ANPEIRONG01",
            "timestamp": int(time.time() * 1000),
        },
        task_manager,
    )

    assert len(result) == 1
    assert isinstance(result[0].pop("timestamp"), int)
    assert result == [{
        "type": "all_tasks_completed",
        "task_type": "RADAR_TARGETING",
        "task_id": 66,
        "task_group_id": 901,
        "repetition_info": task_manager.current_scenario["repetition_info"],
        "is_ai_active": True,
        "is_practice": False,
    }]


def test_new_platform_task_forces_a_fresh_task_group(monkeypatch):
    handler = MessageHandler()
    task_manager = FakeTaskManager()
    task_manager.current_scenario = {
        "repetition_info": {
            "current": 1,
            "total": 2,
            "task_group_id": 901,
        },
        "task_group_id": 901,
        "is_ai_active": True,
    }
    task_manager.is_practice = False
    task_manager._save_to_db = lambda: None
    ensured_groups = []

    monkeypatch.setattr(message_handler_module, "generate_task_id", lambda: 902)
    monkeypatch.setattr(message_handler_module.db_manager, "find_active_task_group", lambda **kwargs: None)
    monkeypatch.setattr(
        message_handler_module.db_manager,
        "ensure_task_group",
        lambda **kwargs: ensured_groups.append(kwargs),
    )

    group_id, task_seq = handler._ensure_current_task_group(
        task_manager=task_manager,
        task_type="RADAR_TARGETING",
        user_id="ANPEIRONG01",
        current_scenario=task_manager.current_scenario,
        event_owner="AI",
        trust_state="",
        message={"type": "task_start"},
        started_at_ms=1234,
        progress_key="RADAR_TARGETING::1-L1-low",
        platform_meta={"normalized": {"platform_task_id": "ANPEIRONG01"}},
        force_new_group=True,
    )

    assert group_id == 902
    assert task_seq == 1
    assert task_manager.current_scenario["task_group_id"] == 902
    assert task_manager.current_scenario["repetition_info"]["task_group_id"] == 902
    assert ensured_groups[0]["group_id"] == 902


def test_new_platform_task_reuses_external_overall_task_group(monkeypatch):
    handler = MessageHandler()
    task_manager = FakeTaskManager()
    task_manager.current_scenario = {
        "repetition_info": {"current": 1, "total": 2, "task_group_id": 901},
        "task_group_id": 901,
        "is_ai_active": True,
    }
    task_manager.is_practice = False
    task_manager._save_to_db = lambda: None
    ensured_groups = []

    monkeypatch.setattr(
        message_handler_module.db_manager,
        "ensure_task_group",
        lambda **kwargs: ensured_groups.append(kwargs),
    )

    group_id, task_seq = handler._ensure_current_task_group(
        task_manager=task_manager,
        task_type="RADAR_TARGETING",
        user_id="ANPEIRONG01",
        current_scenario=task_manager.current_scenario,
        event_owner="AI",
        trust_state="",
        message={"type": "task_start"},
        started_at_ms=1234,
        progress_key="RADAR_TARGETING::1-L1-low",
        platform_meta={"normalized": {"overall_task_id": 777}},
        force_new_group=True,
    )

    assert group_id == 777
    assert task_seq == 1
    assert task_manager.current_scenario["task_group_id"] == 777
    assert task_manager.current_scenario["repetition_info"]["task_group_id"] == 777
    assert ensured_groups[0]["group_id"] == 777


def test_new_formal_platform_task_does_not_reuse_active_practice_group(monkeypatch):
    handler = MessageHandler()
    task_manager = FakeTaskManager()
    task_manager.current_scenario = {
        "repetition_info": {"current": 1, "total": 5, "task_group_id": 901},
        "task_group_id": 901,
        "is_ai_active": False,
    }
    task_manager.is_practice = False
    task_manager._save_to_db = lambda: None
    ensured_groups = []
    active_group_lookups = []

    monkeypatch.setattr(message_handler_module, "generate_task_id", lambda: 999)
    monkeypatch.setattr(
        message_handler_module.db_manager,
        "find_active_task_group",
        lambda **kwargs: active_group_lookups.append(kwargs) or {
            "group_id": 777,
            "status": "active",
            "expected_task_count": 4,
            "is_practice": True,
        },
    )
    monkeypatch.setattr(
        message_handler_module.db_manager,
        "ensure_task_group",
        lambda **kwargs: ensured_groups.append(kwargs),
    )

    group_id, _ = handler._ensure_current_task_group(
        task_manager=task_manager,
        task_type="RADAR_TARGETING",
        user_id="ANPEIRONG01",
        current_scenario=task_manager.current_scenario,
        event_owner="AI",
        trust_state="",
        message={"type": "task_start"},
        started_at_ms=1234,
        progress_key="RADAR_TARGETING::1-L1-low",
        platform_meta={"normalized": {"platform_task_id": "ANPEIRONG01"}},
        force_new_group=True,
    )

    assert group_id == 999
    assert active_group_lookups == []
    assert task_manager.current_scenario["task_group_id"] == 999
    assert task_manager.current_scenario["repetition_info"]["task_group_id"] == 999
    assert ensured_groups[0]["group_id"] == 999
    assert ensured_groups[0]["expected_task_count"] == 5
    assert ensured_groups[0]["is_practice"] is False


def test_sa_task_group_completion_returns_its_group_id():
    handler = MessageHandler()
    task_manager = FakeTaskManager()
    task_manager.current_scenario = {
        "repetition_info": {
            "current": 2,
            "total": 2,
            "task_group_id": 902,
            "is_ai_active": True,
            "is_practice": False,
        },
        "task_group_id": 902,
        "is_ai_active": True,
    }
    handler.current_session.update(
        {
            "task_id": 67,
            "task_started_at_ms": int(time.time() * 1000) - 5000,
            "user_id": "ANPEIRONG01",
        }
    )

    result = asyncio.run(
        handler._handle_task_result_confirmed(
            {
                "type": "task_result_confirmed",
                "task_type": "SA_THREAT_RESPONSE",
                "task_id": 67,
                "user_id": "ANPEIRONG01",
                "timestamp": int(time.time() * 1000),
            },
            {"sa_task_manager": task_manager},
        )
    )

    assert result[0]["type"] == "all_tasks_completed"
    assert result[0]["task_type"] == "SA_THREAT_RESPONSE"
    assert result[0]["task_group_id"] == 902


def test_sa_task_group_completion_recovers_group_id_from_task_run(monkeypatch):
    handler = MessageHandler()
    task_manager = FakeTaskManager()
    task_manager.current_scenario = {
        "repetition_info": {
            "current": 2,
            "total": 2,
            "is_ai_active": False,
            "is_practice": False,
        },
        "is_ai_active": False,
    }
    handler.current_session.update(
        {
            "task_id": 70,
            "task_started_at_ms": int(time.time() * 1000) - 5000,
            "user_id": "ANPEIRONG08",
        }
    )
    recovered_task_ids = []

    def get_task_run_group_id(task_id):
        recovered_task_ids.append(task_id)
        return 903

    monkeypatch.setattr(
        message_handler_module.db_manager,
        "get_task_run_group_id",
        get_task_run_group_id,
    )

    result = asyncio.run(
        handler._handle_task_result_confirmed(
            {
                "type": "task_result_confirmed",
                "task_type": "SA_THREAT_RESPONSE",
                "task_id": 70,
                "user_id": "ANPEIRONG08",
                "timestamp": int(time.time() * 1000),
            },
            {"sa_task_manager": task_manager, "is_practice": True},
        )
    )

    assert recovered_task_ids == [70]
    assert result[0]["type"] == "all_tasks_completed"
    assert result[0]["task_group_id"] == 903
    assert result[0]["is_ai_active"] is False
    assert task_manager.current_scenario["task_group_id"] == 903
    assert task_manager.current_scenario["repetition_info"]["task_group_id"] == 903


def test_stale_antenna_confirmation_is_ignored_after_task_reset():
    handler = MessageHandler()
    handler.current_session.update({
        "task_id": 101,
        "task_ids": {"RADAR_TARGETING": 101},
        "target_elevation": None,
        "stage": "init",
    })

    response, is_valid = handler._handle_antenna_adjustment({
        "task_id": 100,
        "elevation": 2,
        "targetElevation": 2,
    })

    assert is_valid is False
    assert response["status"] == "ignored"
    assert response["task_id"] == 100
    assert "stale" in response["message"]


def test_antenna_confirmation_recovers_missing_target_for_current_task():
    handler = MessageHandler()
    handler.current_session.update({
        "task_id": 101,
        "task_ids": {"RADAR_TARGETING": 101},
        "target_elevation": None,
        "stage": "init",
    })

    response, is_valid = handler._handle_antenna_adjustment({
        "task_id": 101,
        "elevation": 2,
        "targetElevation": 2,
    })

    assert is_valid is True
    assert response["status"] == "success"
    assert response["task_id"] == 101
    assert handler.current_session["target_elevation"] == 2


def test_ignored_antenna_confirmation_is_not_sent_to_client():
    handler = MessageHandler()
    handler.current_session.update({
        "task_id": 101,
        "task_ids": {"RADAR_TARGETING": 101},
        "target_elevation": None,
        "stage": "init",
    })

    result = asyncio.run(handler._handle_antenna_adjusted(
        {
            "task_id": 100,
            "elevation": 2,
            "targetElevation": 2,
        },
        {},
        "AI",
    ))

    assert result == []


def test_stale_settings_update_is_ignored_after_task_reset():
    handler = MessageHandler()
    handler.current_session.update({
        "task_id": 101,
        "task_ids": {"RADAR_TARGETING": 101},
        "target_elevation": None,
        "stage": "init",
    })

    result = asyncio.run(handler._handle_settings_update(
        {
            "task_id": 100,
            "range": 80,
            "scanAngle": 30,
        },
        {},
        "AI",
    ))

    assert result == [{
        "type": "settings_validation",
        "status": "ignored",
        "task_id": 100,
        "message": "Ignored stale radar settings update.",
    }]
    assert handler.current_session["target_elevation"] is None


def test_current_settings_validation_is_scoped_to_current_task():
    handler = MessageHandler()
    handler.current_session.update({
        "task_id": 101,
        "task_ids": {"RADAR_TARGETING": 101},
        "target_elevation": None,
        "stage": "init",
    })

    result = asyncio.run(handler._handle_settings_update(
        {
            "task_id": 101,
            "range": 80,
            "scanAngle": 30,
        },
        {"is_practice": True},
        "AI",
    ))

    assert result[0]["type"] == "settings_validation"
    assert result[0]["status"] == "success"
    assert result[0]["task_id"] == 101
    assert result[1]["type"] == "adjust_antenna"
    assert result[1]["task_id"] == 101
