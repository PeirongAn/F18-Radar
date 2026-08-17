import os
import sys
import sqlite3
import json
import logging
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
logging.raiseExceptions = False

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
    def debug(self, *args, **kwargs):
        pass

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


def test_task_setting_key_includes_control_mode():
    manager = object.__new__(DatabaseManager)
    scenario = {
        "difficulty_name": "low",
        "repetition_info": {"current": 1},
        "is_ai_active": True,
        "ai_level_name": "L2",
        "audio_enabled": True,
    }

    mode_one_key = DatabaseManager.build_task_setting_key(
        manager,
        {**scenario, "control_mode": "1"},
        "user-a",
        "AI",
        "RADAR_TARGETING",
        "normal",
    )
    mode_two_key = DatabaseManager.build_task_setting_key(
        manager,
        {**scenario, "control_mode": "2"},
        "user-a",
        "AI",
        "RADAR_TARGETING",
        "normal",
    )

    assert mode_one_key != mode_two_key
    assert mode_one_key[3] == "1"
    assert mode_two_key[3] == "2"


def test_task_setting_lookup_does_not_reuse_mode_one_for_mode_two(tmp_path):
    db_path = tmp_path / "task-setting-control-mode.db"
    manager = make_sync_database_manager(db_path)
    manager.initialize_database()
    with manager.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO task_settings (
                task_id, user_id, task_type, event_owner, control_mode,
                repetition_count, is_ai_active, difficulty_config,
                audio_enabled, ai_level_name, difficulty_name, trust_state
            ) VALUES (101, 'user-a', 'RADAR_TARGETING', 'AI', '1', 1, 1, '{}', 1, 'L2', 'low', 'normal')
            """
        )
        conn.commit()

    base_scenario = {
        "difficulty_name": "low",
        "difficulty_config": {},
        "repetition_info": {"current": 1},
        "is_ai_active": True,
        "ai_level_name": "L2",
        "audio_enabled": True,
    }

    assert manager.find_existing_task_setting_id(
        {**base_scenario, "control_mode": "1"},
        "user-a",
        "AI",
        "RADAR_TARGETING",
        "normal",
    ) == 101
    assert manager.find_existing_task_setting_id(
        {**base_scenario, "control_mode": "2"},
        "user-a",
        "AI",
        "RADAR_TARGETING",
        "normal",
    ) is None


def test_task_settings_migration_backfills_legacy_ai_as_mode_one(tmp_path):
    db_path = tmp_path / "legacy-task-settings.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE task_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL UNIQUE,
                user_id TEXT,
                task_type TEXT,
                event_owner TEXT,
                execution_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                repetition_count INTEGER NOT NULL,
                is_ai_active BOOLEAN NOT NULL,
                ai_level_config TEXT,
                difficulty_config TEXT NOT NULL,
                audio_enabled BOOLEAN NOT NULL,
                ai_level_name TEXT,
                difficulty_name TEXT NOT NULL,
                trust_state TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO task_settings (
                task_id, user_id, task_type, event_owner, repetition_count,
                is_ai_active, difficulty_config, audio_enabled,
                ai_level_name, difficulty_name, trust_state
            ) VALUES (201, 'legacy-user', 'RADAR_TARGETING', 'AI', 1, 1, '{}', 1, 'L1', 'low', '')
            """
        )
        conn.commit()

    manager = make_sync_database_manager(db_path)
    manager.initialize_database()

    with manager.get_connection() as conn:
        control_mode = conn.execute(
            "SELECT control_mode FROM task_settings WHERE task_id = 201"
        ).fetchone()[0]

    assert control_mode == "1"


def test_formal_progress_isolated_between_control_modes(tmp_path, monkeypatch):
    db_path = tmp_path / "control-mode-progress.db"
    manager = make_sync_database_manager(db_path)
    manager.initialize_database()
    monkeypatch.setattr(task_manager, "db_manager", manager)
    config = {
        "current_level": "L1",
        "levels": [{"level": "L1", "name": "L1"}],
        "game_settings": {
            "practice_repetitions": 1,
            "max_repetitions": 3,
            "current_difficulty": "low",
            "difficulty_levels": {
                "low": {"name": "low", "threat_count": 1, "target_count": 1}
            },
            "audio_enabled": True,
        },
    }
    user_id = "formal-control-mode-user"
    mode_one_key = "RADAR_TARGETING::1-L1-low"
    mode_two_key = "RADAR_TARGETING::2-L1-low"

    mode_one = task_manager.TaskScenarioManager(
        config,
        user_id,
        "RADAR_TARGETING",
        is_practice=False,
        is_ai_active_request=True,
        progress_key=mode_one_key,
    )
    mode_one_scenario = mode_one.get_next_task_parameters(True)
    mode_one.repetition_counter = 2
    mode_one_scenario["repetition_info"]["current"] = 2
    mode_one._save_to_db()

    mode_two = task_manager.TaskScenarioManager(
        config,
        user_id,
        "RADAR_TARGETING",
        is_practice=False,
        is_ai_active_request=True,
        progress_key=mode_two_key,
    )
    mode_two_scenario = mode_two.get_next_task_parameters(True)

    assert mode_two_scenario["repetition_info"]["current"] == 1
    with manager.get_connection() as conn:
        progress_rows = conn.execute(
            "SELECT task_type, ai_repetition_counter FROM user_progress WHERE user_id = ? ORDER BY task_type",
            (user_id,),
        ).fetchall()
    assert progress_rows == [(mode_one_key, 2), (mode_two_key, 1)]


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
    assert "control_mode" in columns


def test_questionnaire_separates_manual_and_collaborative_task_groups(tmp_path):
    db_path = tmp_path / "questionnaire-control-mode.db"
    manager = make_sync_database_manager(db_path)
    manager.initialize_database()
    with manager.get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO task_groups (
                group_id, task_type, user_id, status, expected_task_count,
                completed_task_count, current_task_seq, started_at_ms,
                completed_at_ms, difficulty, autonomy_level, control_mode,
                is_ai_active, is_practice, config_json
            ) VALUES (?, 'RADAR_TARGETING', 'u1', 'completed', 2, 2, 2,
                      ?, ?, 'high', 'L2', ?, ?, 0, '{}')
            """,
            [
                (201, 100, 200, '0', 0),
                (202, 300, 400, '1', 1),
            ],
        )
        conn.commit()

    manager.record_questionnaire({
        "userId": "u1",
        "taskType": "RADAR_TARGETING",
        "taskInfo": {
            "difficulty": "high",
            "autonomyLevel": "L2",
            "controlMode": "0",
        },
        "answers": {"1": 4},
    })
    manager.record_questionnaire({
        "userId": "u1",
        "taskType": "RADAR_TARGETING",
        "taskGroupId": 202,
        "taskInfo": {
            "difficulty": "high",
            "autonomyLevel": "L2",
            "controlMode": "1",
        },
        "answers": {"1": 5},
    })

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT task_group_id, control_mode, is_ai_active
            FROM questionnaire_responses
            ORDER BY id
            """
        ).fetchall()
    assert rows == [(201, '0', 0), (202, '1', 1)]


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
    assert context["status"] == "active"
    assert manager.is_questionnaire_context_eligible(context) is False


def test_questionnaire_context_requires_completed_formal_task_group(tmp_path):
    db_path = tmp_path / "questionnaire-eligibility.db"
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}')
            """,
            [
                (71, "RADAR_TARGETING", "formal-active", "active", 20, 10, 10, 100, None, "high", "L2", 1, 0),
                (72, "RADAR_TARGETING", "formal-complete", "completed", 20, 20, 20, 200, 300, "high", "L2", 1, 0),
                (73, "WEAPON_FIRING", "practice-complete", "completed", 10, 10, 10, 400, 500, "high", "L2", 1, 1),
                (74, "WEAPON_FIRING", "formal-premature", "completed", 20, 10, 10, 600, 700, "high", "L2", 1, 0),
            ],
        )
        conn.commit()

    active = manager.resolve_questionnaire_task_context("formal-active", "RADAR_TARGETING")
    completed = manager.resolve_questionnaire_task_context(
        "formal-complete", "RADAR_TARGETING", submitted_task_group_id=72
    )
    practice = manager.resolve_questionnaire_task_context(
        "practice-complete", "WEAPON_FIRING", submitted_task_group_id=73
    )
    premature = manager.resolve_questionnaire_task_context(
        "formal-premature", "WEAPON_FIRING", submitted_task_group_id=74
    )

    assert manager.is_questionnaire_context_eligible(active) is False
    assert manager.is_questionnaire_context_eligible(completed) is True
    assert manager.is_questionnaire_context_eligible(practice) is False
    assert manager.is_questionnaire_context_eligible(premature) is False

    try:
        manager.record_questionnaire({
            "userId": "formal-active",
            "taskType": "RADAR_TARGETING",
            "taskGroupId": 71,
            "answers": {"1": 5},
        })
    except ValueError as error:
        assert "formal task group is completed" in str(error)
    else:
        raise AssertionError("active formal task unexpectedly accepted a questionnaire")


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


def test_external_questionnaire_context_keeps_control_modes_separate(tmp_path):
    db_path = tmp_path / "external-questionnaire-control-mode.db"
    manager = make_sync_database_manager(db_path)
    manager.initialize_database()
    with manager.get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO task_groups (
                group_id, task_type, user_id, status, expected_task_count,
                completed_task_count, current_task_seq, started_at_ms,
                completed_at_ms, control_mode, is_ai_active, is_practice, config_json
            ) VALUES (?, ?, 'u1', 'completed', 1, 1, 1, ?, ?, ?, ?, 0, '{}')
            """,
            [
                (51, "PLATFORM_CONTROL", 100, 200, "0", 0),
                (52, "PLATFORM_CONTROL", 300, 400, "1", 1),
                (53, "WEAPON_FIRING", 500, 600, "0", 0),
                (54, "WEAPON_FIRING", 700, 800, "2", 1),
            ],
        )
        conn.commit()

    platform_manual = manager.resolve_questionnaire_task_context(
        "u1", "PLATFORM_CONTROL", control_mode="0"
    )
    platform_ai = manager.resolve_questionnaire_task_context(
        "u1", "PLATFORM_CONTROL", control_mode="1"
    )
    weapon_manual = manager.resolve_questionnaire_task_context(
        "u1", "WEAPON_FIRING", control_mode="0"
    )
    weapon_ai = manager.resolve_questionnaire_task_context(
        "u1", "WEAPON_FIRING", control_mode="2"
    )

    assert (platform_manual["task_group_id"], platform_manual["control_mode"]) == (51, "0")
    assert (platform_ai["task_group_id"], platform_ai["control_mode"]) == (52, "1")
    assert (weapon_manual["task_group_id"], weapon_manual["control_mode"]) == (53, "0")
    assert (weapon_ai["task_group_id"], weapon_ai["control_mode"]) == (54, "2")


def test_external_questionnaire_context_falls_back_to_legacy_group_less_run(tmp_path):
    db_path = tmp_path / "external-questionnaire-legacy-run.db"
    manager = make_sync_database_manager(db_path)
    manager.initialize_database()
    config = {
        "task_category": "platform_control",
        "normalized": {
            "task_type": "PLATFORM_CONTROL",
            "platform_task_id": "u1",
            "default_control_mode": "0",
            "control_mode": "0",
            "include_ai": False,
            "is_practice": False,
        },
        "overall_task_id": None,
        "sub_task_seq": 1,
    }
    with manager.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO task_runs (
                task_id, group_id, task_seq, task_type, user_id, status,
                expected_subtasks, completed_subtasks, current_subtask_seq,
                started_at_ms, completed_at_ms, config_json, last_raw_message_json
            ) VALUES (61, NULL, 1, 'PLATFORM_CONTROL', 'u1', 'completed',
                      1, 1, 1, 100, 200, ?, '{}')
            """,
            (json.dumps(config),),
        )
        conn.commit()

    context = manager.resolve_questionnaire_task_context("u1", "PLATFORM_CONTROL")

    assert context["task_id"] == 61
    assert context["control_mode"] == "0"
    assert context["is_ai_active"] is False


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
