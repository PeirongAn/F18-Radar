import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tobii import gaze_service as gaze_service_module
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

        task_dir = Path(tmp) / "raw" / "S002" / "active-task"
        assert task_dir.exists()
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


def test_raw_gaze_frame_keeps_tobii_per_eye_measurements():
    with tempfile.TemporaryDirectory() as tmp:
        svc = GazeService(data_dir=tmp)
        try:
            svc.start_task(
                bbox=[], screen_size=None, task_id="eye-data-task", user_id="S008",
                system_time=1_700_000_000_000_000,
            )
            svc._gaze_data_callback({
                "device_time_stamp": 123456,
                "system_time_stamp": 123999,
                "left_gaze_point_validity": 1,
                "right_gaze_point_validity": 0,
                "left_gaze_point_on_display_area": (0.4, 0.5),
                "right_gaze_point_on_display_area": (float("nan"), float("nan")),
                "left_gaze_point_in_user_coordinate_system": (10.0, 20.0, 30.0),
                "right_gaze_point_in_user_coordinate_system": (11.0, 21.0, 31.0),
                "left_pupil_diameter": 3.2,
                "right_pupil_diameter": float("nan"),
                "left_pupil_validity": 1,
                "right_pupil_validity": 0,
                "left_gaze_origin_in_user_coordinate_system": (1.0, 2.0, 600.0),
                "right_gaze_origin_in_user_coordinate_system": (2.0, 2.0, 600.0),
                "left_gaze_origin_in_trackbox_coordinate_system": (0.4, 0.5, 0.6),
                "right_gaze_origin_in_trackbox_coordinate_system": (0.6, 0.5, 0.6),
                "left_gaze_origin_validity": 1,
                "right_gaze_origin_validity": 1,
            })
            svc.stop_task(task_id="eye-data-task", system_time=1_700_000_000_500_000)
        finally:
            svc.shutdown()

        raw_file = Path(tmp) / "raw" / "S008" / "eye-data-task" / "raw_gaze.jsonl"
        frame = json.loads(raw_file.read_text(encoding="utf-8").strip())
        assert frame["device_ts_us"] == 123456
        assert frame["sdk_system_ts_us"] == 123999
        assert frame["left_eye"]["pupil_diameter_mm"] == 3.2
        assert frame["left_eye"]["origin_user_mm"] == [1.0, 2.0, 600.0]
        assert frame["left_eye"]["gaze_valid"] is True
        assert frame["right_eye"]["pupil_diameter_mm"] is None
        assert frame["right_eye"]["gaze_display"] == [None, None]
        assert frame["right_eye"]["pupil_valid"] is False

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


def test_continuous_invalid_gaze_triggers_single_feedback_until_recovered():
    with tempfile.TemporaryDirectory() as tmp:
        svc = GazeService(data_dir=tmp)
        try:
            svc.start_task(
                bbox=[],
                screen_size=(100, 100),
                task_id="single-feedback-task",
                user_id="S011",
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
            for _ in range(450):
                svc._gaze_data_callback({
                    "left_gaze_point_validity": 0,
                    "right_gaze_point_validity": 0,
                    "left_gaze_point_on_display_area": (0.42, 0.31),
                    "right_gaze_point_on_display_area": (0.42, 0.31),
                })
        finally:
            svc.shutdown()

        conn = sqlite3.connect(Path(tmp) / "gaze_records.db")
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM gaze_feedback_events WHERE task_id = ?",
                ("single-feedback-task",),
            ).fetchone()[0]
        finally:
            conn.close()

        assert count == 1


def test_feedback_can_trigger_again_after_gaze_returns_to_target():
    with tempfile.TemporaryDirectory() as tmp:
        svc = GazeService(data_dir=tmp)
        try:
            svc.start_task(
                bbox=[],
                screen_size=(100, 100),
                task_id="recovered-feedback-task",
                user_id="S012",
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
            invalid_frame = {
                "left_gaze_point_validity": 0,
                "right_gaze_point_validity": 0,
                "left_gaze_point_on_display_area": (0.42, 0.31),
                "right_gaze_point_on_display_area": (0.42, 0.31),
            }
            hit_frame = {
                "left_gaze_point_validity": 1,
                "right_gaze_point_validity": 1,
                "left_gaze_point_on_display_area": (0.42, 0.31),
                "right_gaze_point_on_display_area": (0.42, 0.31),
            }
            for _ in range(250):
                svc._gaze_data_callback(invalid_frame)
            svc._gaze_data_callback(hit_frame)
            for _ in range(250):
                svc._gaze_data_callback(invalid_frame)
        finally:
            svc.shutdown()

        conn = sqlite3.connect(Path(tmp) / "gaze_records.db")
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM gaze_feedback_events WHERE task_id = ?",
                ("recovered-feedback-task",),
            ).fetchone()[0]
        finally:
            conn.close()

        assert count == 2


def test_continuous_invalid_gaze_can_trigger_again_after_cooldown(monkeypatch):
    fake_now = [1_000.0]
    monkeypatch.setattr(gaze_service_module.time, "time", lambda: fake_now[0])

    with tempfile.TemporaryDirectory() as tmp:
        svc = GazeService(data_dir=tmp)
        try:
            svc.start_task(
                bbox=[],
                screen_size=(100, 100),
                task_id="cooldown-feedback-task",
                user_id="S013",
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
            invalid_frame = {
                "left_gaze_point_validity": 0,
                "right_gaze_point_validity": 0,
                "left_gaze_point_on_display_area": (0.42, 0.31),
                "right_gaze_point_on_display_area": (0.42, 0.31),
            }
            for _ in range(250):
                svc._gaze_data_callback(invalid_frame)
            fake_now[0] += 2.0
            for _ in range(250):
                svc._gaze_data_callback(invalid_frame)
            fake_now[0] += 1.1
            svc._gaze_data_callback(invalid_frame)
        finally:
            svc.shutdown()

        conn = sqlite3.connect(Path(tmp) / "gaze_records.db")
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM gaze_feedback_events WHERE task_id = ?",
                ("cooldown-feedback-task",),
            ).fetchone()[0]
        finally:
            conn.close()

        assert count == 2


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


def test_analysis_aoi_snapshots_are_versioned_and_do_not_change_attention_hits():
    with tempfile.TemporaryDirectory() as tmp:
        svc = GazeService(data_dir=tmp)
        try:
            svc.start_task(
                bbox=[],
                screen_size=(100, 100),
                task_id="aoi-task",
                user_id="S014",
                system_time=1_700_000_000_000_000,
                regions=[{
                    "id": "antenna_prompt",
                    "shape": "rect",
                    "left": 0.4,
                    "top": 0.3,
                    "right": 0.5,
                    "bottom": 0.4,
                }],
                coordinate_space="display_area_normalized",
            )
            payload = dict(
                task_id="aoi-task",
                trial_id="aoi-task",
                task_group_id="group-1",
                task_type="RADAR_TARGETING",
                client_snapshot_id="client-1",
                client_captured_at_ms=1_700_000_000_000,
                change_reasons=["trial_started"],
                coordinate_space="display_area_normalized",
                display={
                    "alignment_valid": True,
                    "screen_width_css_px": 100,
                    "screen_height_css_px": 100,
                },
                regions=[
                    {
                        "id": "left_candidate_list",
                        "shape": "rect",
                        "visible": True,
                        "left": 0.3,
                        "top": 0.2,
                        "right": 0.6,
                        "bottom": 0.6,
                        "binding": {"candidate_ids": ["A"]},
                    },
                    {
                        "id": "left_ai_target",
                        "shape": "rect",
                        "visible": True,
                        "left": 0.4,
                        "top": 0.3,
                        "right": 0.5,
                        "bottom": 0.4,
                        "binding": {"target_id": "A"},
                    },
                    {
                        "id": "right_ai_history_accuracy",
                        "shape": "rect",
                        "visible": True,
                        "left": 0.4,
                        "top": 0.3,
                        "right": 0.5,
                        "bottom": 0.4,
                        "binding": {"metric": "ai_history_accuracy"},
                    },
                ],
            )
            first = svc.set_analysis_aoi_snapshot(**payload)
            duplicate = svc.set_analysis_aoi_snapshot(**payload)
            assert first["changed"] is True
            assert first["revision"] == 1
            assert duplicate["changed"] is False
            assert duplicate["revision"] == 1

            svc._gaze_data_callback({
                "left_gaze_point_validity": 1,
                "right_gaze_point_validity": 1,
                "left_gaze_point_on_display_area": (0.42, 0.31),
                "right_gaze_point_on_display_area": (0.42, 0.31),
            })

            payload["regions"][1]["left"] = 0.7
            payload["regions"][1]["right"] = 0.8
            payload["change_reasons"] = ["geometry_changed"]
            second = svc.set_analysis_aoi_snapshot(**payload)
            assert second["changed"] is True
            assert second["revision"] == 2
            svc.stop_task(task_id="aoi-task", system_time=1_700_000_000_500_000)
        finally:
            svc.shutdown()

        raw_file = Path(tmp) / "raw" / "S014" / "aoi-task" / "raw_gaze.jsonl"
        frame = json.loads(raw_file.read_text(encoding="utf-8").strip())
        assert frame["hit"] is True
        assert frame["hits"] == ["antenna_prompt"]
        assert frame["aoi_revision"] == 1
        assert frame["aoi_hits"] == ["left_ai_target", "left_candidate_list", "right_ai_history_accuracy"]

        conn = sqlite3.connect(Path(tmp) / "gaze_records.db")
        try:
            rows = conn.execute(
                "SELECT revision, valid_from_us, valid_to_us, alignment_valid "
                "FROM gaze_aoi_snapshots WHERE task_id = ? ORDER BY revision",
                ("aoi-task",),
            ).fetchall()
        finally:
            conn.close()
        assert [row[0] for row in rows] == [1, 2]
        assert rows[0][2] == rows[1][1]
        assert rows[1][2] == 1_700_000_000_500_000
        assert [row[3] for row in rows] == [1, 1]


def test_invalid_aoi_alignment_records_revision_without_aoi_hits():
    with tempfile.TemporaryDirectory() as tmp:
        svc = GazeService(data_dir=tmp)
        try:
            svc.start_task(
                bbox=[], screen_size=None, task_id="invalid-aoi-task", user_id="S015",
                system_time=1_700_000_000_000_000,
            )
            result = svc.set_analysis_aoi_snapshot(
                task_id="invalid-aoi-task",
                trial_id="invalid-aoi-task",
                task_group_id=None,
                task_type="SA_THREAT_RESPONSE",
                client_snapshot_id="client-invalid",
                client_captured_at_ms=1_700_000_000_000,
                change_reasons=["fullscreen_changed"],
                coordinate_space="display_area_normalized",
                display={"alignment_valid": False},
                regions=[{
                    "id": "right_detail",
                    "shape": "rect",
                    "visible": True,
                    "left": 0.6,
                    "top": 0.2,
                    "right": 0.9,
                    "bottom": 0.6,
                }],
            )
            assert result["revision"] == 1
            svc._gaze_data_callback({
                "left_gaze_point_validity": 1,
                "right_gaze_point_validity": 1,
                "left_gaze_point_on_display_area": (0.7, 0.4),
                "right_gaze_point_on_display_area": (0.7, 0.4),
            })
            svc.stop_task(task_id="invalid-aoi-task", system_time=1_700_000_000_500_000)
        finally:
            svc.shutdown()

        raw_file = Path(tmp) / "raw" / "S015" / "invalid-aoi-task" / "raw_gaze.jsonl"
        frame = json.loads(raw_file.read_text(encoding="utf-8").strip())
        assert frame["aoi_revision"] == 1
        assert "aoi_hits" not in frame

def test_duplicate_start_preserves_analysis_aoi_revision():
    with tempfile.TemporaryDirectory() as tmp:
        svc = GazeService(data_dir=tmp)
        try:
            svc.start_task(
                bbox=[], screen_size=(100, 100), task_id="same-task", user_id="S016",
                system_time=1_700_000_000_000_000,
            )
            common = {
                "task_id": "same-task",
                "trial_id": "same-task",
                "task_group_id": "group-1",
                "task_type": "RADAR_TARGETING",
                "client_snapshot_id": "snapshot-1",
                "client_captured_at_ms": 1_700_000_000_000,
                "change_reasons": ["trial_started"],
                "coordinate_space": "display_area_normalized",
                "display": {"alignment_valid": True},
                "regions": [{
                    "id": "right_detail",
                    "shape": "rect",
                    "visible": True,
                    "left": 0.6,
                    "top": 0.2,
                    "right": 0.9,
                    "bottom": 0.6,
                    "binding": {"mode": "tdc_detail", "target_id": "target-1"},
                }],
            }
            first = svc.set_analysis_aoi_snapshot(**common)
            assert first["revision"] == 1

            repeated = svc.start_task(
                bbox=[], screen_size=(100, 100), task_id="same-task", user_id="S016",
                system_time=1_700_000_000_100_000,
            )
            assert repeated == "same-task"

            common["client_snapshot_id"] = "snapshot-2"
            common["change_reasons"] = ["binding_changed"]
            common["regions"][0]["binding"]["target_id"] = "target-2"
            second = svc.set_analysis_aoi_snapshot(**common)
            assert second["revision"] == 2
            svc.stop_task(task_id="same-task", system_time=1_700_000_000_500_000)
        finally:
            svc.shutdown()

        conn = sqlite3.connect(Path(tmp) / "gaze_records.db")
        try:
            revisions = conn.execute(
                "SELECT revision FROM gaze_aoi_snapshots WHERE task_id = ? ORDER BY revision",
                ("same-task",),
            ).fetchall()
            task_count = conn.execute(
                "SELECT COUNT(*) FROM gaze_tasks WHERE task_id = ?", ("same-task",)
            ).fetchone()[0]
        finally:
            conn.close()
        assert revisions == [(1,), (2,)]
        assert task_count == 1
