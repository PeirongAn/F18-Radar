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
