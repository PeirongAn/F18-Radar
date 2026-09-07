import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

message_handler_module = importlib.import_module("core.message_handler")


class FakeDatabase:
    def __init__(self):
        self.runs = {}
        self.progress_updates = []
        self.events = []

    def get_task_run(self, task_id):
        return self.runs.get(int(task_id))

    def update_task_run_progress(self, task_id, **kwargs):
        self.progress_updates.append((int(task_id), kwargs))

    def record_task_event(self, **kwargs):
        self.events.append(kwargs)


class FakeLogger:
    def debug(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass


def test_second_start_gets_new_task_id_and_retries_active_run(monkeypatch):
    fake_db = FakeDatabase()
    generated = iter([100, 101])
    monkeypatch.setattr(message_handler_module, "db_manager", fake_db)
    monkeypatch.setattr(message_handler_module, "generate_task_id", lambda: next(generated))

    handler = message_handler_module.MessageHandler()
    first_task_id, retried_task_id, started_at = handler._prepare_task_start_identity(
        "RADAR_TARGETING", None, 1_000
    )
    assert (first_task_id, retried_task_id, started_at) == (100, None, 1_000)

    fake_db.runs[100] = {"task_id": 100, "status": "active"}
    handler._set_current_task("RADAR_TARGETING", first_task_id, started_at)
    repeated = handler._prepare_task_start_identity(
        "RADAR_TARGETING", 100, 2_000
    )

    assert repeated == (101, 100, 2_000)
    handler._mark_task_run_retried(100, 101, "RADAR_TARGETING", "u1", 2_000)

    assert fake_db.progress_updates == [(
        100,
        {
            "status": "retried",
            "completed_at_ms": 2_000,
            "raw_message_json": '{"replacement_task_id": 101, "reason": "new_trial_execution"}',
        },
    )]
    assert fake_db.events[0]["event_type"] == "task_retried"
    assert fake_db.events[0]["task_id"] == 100


def test_incomplete_restart_keeps_same_repetition(monkeypatch):
    manager = object.__new__(message_handler_module.TaskScenarioManager)
    manager.config = {}
    manager.user_id = "u1"
    manager.task_type = "RADAR_TARGETING"
    manager.progress_task_type = "RADAR_TARGETING::0-L1-high"
    manager.is_practice = False
    manager.logger = FakeLogger()
    manager.max_repetitions = 10
    manager.repetition_counter = 4
    manager.ai_queue = []
    manager.manual_queue = []
    manager.active_queue = manager.manual_queue
    manager.current_scenario = {
        "difficulty_name": "high",
        "is_ai_active": False,
        "audio_enabled": True,
        "ai_level_name": "L1",
        "repetition_info": {"current": 4, "total": 10},
    }
    monkeypatch.setattr(manager, "_refresh_config", lambda: None)
    monkeypatch.setattr(manager, "_check_previous_task_completion_status", lambda: False)
    monkeypatch.setattr(manager, "_refresh_scenario_config", lambda scenario: None)
    monkeypatch.setattr(manager, "_save_to_db", lambda: None)

    result = manager.get_next_task_parameters(False)

    assert manager.repetition_counter == 4
    assert result["repetition_info"]["current"] == 4
    assert result["repetition_info"]["previous_task_completed"] is False


def test_retry_gets_new_task_id_and_closes_old_active_run(monkeypatch):
    fake_db = FakeDatabase()
    fake_db.runs[76] = {"task_id": 76, "status": "active"}
    monkeypatch.setattr(message_handler_module, "db_manager", fake_db)
    monkeypatch.setattr(message_handler_module, "generate_task_id", lambda: 77)

    handler = message_handler_module.MessageHandler()
    task_id, retried_task_id, started_at = handler._prepare_task_start_identity(
        "RADAR_TARGETING", 76, 3_000
    )

    assert (task_id, retried_task_id, started_at) == (77, 76, 3_000)
    handler._mark_task_run_retried(76, 77, "RADAR_TARGETING", "u1", started_at)

    assert fake_db.progress_updates == [(
        76,
        {
            "status": "retried",
            "completed_at_ms": 3_000,
            "raw_message_json": '{"replacement_task_id": 77, "reason": "new_trial_execution"}',
        },
    )]
    assert fake_db.events[0]["event_type"] == "task_retried"
    assert fake_db.events[0]["task_id"] == 76


def test_completed_matching_task_is_never_reused_or_modified(monkeypatch):
    fake_db = FakeDatabase()
    fake_db.runs[99] = {"task_id": 99, "group_id": 98, "status": "completed"}
    monkeypatch.setattr(message_handler_module, "db_manager", fake_db)
    monkeypatch.setattr(message_handler_module, "generate_task_id", lambda: 124)

    handler = message_handler_module.MessageHandler()
    task_id, retried_task_id, started_at = handler._prepare_task_start_identity(
        "RADAR_TARGETING", 99, 4_000
    )

    assert (task_id, retried_task_id, started_at) == (124, None, 4_000)
    handler._mark_task_run_retried(retried_task_id, task_id, "RADAR_TARGETING", "u1", started_at)
    assert fake_db.progress_updates == []
    assert fake_db.events == []


def test_completed_task_becomes_inactive_before_same_condition_starts_again(monkeypatch):
    fake_db = FakeDatabase()
    fake_db.runs[99] = {"task_id": 99, "group_id": 98, "status": "completed"}
    monkeypatch.setattr(message_handler_module, "db_manager", fake_db)
    monkeypatch.setattr(message_handler_module, "generate_task_id", lambda: 124)

    handler = message_handler_module.MessageHandler()
    handler._set_current_task("RADAR_TARGETING", 99, 1_000)
    handler._mark_current_task_inactive("RADAR_TARGETING", 99)

    result = handler._prepare_task_start_identity("RADAR_TARGETING", 99, 4_000)
    assert result == (124, None, 4_000)


def test_practice_group_never_reuses_completed_formal_group_task_id(monkeypatch):
    fake_db = FakeDatabase()
    fake_db.runs[99] = {"task_id": 99, "group_id": 98, "status": "completed"}
    monkeypatch.setattr(message_handler_module, "db_manager", fake_db)
    monkeypatch.setattr(message_handler_module, "generate_task_id", lambda: 124)

    handler = message_handler_module.MessageHandler()
    handler._set_current_task("RADAR_TARGETING", 99, 1_000)
    handler._mark_current_task_inactive("RADAR_TARGETING", 99)

    result = handler._prepare_task_start_identity(
        "RADAR_TARGETING", 99, 4_000
    )
    assert result == (124, None, 4_000)
