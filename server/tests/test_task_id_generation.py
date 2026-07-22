import os
import sys
import sqlite3
import json
import threading
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
            INSERT INTO task_groups (
                group_id, task_type, user_id, status, expected_task_count,
                completed_task_count, current_task_seq, started_at_ms,
                completed_at_ms, difficulty, autonomy_level, is_ai_active,
                is_practice, config_json
            ) VALUES (100, 'PLATFORM_CONTROL', 'u1', 'completed', 2, 2, 2,
                      10, 21, 'high', '3', 1, 0, '{}')
            """
        )
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
            "difficulty": "high",
            "autonomyLevel": "3",
            "isPractice": False,
        },
        "answers": {"1": 5},
        "source": "react_modal",
        "timestamp": 30,
    })

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT task_group_id, task_type, difficulty, autonomy_level, is_ai_active, is_practice
            FROM questionnaire_responses
            """
        ).fetchone()
    assert row == (100, "PLATFORM_CONTROL", "high", "3", 1, 0)
    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(questionnaire_responses)")}
    assert "task_id" not in columns


def test_questionnaire_context_falls_back_from_stale_id_to_latest_completed_run(tmp_path):
    db_path = tmp_path / "questionnaire-context.db"
    manager = make_sync_database_manager(db_path)
    manager.initialize_database()
    config = {
        "normalized": {
            "difficulty_key": "low",
            "current_level": "L1",
            "include_ai": True,
            "is_practice": False,
        },
        "overall_task_id": 10,
        "sub_task_seq": 1,
    }
    with manager.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO task_groups (
                group_id, task_type, user_id, status, expected_task_count,
                completed_task_count, current_task_seq, started_at_ms,
                completed_at_ms, difficulty, autonomy_level, is_ai_active,
                is_practice, config_json
            ) VALUES (10, 'PLATFORM_CONTROL', 'u1', 'completed', 1, 1, 1,
                      10, 20, 'low', 'L1', 1, 0, '{}')
            """
        )
        conn.execute(
            """
            INSERT INTO task_runs (
                task_id, group_id, task_type, user_id, status, expected_subtasks,
                completed_subtasks, current_subtask_seq, started_at_ms,
                completed_at_ms, config_json, last_raw_message_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (11, 10, "PLATFORM_CONTROL", "u1", "completed", 1, 1, 1, 10, 20, json.dumps(config), "{}"),
        )
        conn.commit()

    stale_context = manager.resolve_questionnaire_task_context("u1", "PLATFORM_CONTROL", submitted_task_id=999)
    blank_context = manager.resolve_questionnaire_task_context("", "")

    assert stale_context["task_group_id"] == 10
    assert blank_context["task_group_id"] == 10
    assert blank_context["difficulty"] == "low"
    assert blank_context["autonomy_level"] == "L1"


def test_questionnaire_context_prefers_active_task_group(tmp_path):
    db_path = tmp_path / "questionnaire-active-group.db"
    manager = make_sync_database_manager(db_path)
    manager.initialize_database()
    with manager.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO task_groups (
                group_id, task_type, user_id, status, expected_task_count,
                completed_task_count, current_task_seq, started_at_ms,
                difficulty, autonomy_level, is_ai_active, is_practice, config_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (21, "PLATFORM_CONTROL", "u1", "active", 3, 1, 2, 100,
             "low", "L1", 1, 0, "{}"),
        )
        conn.commit()

    context = manager.resolve_questionnaire_task_context("u1", "PLATFORM_CONTROL")

    assert context["task_group_id"] == 21
    assert context["difficulty"] == "low"
    assert context["autonomy_level"] == "L1"
    assert context["repetition_current"] == 2
    assert context["repetition_total"] == 3


def test_questionnaire_uses_user_difficulty_and_autonomy_task_group(tmp_path):
    db_path = tmp_path / "questionnaire-business-key.db"
    manager = make_sync_database_manager(db_path)
    manager.initialize_database()
    with manager.get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO task_groups (
                group_id, task_type, user_id, status, expected_task_count,
                completed_task_count, current_task_seq, started_at_ms,
                completed_at_ms, difficulty, autonomy_level, is_ai_active,
                is_practice, config_json
            ) VALUES (?, ?, ?, 'completed', 3, 3, 3, ?, ?, ?, ?, 1, 0, '{}')
            """,
            [
                (31, "RADAR_TARGETING", "u1", 100, 200, "low", "L1"),
                (32, "RADAR_TARGETING", "u1", 300, 400, "high", "L3"),
                (33, "RADAR_TARGETING", "u2", 500, 600, "high", "L3"),
            ],
        )
        conn.commit()

    manager.record_questionnaire({
        "userId": "u1",
        "taskType": "RADAR_TARGETING",
        "taskId": 999999,
        "taskInfo": {"difficulty": "high", "autonomyLevel": "L3"},
        "answers": {"1": 5},
    })

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT task_group_id, difficulty, autonomy_level FROM questionnaire_responses"
        ).fetchone()
    assert row == (32, "high", "L3")


def test_platform_and_weapon_questionnaires_without_config_use_latest_matching_group(tmp_path):
    db_path = tmp_path / "questionnaire-latest-group.db"
    manager = make_sync_database_manager(db_path)
    manager.initialize_database()
    with manager.get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO task_groups (
                group_id, task_type, user_id, status, expected_task_count,
                completed_task_count, current_task_seq, started_at_ms,
                completed_at_ms, difficulty, autonomy_level, is_ai_active,
                is_practice, config_json
            ) VALUES (?, ?, ?, 'completed', 1, 1, 1, ?, ?, ?, ?, 1, 0, '{}')
            """,
            [
                (41, "PLATFORM_CONTROL", "u1", 100, 200, "low", "L1"),
                (42, "PLATFORM_CONTROL", "u1", 300, 400, "high", "L3"),
                (43, "PLATFORM_CONTROL", "u2", 500, 600, "medium", "L2"),
                (44, "WEAPON_LAUNCH", "u1", 700, 800, "medium", "L2"),
            ],
        )
        conn.commit()

    platform = manager.resolve_questionnaire_task_context("u1", "PLATFORM_CONTROL")
    weapon = manager.resolve_questionnaire_task_context("u1", "WEAPON_FIRING")

    assert platform["task_group_id"] == 42
    assert platform["difficulty"] == "high"
    assert platform["autonomy_level"] == "L3"
    assert weapon["task_group_id"] == 44
    assert weapon["difficulty"] == "medium"
    assert weapon["autonomy_level"] == "L2"


def test_find_active_task_group_uses_same_progress_key_only(tmp_path):
    db_path = tmp_path / "active-task-group.db"
    manager = make_sync_database_manager(db_path)
    manager.initialize_database()
    with manager.get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO task_groups (
                group_id, task_type, user_id, status, expected_task_count,
                completed_task_count, current_task_seq, started_at_ms,
                difficulty, autonomy_level, is_ai_active, is_practice,
                progress_key, config_json
            ) VALUES (?, 'RADAR_TARGETING', 'u1', ?, 2, 0, 0, ?, 'low', 'L1', 1, 0, ?, '{}')
            """,
            [
                (51, "completed", 100, "RADAR_TARGETING::1-L1-low"),
                (52, "active", 200, "RADAR_TARGETING::1-L1-low"),
                (53, "active", 300, "RADAR_TARGETING::2-L1-low"),
            ],
        )
        conn.commit()

    group = manager.find_active_task_group(
        user_id="u1",
        task_type="RADAR_TARGETING",
        progress_key="RADAR_TARGETING::1-L1-low",
    )

    assert group is not None
    assert group["group_id"] == 52


def test_retry_settings_keep_old_rows_and_resolve_latest_task_id(tmp_path):
    db_path = tmp_path / "retry-settings.db"
    manager = make_sync_database_manager(db_path)
    manager._task_settings_lock = threading.Lock()
    manager.initialize_database()
    scenario = {
        "difficulty_name": "low",
        "difficulty_config": {"target_count": 3},
        "repetition_info": {"current": 1},
        "is_ai_active": True,
        "ai_level_name": "L2",
        "ai_level_config": {"accuracy": 0.8},
        "audio_enabled": False,
    }
    manager.record_retry_task_settings(
        101, scenario, "u1", "AI", False, "RADAR_TARGETING", ""
    )
    manager.record_retry_task_settings(
        102, scenario, "u1", "AI", False, "RADAR_TARGETING", ""
    )

    assert manager.find_existing_task_setting_id(
        scenario, "u1", "AI", "RADAR_TARGETING", ""
    ) == 102
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT task_id FROM task_settings ORDER BY id"
        ).fetchall()
        conn.executemany(
            """
            INSERT INTO task_runs (task_id, task_type, user_id, status, started_at_ms)
            VALUES (?, 'RADAR_TARGETING', 'u1', ?, ?)
            """,
            [(101, "retried", 100), (102, "active", 200)],
        )
        conn.commit()
    assert rows == [(101,), (102,)]
    active_run = manager.find_active_task_run("u1", "RADAR_TARGETING")
    assert active_run is not None
    assert active_run["task_id"] == 102
    assert active_run["status"] == "active"
