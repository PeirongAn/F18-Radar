import os
import sys
import logging
import json
import sqlite3
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
logging.raiseExceptions = False

from network import platform_task_bridge as bridge
from tobii.gaze_service import GazeService


class FakeDb:
    def __init__(self):
        self.runs = {}
        self.events = []
        self.results = []

    def find_active_task_run(self, user_id, task_type):
        active = [
            run for run in self.runs.values()
            if run["user_id"] == user_id and run["task_type"] == task_type and run["status"] != "completed"
        ]
        if not active:
            return None
        return sorted(active, key=lambda run: run["started_at_ms"], reverse=True)[0].copy()

    def find_recent_completed_task_run(self, user_id, task_type, since_ms=None):
        completed = [
            run for run in self.runs.values()
            if run["user_id"] == user_id
            and run["task_type"] == task_type
            and run["status"] == "completed"
            and run.get("completed_at_ms") is not None
            and (since_ms is None or run.get("completed_at_ms", 0) >= since_ms)
        ]
        if not completed:
            return None
        return sorted(completed, key=lambda run: run["completed_at_ms"], reverse=True)[0].copy()

    def create_task_run(self, **kwargs):
        self.runs[kwargs["task_id"]] = {
            **kwargs,
            "status": "active",
            "completed_subtasks": 0,
            "current_subtask_seq": 0,
        }

    def update_task_run_progress(self, task_id, **kwargs):
        run = self.runs[task_id]
        for key, value in kwargs.items():
            if value is not None:
                run[key] = value

    def record_task_event(self, **kwargs):
        self.events.append(kwargs)

    def record_subtask_result(self, **kwargs):
        self.results.append(kwargs)

    def record_external_task(self, **kwargs):
        raise AssertionError("platform_external_tasks should not be written")

    def record_external_task_result(self, **kwargs):
        raise AssertionError("platform_external_tasks should not be written")


class FakeGaze:
    def __init__(self):
        self.started = []
        self.markers = []
        self.stopped = []
        self.active_task_id = "active-gaze-task"

    def start_task(self, **kwargs):
        self.started.append(kwargs)
        self.active_task_id = str(kwargs.get("task_id") or self.active_task_id)
        return self.active_task_id

    def get_active_task_id(self):
        return self.active_task_id

    def record_marker(self, name, payload=None, task_id=None, user_id="", system_time=None):
        resolved_task_id = self.active_task_id if task_id is None else str(task_id)
        self.markers.append({
            "name": name,
            "payload": payload or {},
            "task_id": resolved_task_id,
            "user_id": user_id,
            "system_time": system_time,
        })
        return {"task_id": resolved_task_id}

    def stop_task(self, task_id=None, end_trigger="", system_time=None):
        self.stopped.append({"task_id": task_id, "end_trigger": end_trigger, "system_time": system_time})
        self.active_task_id = None


class FakePhysio:
    def __init__(self):
        self.subjects = []
        self.started = []
        self.markers = []
        self.stopped = 0
        self.cleared = 0

    def set_subject(self, user_id, metadata):
        self.subjects.append((user_id, metadata))

    def start_task(self, task_name, metadata=None, run_id=None):
        self.started.append((task_name, metadata or {}, run_id))

    def marker(self, name, payload=None):
        self.markers.append({"name": name, "payload": payload or {}})

    def stop_task(self):
        self.stopped += 1

    def clear_subject(self):
        self.cleared += 1


class FakeExternalCollectors:
    def __init__(self):
        self.started = []
        self.markers = []
        self.stopped = []
        self.cleared = 0

    def start_task(self, task_name, subject_id, task_id, metadata=None):
        self.started.append((task_name, subject_id, task_id, metadata or {}))

    def marker(self, name, payload=None):
        self.markers.append({"name": name, "payload": payload or {}})

    def stop_task(self, task_id=None):
        self.stopped.append(task_id)

    def clear_subject(self):
        self.cleared += 1


def make_config():
    return {
        "current_level": "L1",
        "levels": [{"level": "L1"}, {"level": "L2"}, {"level": "L3"}],
        "game_settings": {
            "current_difficulty": "low",
            "difficulty_levels": {
                "low": {"name": "low"},
                "medium": {"name": "medium"},
                "high": {"name": "high"},
            },
            "audio_enabled": True,
        },
    }


def setup_bridge(monkeypatch):
    fake_db = FakeDb()
    ids = iter([42, 43, 44])
    bridge._pending = None
    bridge._active_web_task_overlays.clear()
    bridge._active_external_tasks.clear()
    tmpdir = tempfile.TemporaryDirectory()
    monkeypatch.setattr(bridge, "INIT_CONFIG_PATH", str(Path(tmpdir.name) / "init_config.json"))
    monkeypatch.setattr(bridge, "_test_tmpdir", tmpdir, raising=False)
    monkeypatch.setattr(bridge, "db_manager", fake_db)
    monkeypatch.setattr(bridge, "generate_task_id", lambda: next(ids))
    monkeypatch.setattr(bridge.config_manager, "get_config", make_config)
    return fake_db


def test_web_task_numeric_difficulty_uses_shared_protocol(monkeypatch):
    setup_bridge(monkeypatch)

    _, radar = bridge._normalize_platform_task_fields({
        "TaskName": "\u4f20\u611f\u5668\u4efb\u52a1",
        "ID": "RadarUser",
        "Difficulty": "1",
        "Action": "task_start",
    })
    _, sa = bridge._normalize_platform_task_fields({
        "TaskName": "\u5a01\u80c1\u6392\u5e8f\u4efb\u52a1",
        "ID": "SaUser",
        "Difficulty": "3",
        "Action": "task_start",
    })

    assert radar["difficulty_key"] == "high"
    assert radar["difficulty_display"] == "high"
    assert sa["difficulty_key"] == "low"
    assert sa["difficulty_display"] == "low"


def test_external_lifecycle_numeric_difficulty_uses_shared_protocol(monkeypatch):
    setup_bridge(monkeypatch)
    _, normalized = bridge._normalize_platform_task_fields({
        "TaskName": "\u6b66\u5668\u53d1\u5c04\u4efb\u52a1",
        "ID": "DefaultID",
        "Gender": "1",
        "DefaultControlMode": "1",
        "AIAutonomyLeve": "3",
        "TaskMode": "0",
        "Difficulty": "1",
        "aiprecision": "1",
        "TaskNumber": "0",
        "Action": "task_start",
    })

    assert normalized["ai_autonomy_level"] == "L3"
    assert normalized["current_level"] == "L3"
    assert normalized["difficulty_key"] == "high"
    assert normalized["difficulty_display"] == "high"
    assert normalized["difficulty_raw"] == "1"

    _, platform = bridge._normalize_platform_task_fields({
        "TaskName": "\u5e73\u53f0\u4efb\u52a1",
        "ID": "DefaultID",
        "Difficulty": "3",
        "Action": "task_start",
    })
    assert platform["difficulty_key"] == "low"
    assert platform["difficulty_display"] == "low"


def test_platform_autonomy_numeric_zero_is_not_a_protocol_level(monkeypatch):
    setup_bridge(monkeypatch)
    config = make_config()
    config["current_level"] = "L2"

    assert bridge._normalize_current_level("0", config) == "L2"


def overall_start(task_number="3"):
    return {
        "TaskName": "平台任务",
        "ID": "DefaultID",
        "Gender": "1",
        "DefaultControlMode": "1",
        "AIAutonomyLeve": "3",
        "TaskMode": "1",
        "Difficulty": "1",
        "TaskNumber": task_number,
        "Action": "task_start",
    }


def weapon_overall_start(task_number="1"):
    return {
        "TaskName": "武器发射任务",
        "ID": "DefaultID",
        "Gender": "1",
        "DefaultControlMode": "0",
        "AIAutonomyLeve": "3",
        "TaskMode": "1",
        "aiprecision": "3",
        "TaskNumber": task_number,
        "Action": "task_start",
    }


def sub_start():
    return {"TaskName": "平台任务", "ID": "DefaultID", "Action": "sub_start"}


def simple_task_start():
    return {"TaskName": "平台任务", "ID": "DefaultID", "Action": "task_start"}


def sub_end():
    return {
        "TaskName": "平台任务",
        "ID": "DefaultID",
        "Action": "sub_end",
        "result": {
            "CurrentRedcord": [],
            "Fire": [{"FireResult": True}, {"FireResult": False}],
            "AITIME": {"AiRemindTime": 2},
            "AIcontrolTime": 41.5,
            "PersonControlTime": 3,
            "SwitchInfo": [{"mode": "AI"}],
            "CurrentTaskScore": 7,
            "ConfigControlMode": "AI",
        },
    }


def sub_ennd():
    message = sub_end()
    message["Action"] = "sub_ennd"
    return message


def radar_overlay(user_id="RadarUser"):
    return {
        "TaskName": "传感器任务",
        "ID": user_id,
        "Gender": "1",
        "DefaultControlMode": "0",
        "AIAutonomyLeve": "1",
        "TaskMode": "1",
        "Difficulty": "2",
        "TaskNumber": "2",
        "Action": "task_start",
    }


def sa_overlay(user_id="SaUser"):
    return {
        "TaskName": "威胁排序任务",
        "ID": user_id,
        "Gender": "1",
        "DefaultControlMode": "1",
        "AIAutonomyLeve": "2",
        "TaskMode": "1",
        "Difficulty": "1",
        "TaskNumber": "4",
        "Action": "task_start",
    }


def test_overall_task_start_creates_task_run_and_event(monkeypatch):
    fake_db = setup_bridge(monkeypatch)

    replies = bridge._handle_external_task(overall_start("3"), "platform_control")

    assert replies[0]["status"] == "ok"
    assert replies[0]["task_id"] == 42
    assert replies[0]["task_type"] == "PLATFORM_CONTROL"
    assert fake_db.runs[42]["expected_subtasks"] == 3
    assert fake_db.runs[42]["completed_subtasks"] == 0
    assert fake_db.events[0]["event_type"] == "overall_start"
    assert fake_db.events[0]["task_id"] == 42


def test_web_overlay_entry_semantics_and_task_scoped_pending(monkeypatch):
    setup_bridge(monkeypatch)

    radar_meta = bridge.apply_platform_task_message(radar_overlay())
    sa_meta = bridge.apply_platform_task_message(sa_overlay())

    assert radar_meta["entry_mode"] == "web_overlay"
    assert radar_meta["task_type"] == "RADAR_TARGETING"
    assert radar_meta["task_category"] == "radar"
    assert sa_meta["entry_mode"] == "web_overlay"
    assert sa_meta["task_type"] == "SA_THREAT_RESPONSE"
    assert bridge.peek_pending_include_ai("RadarUser", "RADAR_TARGETING") is None
    assert bridge.peek_pending_include_ai("SaUser", "SA_THREAT_RESPONSE") is True

    overlay, meta = bridge.consume_pending_for_task_start("RadarUser", "RADAR_TARGETING")
    assert overlay is None
    assert meta is None

    overlay, meta = bridge.get_active_overlay_for_task("RadarUser", "RADAR_TARGETING")
    assert overlay["repetition_total_override"] == 2
    assert meta["normalized"]["platform_task_id"] == "RadarUser"
    assert meta["normalized"]["task_type"] == "RADAR_TARGETING"

    overlay, meta = bridge.consume_pending_for_task_start("SaUser", "SA_THREAT_RESPONSE")
    assert overlay["repetition_total_override"] == 4
    assert meta["normalized"]["platform_task_id"] == "SaUser"
    assert meta["normalized"]["task_type"] == "SA_THREAT_RESPONSE"
    cached = json.loads(Path(bridge.INIT_CONFIG_PATH).read_text(encoding="utf-8"))
    assert cached["userId"] == "SaUser"
    assert cached["taskType"] == "sa"
    assert cached["taskNumber"] == 4


def test_simple_task_start_records_sub_start(monkeypatch):
    fake_db = setup_bridge(monkeypatch)
    bridge._handle_external_task(overall_start("3"), "platform_control")

    replies = bridge._handle_external_task(sub_start(), "platform_control")

    assert replies[0]["sub_task_seq"] == 1
    assert fake_db.runs[42]["current_subtask_seq"] == 1
    assert fake_db.events[-1]["event_type"] == "sub_start"
    assert fake_db.events[-1]["sub_task_seq"] == 1


def test_simple_task_start_without_overall_starts_external_collectors(monkeypatch):
    fake_db = setup_bridge(monkeypatch)
    external = FakeExternalCollectors()

    replies = bridge._handle_external_task(
        simple_task_start(),
        "platform_control",
        external_collectors=external,
    )

    assert replies[0]["task_id"] == 42
    assert replies[0]["sub_task_seq"] == 1
    assert fake_db.runs[42]["task_type"] == "PLATFORM_CONTROL"
    assert [event["event_type"] for event in fake_db.events] == ["sub_start"]
    assert external.started[0][0] == "PLATFORM_CONTROL"
    assert external.started[0][1] == "DefaultID"
    assert external.started[0][2] == "42"
    assert [marker["name"] for marker in external.markers] == ["sub_start"]


def test_weapon_simple_task_start_without_overall_starts_external_collectors(monkeypatch):
    fake_db = setup_bridge(monkeypatch)
    external = FakeExternalCollectors()

    replies = bridge._handle_external_task(
        {"TaskName": "姝﹀櫒鍙戝皠浠诲姟", "ID": "DefaultID", "Action": "sub_start"},
        "weapon_launch",
        external_collectors=external,
    )

    assert replies[0]["task_id"] == 42
    assert replies[0]["task_type"] == "WEAPON_LAUNCH"
    assert replies[0]["sub_task_seq"] == 1
    assert fake_db.runs[42]["task_type"] == "WEAPON_LAUNCH"
    assert [event["event_type"] for event in fake_db.events] == ["sub_start"]
    assert external.started[0][0] == "WEAPON_LAUNCH"
    assert external.started[0][1] == "DefaultID"
    assert external.started[0][2] == "42"
    assert [marker["name"] for marker in external.markers] == ["sub_start"]


def test_sub_end_records_event_result_and_completes_by_task_number(monkeypatch):
    fake_db = setup_bridge(monkeypatch)
    bridge._handle_external_task(overall_start("1"), "platform_control")
    bridge._handle_external_task(sub_start(), "platform_control")

    replies = bridge._handle_external_task(sub_end(), "platform_control")

    assert replies[0]["task_status"] == "completed"
    assert fake_db.runs[42]["status"] == "completed"
    assert fake_db.runs[42]["completed_subtasks"] == 1
    assert fake_db.runs[43]["status"] == "completed"
    assert fake_db.events[-1]["event_type"] == "sub_end"
    assert fake_db.events[-1]["task_id"] == 43
    assert fake_db.results[0]["task_id"] == 43
    assert fake_db.results[0]["sub_task_seq"] == 1
    assert fake_db.results[0]["current_task_score"] == 7
    assert fake_db.results[0]["ai_control_time"] == 41.5
    assert fake_db.results[0]["person_control_time"] == 3
    assert fake_db.results[0]["ai_remind_time"] == 2
    assert fake_db.results[0]["switch_count"] == 1
    assert fake_db.results[0]["fire_count"] == 2
    assert fake_db.results[0]["fire_success_count"] == 1


def test_sub_end_maintains_task_count_without_sub_start(monkeypatch):
    fake_db = setup_bridge(monkeypatch)
    bridge._handle_external_task(overall_start("2"), "platform_control")

    first = bridge._handle_external_task(sub_end(), "platform_control")
    second = bridge._handle_external_task(sub_end(), "platform_control")

    assert first[0]["sub_task_seq"] == 1
    assert first[0]["completed_subtasks"] == 1
    assert first[0]["task_status"] == "active"
    assert second[0]["sub_task_seq"] == 2
    assert second[0]["completed_subtasks"] == 2
    assert second[0]["task_status"] == "completed"
    assert fake_db.runs[42]["current_subtask_seq"] == 2
    assert fake_db.runs[42]["completed_subtasks"] == 2
    assert fake_db.runs[42]["status"] == "completed"
    assert first[0]["task_id"] == 43
    assert second[0]["task_id"] == 44
    assert [event["sub_task_seq"] for event in fake_db.events if event["event_type"] == "sub_end"] == [1, 2]


def test_sub_ennd_alias_stops_active_external_collector(monkeypatch):
    setup_bridge(monkeypatch)
    external = FakeExternalCollectors()

    bridge._handle_external_task(
        overall_start("1"),
        "platform_control",
        external_collectors=external,
    )
    bridge._handle_external_task(
        sub_start(),
        "platform_control",
        external_collectors=external,
    )

    replies = bridge._handle_external_task(
        sub_ennd(),
        "platform_control",
        external_collectors=external,
    )

    diagnostics = replies[0]["diagnostics"]
    assert replies[0]["status"] == "ok"
    assert replies[0]["task_status"] == "completed"
    assert diagnostics["raw_action"] == "sub_ennd"
    assert diagnostics["action"] == "sub_end"
    assert diagnostics["action_was_normalized"] is True
    assert diagnostics["event_role"] == "subtask_end"
    assert external.started[0][2] == "43"
    assert [marker["name"] for marker in external.markers] == ["sub_start", "sub_end"]
    assert external.stopped == ["43"]


def test_sub_end_without_sub_start_skips_external_stop(monkeypatch):
    setup_bridge(monkeypatch)
    external = FakeExternalCollectors()

    bridge._handle_external_task(
        overall_start("1"),
        "platform_control",
        external_collectors=external,
    )

    replies = bridge._handle_external_task(
        sub_ennd(),
        "platform_control",
        external_collectors=external,
    )

    diagnostics = replies[0]["diagnostics"]
    assert replies[0]["status"] == "ok"
    assert replies[0]["task_id"] == 43
    assert replies[0]["task_status"] == "completed"
    assert diagnostics["raw_action"] == "sub_ennd"
    assert diagnostics["action"] == "sub_end"
    assert diagnostics["action_was_normalized"] is True
    assert diagnostics["event_role"] == "subtask_end_without_start"
    assert external.started == []
    assert external.markers == []
    assert external.stopped == []


def test_overall_task_start_resumes_unfinished_task(monkeypatch):
    fake_db = setup_bridge(monkeypatch)
    bridge._handle_external_task(overall_start("3"), "platform_control")
    bridge._handle_external_task(sub_start(), "platform_control")
    bridge._handle_external_task(sub_end(), "platform_control")
    bridge._active_external_tasks.clear()

    replies = bridge._handle_external_task(overall_start("3"), "platform_control")

    assert replies[0]["task_id"] == 42
    assert replies[0]["completed_subtasks"] == 1
    assert fake_db.runs[42]["status"] == "active"
    assert fake_db.events[-1]["event_type"] == "overall_start"


def test_extra_overall_task_start_while_active_is_ignored(monkeypatch):
    fake_db = setup_bridge(monkeypatch)
    bridge._handle_external_task(overall_start("3"), "platform_control")

    replies = bridge._handle_external_task(overall_start("3"), "platform_control")

    assert replies[0]["status"] == "ignored"
    assert list(fake_db.runs) == [42]
    assert len([event for event in fake_db.events if event["event_type"] == "overall_start"]) == 1


def test_new_external_overall_closes_other_active_category_for_same_user(monkeypatch):
    fake_db = setup_bridge(monkeypatch)
    gaze = FakeGaze()
    physio = FakePhysio()

    bridge._handle_external_task(overall_start("1"), "platform_control", gaze_svc=gaze, physio_svc=physio)
    replies = bridge._handle_external_task(weapon_overall_start("1"), "weapon_launch", gaze_svc=gaze, physio_svc=physio)

    assert replies[0]["task_id"] == 43
    assert fake_db.runs[42]["status"] == "completed"
    assert fake_db.runs[42]["completed_at_ms"]
    assert fake_db.runs[43]["status"] == "active"
    assert [event["event_type"] for event in fake_db.events] == [
        "overall_start",
        "auto_closed_by_new_overall",
        "overall_start",
    ]
    assert gaze.stopped == []
    assert gaze.started == []
    assert physio.stopped == 0


def test_duplicate_full_overall_after_completed_task_is_compat_stop(monkeypatch):
    fake_db = setup_bridge(monkeypatch)
    gaze = FakeGaze()
    physio = FakePhysio()

    bridge._handle_external_task(overall_start("1"), "platform_control", gaze_svc=gaze, physio_svc=physio)
    bridge._handle_external_task(sub_start(), "platform_control", gaze_svc=gaze, physio_svc=physio)
    bridge._handle_external_task(sub_end(), "platform_control", gaze_svc=gaze, physio_svc=physio)
    replies = bridge._handle_external_task(overall_start("1"), "platform_control", gaze_svc=gaze, physio_svc=physio)

    assert replies[0]["event_type"] == "overall_stop_compat"
    assert replies[0]["task_id"] == 42
    assert replies[0]["compat"] is True
    assert sorted(fake_db.runs) == [42, 43]
    assert fake_db.runs[42]["status"] == "completed"
    assert fake_db.runs[43]["status"] == "completed"
    assert [event["event_type"] for event in fake_db.events] == [
        "overall_start",
        "sub_start",
        "sub_end",
        "overall_stop_compat",
    ]
    assert [marker["name"] for marker in gaze.markers] == [
        "sub_start",
        "sub_end",
        "overall_stop_compat",
    ]
    assert gaze.markers[-1]["payload"]["compat_reason"] == (
        "duplicate_identical_overall_start_after_completed_run"
    )


def test_different_full_overall_after_completed_task_starts_new_task(monkeypatch):
    fake_db = setup_bridge(monkeypatch)

    bridge._handle_external_task(overall_start("1"), "platform_control")
    bridge._handle_external_task(sub_start(), "platform_control")
    bridge._handle_external_task(sub_end(), "platform_control")
    replies = bridge._handle_external_task(overall_start("2"), "platform_control")

    assert replies[0].get("event_type") != "overall_stop_compat"
    assert replies[0]["task_id"] == 44
    assert sorted(fake_db.runs) == [42, 43, 44]
    assert fake_db.runs[44]["status"] == "active"


def test_sub_start_and_sub_end_emit_gaze_and_physio_markers(monkeypatch):
    setup_bridge(monkeypatch)
    gaze = FakeGaze()
    physio = FakePhysio()
    external = FakeExternalCollectors()

    bridge._handle_external_task(
        overall_start("1"),
        "platform_control",
        gaze_svc=gaze,
        physio_svc=physio,
        external_collectors=external,
    )
    bridge._handle_external_task(
        sub_start(),
        "platform_control",
        gaze_svc=gaze,
        physio_svc=physio,
        external_collectors=external,
    )
    bridge._handle_external_task(
        sub_end(),
        "platform_control",
        gaze_svc=gaze,
        physio_svc=physio,
        external_collectors=external,
    )

    assert gaze.started[0]["task_id"] == "43"
    assert gaze.started[0]["task_source"] == "platform_control"
    assert gaze.started[0]["task_name"] == "PLATFORM_CONTROL"
    assert gaze.started[0]["start_trigger"] == "sub_start"
    assert [marker["name"] for marker in gaze.markers] == ["sub_start", "sub_end"]
    assert [marker["task_id"] for marker in gaze.markers] == ["43", "43"]
    assert [marker["payload"]["gaze_task_id"] for marker in gaze.markers] == ["43", "43"]
    assert [marker["payload"]["external_task_id"] for marker in gaze.markers] == [43, 43]
    assert gaze.markers[0]["payload"]["sub_task_seq"] == 1
    assert gaze.markers[1]["payload"]["sub_task_seq"] == 1
    assert gaze.stopped[0]["task_id"] == "43"
    assert gaze.stopped[0]["end_trigger"] == "sub_end"

    assert physio.subjects[0][0] == "DefaultID"
    assert physio.started[0][0] == "PLATFORM_CONTROL"
    assert physio.started[0][2] == "43"
    assert [marker["name"] for marker in physio.markers] == ["sub_start", "sub_end"]
    assert physio.markers[-1]["payload"]["fire_success_count"] == 1
    assert physio.stopped == 1
    assert physio.cleared == 1

    assert external.started[0][0] == "PLATFORM_CONTROL"
    assert external.started[0][1] == "DefaultID"
    assert external.started[0][2] == "43"
    assert [marker["name"] for marker in external.markers] == ["sub_start", "sub_end"]
    assert external.markers[-1]["payload"]["fire_success_count"] == 1
    assert external.stopped == ["43"]
    assert external.cleared == 1


def test_external_gaze_and_physio_cover_overall_task_until_all_subtasks_complete(monkeypatch):
    setup_bridge(monkeypatch)
    gaze = FakeGaze()
    physio = FakePhysio()

    bridge._handle_external_task(overall_start("2"), "platform_control", gaze_svc=gaze, physio_svc=physio)
    bridge._handle_external_task(sub_start(), "platform_control", gaze_svc=gaze, physio_svc=physio)
    first_end = bridge._handle_external_task(sub_end(), "platform_control", gaze_svc=gaze, physio_svc=physio)

    assert first_end[0]["task_status"] == "active"
    assert len(gaze.started) == 1
    assert gaze.stopped[0]["task_id"] == "43"
    assert physio.stopped == 1

    bridge._handle_external_task(sub_start(), "platform_control", gaze_svc=gaze, physio_svc=physio)
    second_end = bridge._handle_external_task(sub_end(), "platform_control", gaze_svc=gaze, physio_svc=physio)

    assert second_end[0]["task_status"] == "completed"
    assert len(gaze.started) == 2
    assert gaze.stopped[1]["task_id"] == "44"
    assert physio.stopped == 2
    assert [marker["name"] for marker in gaze.markers] == [
        "sub_start",
        "sub_end",
        "sub_start",
        "sub_end",
    ]


def test_external_task_creates_overall_gaze_db_task_and_subtask_markers(monkeypatch):
    setup_bridge(monkeypatch)
    with tempfile.TemporaryDirectory() as tmp:
        gaze = GazeService(data_dir=tmp)
        try:
            bridge._handle_external_task(overall_start("1"), "platform_control", gaze_svc=gaze)
            bridge._handle_external_task(sub_start(), "platform_control", gaze_svc=gaze)
            bridge._handle_external_task(sub_end(), "platform_control", gaze_svc=gaze)
        finally:
            gaze.shutdown()

        conn = sqlite3.connect(Path(tmp) / "gaze_records.db")
        try:
            tasks = conn.execute(
                "SELECT task_id, user_id, task_source, task_name, start_trigger, end_trigger, status "
                "FROM gaze_tasks ORDER BY id"
            ).fetchall()
            markers = conn.execute(
                "SELECT task_id, user_id, name, payload_json FROM gaze_markers ORDER BY id"
            ).fetchall()
        finally:
            conn.close()

    assert tasks == [
        (
            "43",
            "DefaultID",
            "platform_control",
            "PLATFORM_CONTROL",
            "sub_start",
            "sub_end",
            "completed",
        )
    ]
    assert [(row[0], row[1], row[2]) for row in markers] == [
        ("43", "DefaultID", "sub_start"),
        ("43", "DefaultID", "sub_end"),
    ]
    payload = json.loads(markers[0][3])
    assert "gaze_task_id" not in payload
    assert payload["external_task_id"] == 43
    assert payload["sub_task_seq"] == 1
    sub_payload = json.loads(markers[1][3])
    assert sub_payload["sub_task_seq"] == 1
