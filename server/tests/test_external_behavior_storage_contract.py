import json
import os
import sys
import threading

import pytest


sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from managers.database_manager import DatabaseManager
from network.external_behavior_storage import (
    ExternalBehaviorError,
    ExternalBehaviorStore,
)


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
    manager._operation_lock = threading.Lock()
    manager._pending_operation_keys = set()
    manager._task_settings_lock = threading.Lock()
    manager._pending_task_setting_keys = set()

    def execute_sync(sql, params):
        with manager.get_connection() as connection:
            connection.execute(sql, params)
            connection.commit()

    manager.execute_async = execute_sync
    manager.initialize_database()
    return manager


def insert_task_run(
    manager,
    *,
    task_id,
    group_id=900,
    user_id="P001",
    task_type="PLATFORM_CONTROL",
    status="active",
    started_at_ms=1_785_380_705_000,
):
    with manager.get_connection() as connection:
        connection.execute(
            """
            INSERT INTO task_runs (
                task_id, group_id, task_seq, task_type, user_id, status,
                expected_subtasks, completed_subtasks, current_subtask_seq,
                started_at_ms, config_json
            ) VALUES (?, ?, 1, ?, ?, ?, 1, 0, 1, ?, ?)
            """,
            (
                task_id,
                group_id,
                task_type,
                user_id,
                status,
                started_at_ms,
                json.dumps(
                    {
                        "overall_task_id": group_id,
                        "sub_task_seq": 1,
                    }
                ),
            ),
        )
        connection.commit()


def behavior_message(
    client_event_id="event-001",
    *,
    task_id=None,
    timestamp=1_785_380_705_879,
):
    data = {
        "PlayerID": "P001",
        "task_type": "PLATFORM_CONTROL",
        "task_id": task_id,
        "button": "button4",
        "type": "y_axis_start",
        "owner": "AI",
        "pose_data": [
            {
                "Side": "Our",
                "ID": "101",
                "timestamp": 1_785_380_705_879,
                "posture": {
                    "Pitch": 7.4261,
                    "Yaw": 120.1377,
                    "Roll": 78.825,
                },
            }
        ],
    }
    if timestamp is not None:
        data["timestamp"] = timestamp
    return {
        "type": "external_behavior_record",
        "schema_version": "1.0",
        "client_event_id": client_event_id,
        "data": data,
    }


def test_behavior_table_is_created(tmp_path):
    manager = make_sync_database_manager(tmp_path / "behavior.db")

    with manager.get_connection() as connection:
        row = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'external_behavior_records'
            """
        ).fetchone()

    assert row is not None


def test_null_task_id_resolves_unique_active_task_and_stores_behavior(tmp_path):
    manager = make_sync_database_manager(tmp_path / "behavior.db")
    insert_task_run(manager, task_id=101, group_id=90)
    store = ExternalBehaviorStore(manager)

    reply = store.write(behavior_message())

    assert reply["ok"] is True
    assert reply["resolved_task_id"] == 101
    assert reply["task_group_id"] == 90
    assert reply["behavior_type"] == "y_axis_start"
    assert reply["duplicate"] is False
    with manager.get_connection() as connection:
        row = connection.execute(
            """
            SELECT client_event_id, task_id, user_id, task_type, button,
                   behavior_type, owner, is_active, source_timestamp_ms,
                   received_at_ms, pose_data_json, schema_version
            FROM external_behavior_records
            """
        ).fetchone()
        operation_count = connection.execute(
            "SELECT COUNT(*) FROM user_operations"
        ).fetchone()[0]

    assert row[:9] == (
        "event-001",
        101,
        "P001",
        "PLATFORM_CONTROL",
        "button4",
        "y_axis_start",
        "AI",
        1,
        1_785_380_705_879,
    )
    assert row[9] > 0
    assert json.loads(row[10])[0]["posture"]["Yaw"] == 120.1377
    assert row[11] == "1.0"
    assert operation_count == 0


def test_external_source_timestamp_is_optional(tmp_path):
    manager = make_sync_database_manager(tmp_path / "behavior.db")
    insert_task_run(manager, task_id=101)
    store = ExternalBehaviorStore(manager)

    reply = store.write(behavior_message(timestamp=None))

    assert reply["ok"] is True
    with manager.get_connection() as connection:
        row = connection.execute(
            """
            SELECT source_timestamp_ms, received_at_ms
            FROM external_behavior_records
            """
        ).fetchone()
    assert row[0] is None
    assert row[1] > 0


def test_duplicate_client_event_id_is_idempotent(tmp_path):
    manager = make_sync_database_manager(tmp_path / "behavior.db")
    insert_task_run(manager, task_id=101)
    store = ExternalBehaviorStore(manager)
    message = behavior_message()

    first = store.write(message)
    second = store.write(message)

    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert first["behavior_record_id"] == second["behavior_record_id"]
    with manager.get_connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM external_behavior_records"
        ).fetchone()[0]
    assert count == 1


def test_duplicate_is_returned_after_task_has_completed(tmp_path):
    manager = make_sync_database_manager(tmp_path / "behavior.db")
    insert_task_run(manager, task_id=101)
    store = ExternalBehaviorStore(manager)
    message = behavior_message()
    first = store.write(message)
    with manager.get_connection() as connection:
        connection.execute(
            """
            UPDATE task_runs
            SET status = 'completed', completed_at_ms = ?
            WHERE task_id = 101
            """,
            (1_785_380_706_000,),
        )
        connection.commit()

    second = store.write(message)

    assert second["ok"] is True
    assert second["duplicate"] is True
    assert second["behavior_record_id"] == first["behavior_record_id"]
    assert second["resolved_task_id"] == 101


def test_reused_client_event_id_with_different_payload_is_rejected(tmp_path):
    manager = make_sync_database_manager(tmp_path / "behavior.db")
    insert_task_run(manager, task_id=101)
    store = ExternalBehaviorStore(manager)
    store.write(behavior_message())
    changed = behavior_message()
    changed["data"]["type"] = "y_axis_end"

    with pytest.raises(ExternalBehaviorError) as exc_info:
        store.write(changed)

    assert exc_info.value.code == "CLIENT_EVENT_ID_CONFLICT"


def test_multiple_active_tasks_are_rejected_as_ambiguous(tmp_path):
    manager = make_sync_database_manager(tmp_path / "behavior.db")
    insert_task_run(manager, task_id=101, started_at_ms=1_785_380_705_000)
    insert_task_run(manager, task_id=102, started_at_ms=1_785_380_705_100)
    store = ExternalBehaviorStore(manager)

    with pytest.raises(ExternalBehaviorError) as exc_info:
        store.write(behavior_message())

    assert exc_info.value.code == "ACTIVE_TASK_AMBIGUOUS"
    with manager.get_connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM external_behavior_records"
        ).fetchone()[0]
    assert count == 0


def test_explicit_task_id_must_match_active_context(tmp_path):
    manager = make_sync_database_manager(tmp_path / "behavior.db")
    insert_task_run(manager, task_id=101, user_id="OTHER")
    store = ExternalBehaviorStore(manager)

    with pytest.raises(ExternalBehaviorError) as exc_info:
        store.write(behavior_message(task_id=101))

    assert exc_info.value.code == "TASK_ID_MISMATCH"


@pytest.mark.parametrize(
    ("task_type", "status"),
    [
        ("WEAPON_FIRING", "active"),
        ("PLATFORM_CONTROL", "completed"),
    ],
)
def test_explicit_task_id_rejects_wrong_task_type_or_inactive_task(
    tmp_path,
    task_type,
    status,
):
    manager = make_sync_database_manager(tmp_path / "behavior.db")
    insert_task_run(
        manager,
        task_id=101,
        task_type=task_type,
        status=status,
    )
    store = ExternalBehaviorStore(manager)

    with pytest.raises(ExternalBehaviorError) as exc_info:
        store.write(behavior_message(task_id=101))

    assert exc_info.value.code == "TASK_ID_MISMATCH"
    with manager.get_connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM external_behavior_records"
        ).fetchone()[0]
    assert count == 0


def test_legacy_behavior_type_is_normalized(tmp_path):
    manager = make_sync_database_manager(tmp_path / "behavior.db")
    insert_task_run(manager, task_id=101)
    store = ExternalBehaviorStore(manager)
    message = behavior_message()
    message["data"]["type"] = "SwitchMode"
    message["data"]["button"] = "button5"

    reply = store.write(message)

    assert reply["behavior_type"] == "switch_mode"
    with manager.get_connection() as connection:
        row = connection.execute(
            """
            SELECT behavior_type, is_active
            FROM external_behavior_records
            """
        ).fetchone()
    assert row == ("switch_mode", 1)
