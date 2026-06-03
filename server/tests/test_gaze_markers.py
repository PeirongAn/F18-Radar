import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tobii.gaze_service import GazeService


def _rows(db_path: Path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT marker_id, task_id, user_id, name, payload_json FROM gaze_markers ORDER BY id"
        ).fetchall()
    finally:
        conn.close()


def _task_rows(db_path: Path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT task_id, end_time_us, end_trigger, status, total_frames, valid_frames, in_region_frames "
            "FROM gaze_tasks ORDER BY id"
        ).fetchall()
    finally:
        conn.close()


def test_marker_without_active_task_writes_gaze_markers_table():
    with tempfile.TemporaryDirectory() as tmp:
        svc = GazeService(data_dir=tmp)
        try:
            marker = svc.record_marker(
                "manual_marker",
                {"note": "no active task"},
                task_id="external-task",
                user_id="S001",
                system_time=1_700_000_000_000_000,
            )
        finally:
            svc.shutdown()

        rows = _rows(Path(tmp) / "gaze_records.db")
        assert len(rows) == 1
        assert rows[0][0] == marker["marker_id"]
        assert rows[0][1] == "external-task"
        assert rows[0][2] == "S001"
        assert rows[0][3] == "manual_marker"
        assert json.loads(rows[0][4]) == {"note": "no active task"}
        assert not list(Path(tmp).glob("users/**/markers.jsonl"))


def test_marker_with_active_task_writes_db_only():
    with tempfile.TemporaryDirectory() as tmp:
        svc = GazeService(data_dir=tmp)
        try:
            task_id = svc.start_task(
                bbox=[],
                screen_size=None,
                task_id="active-task",
                user_id="S002",
                system_time=1_700_000_000_000_000,
            )
            marker = svc.record_marker(
                "fixation_check",
                {
                    "target": "panel-a",
                    "task_id": task_id,
                    "user_id": "S002",
                    "event_type": "sub_start",
                    "gaze_task_id": task_id,
                    "timestamp": 1_700_000_000_100_000,
                },
                task_id=task_id,
                system_time=1_700_000_000_100_000,
            )
        finally:
            svc.shutdown()

        rows = _rows(Path(tmp) / "gaze_records.db")
        assert len(rows) == 1
        assert rows[0][1] == "active-task"
        assert rows[0][2] == "S002"
        assert json.loads(rows[0][4]) == {"target": "panel-a"}
        assert marker["payload"] == {"target": "panel-a"}

        task_dir = next(Path(tmp).glob("users/S002/**/active-task"))
        assert not (task_dir / "markers.jsonl").exists()


def test_marker_task_id_mismatch_raises_and_does_not_write_marker_file():
    with tempfile.TemporaryDirectory() as tmp:
        svc = GazeService(data_dir=tmp)
        try:
            svc.start_task(
                bbox=[],
                screen_size=None,
                task_id="active-task",
                user_id="S003",
                system_time=1_700_000_000_000_000,
            )
            try:
                svc.record_marker("bad_marker", task_id="other-task")
                raised = False
            except ValueError as exc:
                raised = True
                assert "task_id mismatch" in str(exc)
        finally:
            svc.shutdown()

        assert raised is True
        rows = _rows(Path(tmp) / "gaze_records.db")
        assert rows == []
        assert not list(Path(tmp).glob("users/S003/**/active-task/markers.jsonl"))


def test_start_task_auto_closes_previous_task_in_db_without_summary_file():
    with tempfile.TemporaryDirectory() as tmp:
        svc = GazeService(data_dir=tmp)
        try:
            svc.start_task(
                bbox=[],
                screen_size=None,
                task_id="old-task",
                user_id="S004",
                system_time=1_700_000_000_000_000,
            )
            svc.start_task(
                bbox=[],
                screen_size=None,
                task_id="new-task",
                user_id="S004",
                system_time=1_700_000_000_500_000,
            )
            svc.stop_task(
                task_id="new-task",
                system_time=1_700_000_001_000_000,
            )
        finally:
            svc.shutdown()

        assert not list(Path(tmp).glob("raw/S004/**/summary.json"))
        rows = _task_rows(Path(tmp) / "gaze_records.db")
        assert rows[0][:4] == (
            "old-task",
            1_700_000_000_500_000,
            "auto_closed_by_new_task",
            "completed",
        )
        assert rows[1][:4] == (
            "new-task",
            1_700_000_001_000_000,
            "task_end",
            "completed",
        )


def test_stop_task_id_mismatch_does_not_close_active_task():
    with tempfile.TemporaryDirectory() as tmp:
        svc = GazeService(data_dir=tmp)
        try:
            svc.start_task(
                bbox=[],
                screen_size=None,
                task_id="active-task",
                user_id="S005",
                system_time=1_700_000_000_000_000,
            )
            try:
                svc.stop_task(
                    task_id="other-task",
                    system_time=1_700_000_000_500_000,
                )
                raised = False
            except ValueError as exc:
                raised = True
                assert "stop task_id mismatch" in str(exc)

            svc.stop_task(
                task_id="active-task",
                system_time=1_700_000_001_000_000,
            )
        finally:
            svc.shutdown()

        assert raised is True
        assert not list(Path(tmp).glob("raw/S005/**/other-task/summary.json"))
        assert not list(Path(tmp).glob("raw/S005/**/active-task/summary.json"))
        rows = _task_rows(Path(tmp) / "gaze_records.db")
        assert rows == [
            (
                "active-task",
                1_700_000_001_000_000,
                "task_end",
                "completed",
                0,
                0,
                0,
            )
        ]


def test_raw_gaze_frame_uses_slim_format_without_task_envelope():
    with tempfile.TemporaryDirectory() as tmp:
        svc = GazeService(data_dir=tmp)
        try:
            svc.start_task(
                bbox=[],
                screen_size=None,
                task_id="raw-task",
                user_id="S006",
                system_time=1_700_000_000_000_000,
            )
            svc._gaze_data_callback({
                "left_gaze_point_validity": 1,
                "right_gaze_point_validity": 1,
                "left_gaze_point_on_display_area": (0.736, 0.951),
                "right_gaze_point_on_display_area": (0.736, 0.951),
            })
            svc._gaze_data_callback({
                "left_gaze_point_validity": 0,
                "right_gaze_point_validity": 0,
            })
            svc.stop_task(task_id="raw-task", system_time=1_700_000_000_500_000)
        finally:
            svc.shutdown()

        raw_file = Path(tmp) / "raw" / "S006" / "raw-task" / "raw_gaze.jsonl"
        assert raw_file.exists()
        frames = [
            json.loads(line)
            for line in raw_file.read_text(encoding="utf-8").splitlines()
        ]
        assert len(frames) == 2
        assert frames[0]["gaze"] == [0.736, 0.951]
        assert frames[0]["hit"] is False
        assert frames[1]["gaze"] is None
        assert frames[1]["hit"] is False
        assert "hits" not in frames[0]
        assert "task_id" not in frames[0]
        assert "user_id" not in frames[0]
        assert "valid" not in frames[0]
        assert "in_region" not in frames[0]
        assert "region_hits" not in frames[0]

        rows = _task_rows(Path(tmp) / "gaze_records.db")
        assert rows[0][4:] == (2, 1, 0)


def test_raw_gaze_frame_writes_hits_only_when_region_matches():
    with tempfile.TemporaryDirectory() as tmp:
        svc = GazeService(data_dir=tmp)
        try:
            svc.start_task(
                bbox=[],
                screen_size=(100, 100),
                task_id="hit-task",
                user_id="S007",
                system_time=1_700_000_000_000_000,
                regions=[
                    {
                        "id": "antenna_prompt",
                        "shape": "rect",
                        "left": 0.4,
                        "top": 0.3,
                        "right": 0.5,
                        "bottom": 0.4,
                    }
                ],
                coordinate_space="display_area_normalized",
            )
            svc._gaze_data_callback({
                "left_gaze_point_validity": 1,
                "right_gaze_point_validity": 1,
                "left_gaze_point_on_display_area": (0.42, 0.31),
                "right_gaze_point_on_display_area": (0.42, 0.31),
            })
            svc.stop_task(task_id="hit-task", system_time=1_700_000_000_500_000)
        finally:
            svc.shutdown()

        raw_file = Path(tmp) / "raw" / "S007" / "hit-task" / "raw_gaze.jsonl"
        assert raw_file.exists()
        frame = json.loads(raw_file.read_text(encoding="utf-8").strip())
        assert frame["gaze"] == [0.42, 0.31]
        assert frame["hit"] is True
        assert frame["hits"] == ["antenna_prompt"]

        rows = _task_rows(Path(tmp) / "gaze_records.db")
        assert rows[0][4:] == (1, 1, 1)

def test_empty_attention_region_does_not_trigger_feedback():
    with tempfile.TemporaryDirectory() as tmp:
        svc = GazeService(data_dir=tmp)
        try:
            svc.start_task(
                bbox=[],
                screen_size=None,
                task_id="empty-region-task",
                user_id="S010",
                system_time=1_700_000_000_000_000,
            )
            for _ in range(250):
                svc._gaze_data_callback({
                    "left_gaze_point_validity": 1,
                    "right_gaze_point_validity": 1,
                    "left_gaze_point_on_display_area": (0.736, 0.951),
                    "right_gaze_point_on_display_area": (0.736, 0.951),
                })
        finally:
            svc.shutdown()

        conn = sqlite3.connect(Path(tmp) / "gaze_records.db")
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM gaze_feedback_events WHERE task_id = ?",
                ("empty-region-task",),
            ).fetchone()[0]
        finally:
            conn.close()

        assert count == 0


def test_targets_store_normalized_region_without_raw_bbox_json():
    with tempfile.TemporaryDirectory() as tmp:
        svc = GazeService(data_dir=tmp)
        try:
            svc.start_task(
                bbox=[[10, 20, 30, 40]],
                screen_size=(100, 100),
                task_id="target-task",
                user_id="S008",
                system_time=1_700_000_000_000_000,
            )
        finally:
            svc.shutdown()

        conn = sqlite3.connect(Path(tmp) / "gaze_records.db")
        try:
            row = conn.execute(
                "SELECT bbox_json, normalized_bbox_json, screen_width, screen_height "
                "FROM gaze_targets WHERE task_id = ?",
                ("target-task",),
            ).fetchone()
        finally:
            conn.close()

        assert row[0] is None
        assert json.loads(row[1]) == [
            {
                "shape": "rect",
                "left": 0.1,
                "top": 0.2,
                "right": 0.3,
                "bottom": 0.4,
            }
        ]
        assert row[2:] == (100, 100)


def test_feedback_payload_removes_duplicate_envelope_fields():
    with tempfile.TemporaryDirectory() as tmp:
        svc = GazeService(data_dir=tmp)
        try:
            svc.start_task(
                bbox=[],
                screen_size=None,
                task_id="feedback-task",
                user_id="S009",
                system_time=1_700_000_000_000_000,
            )
            svc._push_attention_feedback("feedback-task", 200)
        finally:
            svc.shutdown()

        conn = sqlite3.connect(Path(tmp) / "gaze_records.db")
        try:
            row = conn.execute(
                "SELECT reason, consecutive_false_count, threshold, payload_json "
                "FROM gaze_feedback_events WHERE task_id = ?",
                ("feedback-task",),
            ).fetchone()
        finally:
            conn.close()

        payload = json.loads(row[3])
        assert row[:3] == ("consecutive_not_in_target", 200, 200)
        assert payload["action"] == "flash_mode"
        assert payload["should_flash"] is True
        assert "task_id" not in payload
        assert "reason" not in payload
        assert "consecutive_false_count" not in payload
        assert "threshold" not in payload
