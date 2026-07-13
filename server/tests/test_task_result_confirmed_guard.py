import asyncio
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
logging.raiseExceptions = False

from core.message_handler import MessageHandler


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

    assert result == [{
        "type": "all_tasks_completed",
        "task_type": "RADAR_TARGETING",
        "task_id": 66,
        "task_group_id": 901,
        "repetition_info": task_manager.current_scenario["repetition_info"],
        "is_ai_active": True,
        "is_practice": False,
    }]


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
    assert "stale" in response["message"]


def test_antenna_confirmation_without_a_pending_target_is_ignored():
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

    assert is_valid is False
    assert response["status"] == "ignored"
    assert "pending target" in response["message"]


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
