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


def test_same_active_trial_start_is_idempotent(monkeypatch):
    fake_db = FakeDatabase()
    generated = iter([100, 101])
    monkeypatch.setattr(message_handler_module, "db_manager", fake_db)
    monkeypatch.setattr(message_handler_module, "generate_task_id", lambda: next(generated))

    handler = message_handler_module.MessageHandler()
    key = ("u1", "RADAR_TARGETING", "AI", 1, 1, "L2", "low", 0, "")

    first_task_id, duplicate, retried_task_id, started_at = handler._prepare_task_start_identity(
        "RADAR_TARGETING", key, None, 1_000
    )
    assert (first_task_id, duplicate, retried_task_id, started_at) == (100, False, None, 1_000)

    handler._set_current_task("RADAR_TARGETING", first_task_id, started_at, key)
    handler._cache_task_start_responses(
        "RADAR_TARGETING", first_task_id, key, [{"type": "init_settings", "task_id": 100}]
    )
    repeated = handler._prepare_task_start_identity(
        "RADAR_TARGETING", key, None, 2_000
    )

    assert repeated == (100, True, None, 1_000)
    assert handler._get_cached_task_start_responses(
        "RADAR_TARGETING", 100, key
    ) == [{"type": "init_settings", "task_id": 100}]


def test_retry_gets_new_task_id_and_closes_old_run(monkeypatch):
    fake_db = FakeDatabase()
    fake_db.runs[76] = {"task_id": 76, "status": "active"}
    monkeypatch.setattr(message_handler_module, "db_manager", fake_db)
    monkeypatch.setattr(message_handler_module, "generate_task_id", lambda: 77)

    handler = message_handler_module.MessageHandler()
    key = ("u1", "RADAR_TARGETING", "AI", 1, 1, "L2", "low", 0, "")
    task_id, duplicate, retried_task_id, started_at = handler._prepare_task_start_identity(
        "RADAR_TARGETING", key, 76, 3_000
    )

    assert (task_id, duplicate, retried_task_id, started_at) == (77, False, 76, 3_000)
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
