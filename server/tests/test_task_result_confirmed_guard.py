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
