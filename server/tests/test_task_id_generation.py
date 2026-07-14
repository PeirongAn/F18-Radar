import os
import sys
import sqlite3
import json
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from managers import task_manager
from managers.database_manager import DatabaseManager


class FakeDb:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE task_settings (task_id INTEGER)")
        self.conn.execute("CREATE TABLE user_operations (task_id INTEGER)")
        self.conn.execute("CREATE TABLE task_runs (task_id INTEGER)")
        self.conn.execute("CREATE TABLE task_groups (group_id INTEGER)")
        self.conn.execute("INSERT INTO task_settings (task_id) VALUES (10)")
        self.conn.execute("INSERT INTO user_operations (task_id) VALUES (11)")
        self.conn.execute("INSERT INTO task_runs (task_id) VALUES (42)")
        self.conn.execute("INSERT INTO task_groups (group_id) VALUES (50)")
        self.conn.commit()

    @contextmanager
    def get_connection(self):
        yield self.conn


class DummyLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


def make_sync_database_manager(db_path):
    manager = object.__new__(DatabaseManager)
    manager.db_path = str(db_path)
    manager.logger = DummyLogger()
    manager._shutdown_requested = True

    def execute_sync(sql, params):
        with manager.get_connection() as conn:
            conn.execute(sql, params)
            conn.commit()

    manager.execute_async = execute_sync
    return manager


def test_generate_task_id_includes_task_runs(monkeypatch):
    fake_db = FakeDb()
    monkeypatch.setattr(task_manager, "db_manager", fake_db)

    assert task_manager.generate_task_id() == 51


def test_task_setting_key_includes_trust_state():
    manager = object.__new__(DatabaseManager)
    scenario = {
        "difficulty_name": "low",
        "repetition_info": {"current": 1},
        "is_ai_active": True,
        "ai_level_name": "L2",
        "audio_enabled": True,
    }

    under_key = DatabaseManager.build_task_setting_key(
        manager,
        scenario,
        "user-a",
        "AI",
        "RADAR_TARGETING",
        "under_trust",
    )
    over_key = DatabaseManager.build_task_setting_key(
        manager,
        scenario,
        "user-a",
        "AI",
        "RADAR_TARGETING",
        "over_trust",
    )

    assert under_key != over_key
    assert under_key[-1] == "under_trust"
    assert over_key[-1] == "over_trust"


def test_html_questionnaire_resolves_completed_external_subtask_run(tmp_path):
    db_path = tmp_path / "questionnaire.db"
    manager = make_sync_database_manager(db_path)
    manager.initialize_database()
    overall_config = {
        "normalized": {
            "difficulty_key": "high",
            "current_level": "3",
            "include_ai": True,
            "is_practice": False,
        }
    }
    subtask_config = {
        **overall_config,
        "overall_task_id": 100,
        "sub_task_seq": 1,
    }
    with manager.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO task_runs (
                task_id, task_type, user_id, status, expected_subtasks,
                completed_subtasks, current_subtask_seq, started_at_ms,
                completed_at_ms, config_json, last_raw_message_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (100, "PLATFORM_CONTROL", "u1", "completed", 2, 1, 1, 10, 20, json.dumps(overall_config), "{}"),
        )
        conn.execute(
            """
            INSERT INTO task_runs (
                task_id, task_type, user_id, status, expected_subtasks,
                completed_subtasks, current_subtask_seq, started_at_ms,
                completed_at_ms, config_json, last_raw_message_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (101, "PLATFORM_CONTROL", "u1", "completed", 1, 1, 1, 11, 21, json.dumps(subtask_config), "{}"),
        )
        conn.commit()

    manager.record_questionnaire({
        "type": "questionnaire_submitted",
        "userId": "u1",
        "taskType": "PLATFORM_CONTROL",
        "repetitionCurrent": 1,
        "repetitionTotal": 0,
        "taskInfo": {
            "difficulty": "low",
            "autonomyLevel": "1",
            "isPractice": True,
        },
        "answers": {"1": 5},
        "source": "react_modal",
        "timestamp": 30,
    })

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT task_id, task_group_id, task_type, difficulty, autonomy_level, is_ai_active, is_practice
            FROM questionnaire_responses
            """
        ).fetchone()
    assert row == (101, 100, "PLATFORM_CONTROL", "high", "3", 1, 0)
