import json
import logging
import os
import sys
import threading

import pytest


sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
logging.raiseExceptions = False

from managers.database_manager import DatabaseManager


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
    """Build a DatabaseManager that writes synchronously into a temporary DB."""
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
    user_id="P001",
    task_type="PLATFORM_CONTROL",
    status="active",
    started_at_ms=1_781_523_456_000,
):
    with manager.get_connection() as connection:
        connection.execute(
            """
            INSERT INTO task_runs (
                task_id, group_id, task_seq, task_type, user_id, status,
                expected_subtasks, completed_subtasks, current_subtask_seq,
                started_at_ms, config_json
            ) VALUES (?, ?, ?, ?, ?, ?, 1, 0, 1, ?, ?)
            """,
            (
                task_id,
                900,
                1,
                task_type,
                user_id,
                status,
                started_at_ms,
                json.dumps(
                    {
                        "overall_task_id": 900,
                        "sub_task_seq": 1,
                    }
                ),
            ),
        )
        connection.commit()


def record_external_behavior(manager, payload):
    """Map the documented Web payload onto the existing user_operations API."""
    data = payload["data"]
    resolved = manager.find_active_task_run(data["PlayerID"], data["task_type"])
    if resolved is None:
        return None

    behavior_type = data["type"]
    manager.record_operation(
        {
            "task_id": resolved["task_id"],
            "operationType": behavior_type,
            "timestamp": data["timestamp"],
            "receive_timestamp": data["timestamp"] + 10,
            "isActive": behavior_type.endswith("_start"),
            "parameters": {
                "button": data.get("button"),
                "owner": data["owner"],
                "client_event_id": payload["client_event_id"],
                "schema_version": payload["schema_version"],
                "pose_data": data["pose_data"],
            },
            "user_id": data["PlayerID"],
            "event_owner": "manual" if data["owner"] == "User" else "AI",
        },
        is_practice=False,
    )
    return resolved["task_id"]


def behavior_payload(client_event_id="event-001"):
    return {
        "type": "external_behavior_record",
        "schema_version": "1.0",
        "client_event_id": client_event_id,
        "data": {
            "PlayerID": "P001",
            "task_type": "PLATFORM_CONTROL",
            "task_id": None,
            "button": "button4",
            "type": "y_axis_start",
            "timestamp": 1_781_523_456_789,
            "owner": "User",
            "pose_data": [
                {
                    "Side": "Our",
                    "ID": "101",
                    "timestamp": 1_781_523_456_789,
                    "posture": {
                        "Pitch": 5.2,
                        "Yaw": 180.0,
                        "Roll": -12.4,
                    },
                }
            ],
        },
    }


def test_null_external_task_id_resolves_unique_active_task_and_records_behavior(tmp_path):
    manager = make_sync_database_manager(tmp_path / "behavior.db")
    insert_task_run(manager, task_id=101)

    resolved_task_id = record_external_behavior(manager, behavior_payload())

    assert resolved_task_id == 101
    with manager.get_connection() as connection:
        row = connection.execute(
            """
            SELECT task_id, operation_type, timestamp, receive_timestamp,
                   is_active, parameters, user_id, event_owner
            FROM user_operations
            """
        ).fetchone()

    assert row is not None
    assert row[0] == 101
    assert row[1] == "y_axis_start"
    assert row[2] == 1_781_523_456_789
    assert row[3] == 1_781_523_456_799
    assert row[4] == 1
    assert row[6] == "P001"
    assert row[7] == "manual"
    parameters = json.loads(row[5])
    assert parameters["button"] == "button4"
    assert parameters["client_event_id"] == "event-001"
    assert parameters["pose_data"][0]["posture"] == {
        "Pitch": 5.2,
        "Yaw": 180.0,
        "Roll": -12.4,
    }


def test_null_external_task_id_does_not_cross_user_or_task_type(tmp_path):
    manager = make_sync_database_manager(tmp_path / "behavior.db")
    insert_task_run(
        manager,
        task_id=201,
        user_id="OTHER_USER",
        task_type="PLATFORM_CONTROL",
        started_at_ms=1_781_523_456_100,
    )
    insert_task_run(
        manager,
        task_id=202,
        user_id="P001",
        task_type="WEAPON_FIRING",
        started_at_ms=1_781_523_456_200,
    )
    insert_task_run(
        manager,
        task_id=203,
        user_id="P001",
        task_type="PLATFORM_CONTROL",
        started_at_ms=1_781_523_456_000,
    )

    resolved_task_id = record_external_behavior(manager, behavior_payload())

    assert resolved_task_id == 203


def test_missing_active_task_does_not_write_behavior(tmp_path):
    manager = make_sync_database_manager(tmp_path / "behavior.db")

    resolved_task_id = record_external_behavior(manager, behavior_payload())

    assert resolved_task_id is None
    with manager.get_connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM user_operations"
        ).fetchone()[0]
    assert count == 0


@pytest.mark.xfail(
    strict=False,
    reason=(
        "find_active_task_run currently selects the newest active row; "
        "the external behavior contract requires ambiguous matches to be rejected"
    ),
)
def test_multiple_active_tasks_are_rejected_as_ambiguous(tmp_path):
    manager = make_sync_database_manager(tmp_path / "behavior.db")
    insert_task_run(manager, task_id=301, started_at_ms=1_781_523_456_000)
    insert_task_run(manager, task_id=302, started_at_ms=1_781_523_456_100)

    resolved = manager.find_active_task_run("P001", "PLATFORM_CONTROL")

    assert resolved is None


@pytest.mark.xfail(
    strict=False,
    reason=(
        "user_operations has no unique client_event_id column or index, "
        "so replayed WebSocket events are not yet idempotent"
    ),
)
def test_duplicate_client_event_id_is_stored_only_once(tmp_path):
    manager = make_sync_database_manager(tmp_path / "behavior.db")
    insert_task_run(manager, task_id=401)
    payload = behavior_payload(client_event_id="same-event")

    record_external_behavior(manager, payload)
    record_external_behavior(manager, payload)

    with manager.get_connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM user_operations WHERE task_id = 401"
        ).fetchone()[0]
    assert count == 1


@pytest.mark.xfail(
    strict=False,
    reason=(
        "external_pose_records has been specified but is not created by "
        "DatabaseManager.initialize_database yet"
    ),
)
def test_pose_snapshot_table_exists(tmp_path):
    manager = make_sync_database_manager(tmp_path / "behavior.db")

    with manager.get_connection() as connection:
        row = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'external_pose_records'
            """
        ).fetchone()

    assert row is not None
