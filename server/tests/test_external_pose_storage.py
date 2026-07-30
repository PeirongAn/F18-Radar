import json
import os
import sys
import threading

import pytest


sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from managers.database_manager import DatabaseManager
from network.external_pose_storage import ExternalPoseError, ExternalPoseFileStore


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
    started_at_ms=1_785_378_328_000,
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


def pose_message(snapshot_id="snapshot-001", task_id=None):
    return {
        "type": "external_pose_record",
        "schema_version": "1.0",
        "client_snapshot_id": snapshot_id,
        "data": {
            "PlayerID": "P001",
            "task_type": "PLATFORM_CONTROL",
            "task_id": task_id,
            "captured_at": 1_785_378_328_152,
            "pose_data": [
                {
                    "Side": "Our",
                    "ID": "101",
                    "timestamp": 1_785_378_328_152,
                    "posture": {
                        "X": -9386.388,
                        "Y": 12711.761,
                        "Z": 50121.710,
                    },
                }
            ],
        },
    }


def test_null_task_id_writes_jsonl_and_sqlite_file_index(tmp_path):
    manager = make_sync_database_manager(tmp_path / "radar.db")
    insert_task_run(manager, task_id=101, group_id=90)
    store = ExternalPoseFileStore(
        manager,
        root_dir=tmp_path / "pose",
        sync_every=1,
    )

    reply = store.write(pose_message())
    store.close()

    assert reply == {
        "type": "external_pose_record_result",
        "ok": True,
        "client_snapshot_id": "snapshot-001",
        "pose_snapshot_id": "snapshot-001",
        "resolved_task_id": 101,
        "task_id": 101,
        "task_group_id": 90,
        "task_type": "PLATFORM_CONTROL",
        "pose_record_count": 1,
        "duplicate": False,
        "server_time_us": reply["server_time_us"],
    }
    path = tmp_path / "pose" / "P001" / "101" / "pose_samples.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["resolved_task_id"] == 101
    assert rows[0]["task_group_id"] == 90
    assert rows[0]["pose_data"][0]["posture"] == {
        "X": -9386.388,
        "Y": 12711.761,
        "Z": 50121.71,
    }

    with manager.get_connection() as connection:
        index_row = connection.execute(
            """
            SELECT task_id, task_group_id, user_id, task_type, file_path,
                   row_count, entity_record_count, first_pose_time_ms,
                   last_pose_time_ms, status
            FROM external_pose_files
            """
        ).fetchone()
    assert index_row[:4] == (101, 90, "P001", "PLATFORM_CONTROL")
    assert index_row[4] == str(path.resolve())
    assert index_row[5:] == (
        1,
        1,
        1_785_378_328_152,
        1_785_378_328_152,
        "closed",
    )


def test_duplicate_snapshot_id_is_acknowledged_without_second_file_row(tmp_path):
    manager = make_sync_database_manager(tmp_path / "radar.db")
    insert_task_run(manager, task_id=101)
    store = ExternalPoseFileStore(manager, root_dir=tmp_path / "pose", sync_every=1)

    first = store.write(pose_message())
    second = store.write(pose_message())
    store.close()

    assert first["duplicate"] is False
    assert second["duplicate"] is True
    path = tmp_path / "pose" / "P001" / "101" / "pose_samples.jsonl"
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_recent_snapshot_ids_are_restored_from_existing_file(tmp_path):
    manager = make_sync_database_manager(tmp_path / "radar.db")
    insert_task_run(manager, task_id=101)
    first_store = ExternalPoseFileStore(manager, root_dir=tmp_path / "pose", sync_every=1)
    first_store.write(pose_message())
    first_store.close()

    restarted_store = ExternalPoseFileStore(manager, root_dir=tmp_path / "pose", sync_every=1)
    reply = restarted_store.write(pose_message())
    restarted_store.close()

    assert reply["duplicate"] is True
    path = tmp_path / "pose" / "P001" / "101" / "pose_samples.jsonl"
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_multiple_active_database_candidates_are_rejected(tmp_path):
    manager = make_sync_database_manager(tmp_path / "radar.db")
    insert_task_run(manager, task_id=101, started_at_ms=1_785_378_328_000)
    insert_task_run(manager, task_id=102, started_at_ms=1_785_378_328_100)
    store = ExternalPoseFileStore(manager, root_dir=tmp_path / "pose")

    with pytest.raises(ExternalPoseError) as exc_info:
        store.write(pose_message())
    store.close()

    assert exc_info.value.code == "ACTIVE_TASK_AMBIGUOUS"
    assert not (tmp_path / "pose").exists()


def test_explicit_task_id_must_match_active_user_and_task_type(tmp_path):
    manager = make_sync_database_manager(tmp_path / "radar.db")
    insert_task_run(manager, task_id=101, user_id="OTHER")
    store = ExternalPoseFileStore(manager, root_dir=tmp_path / "pose")

    with pytest.raises(ExternalPoseError) as exc_info:
        store.write(pose_message(task_id=101))
    store.close()

    assert exc_info.value.code == "TASK_ID_MISMATCH"


@pytest.mark.parametrize(
    ("task_type", "status"),
    [
        ("WEAPON_FIRING", "active"),
        ("PLATFORM_CONTROL", "completed"),
    ],
)
def test_explicit_pose_task_id_rejects_wrong_type_or_inactive_task(
    tmp_path,
    task_type,
    status,
):
    manager = make_sync_database_manager(tmp_path / "radar.db")
    insert_task_run(
        manager,
        task_id=101,
        task_type=task_type,
        status=status,
    )
    store = ExternalPoseFileStore(manager, root_dir=tmp_path / "pose")

    with pytest.raises(ExternalPoseError) as exc_info:
        store.write(pose_message(task_id=101))
    store.close()

    assert exc_info.value.code == "TASK_ID_MISMATCH"
    assert not (tmp_path / "pose").exists()


def test_weapon_launch_alias_and_orientation_fields_are_accepted(tmp_path):
    manager = make_sync_database_manager(tmp_path / "radar.db")
    insert_task_run(
        manager,
        task_id=201,
        task_type="WEAPON_FIRING",
    )
    store = ExternalPoseFileStore(manager, root_dir=tmp_path / "pose", sync_every=1)
    message = pose_message()
    message["type"] = "external_pose_data"
    message["data"]["task_type"] = "WEAPON_LAUNCH"
    message["data"]["pose_data"][0]["posture"] = {
        "Pitch": 5.2,
        "Yaw": 180.0,
        "Roll": -12.4,
    }

    reply = store.write(message)
    store.close()

    assert reply["ok"] is True
    assert reply["task_type"] == "WEAPON_FIRING"
    assert reply["resolved_task_id"] == 201
