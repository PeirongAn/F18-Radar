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
from core.message_handler import MessageHandler
from tobii.gaze_service import GazeService


class FakeDb:
    def __init__(self):
        self.runs = {}
        self.groups = {}
        self.events = []
        self.results = []

    def find_active_task_run(self, user_id, task_type, overall_only=False):
        active = [
            run for run in self.runs.values()
            if run["user_id"] == user_id and run["task_type"] == task_type and run["status"] != "completed"
        ]
        for run in sorted(active, key=lambda run: (run["started_at_ms"], run["task_id"]), reverse=True):
            if not overall_only:
                return run.copy()
            config_obj = json.loads(run.get("config_json") or "{}")
            if config_obj.get("overall_task_id") is None:
                return run.copy()
        return None

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

    def create_task_group(self, **kwargs):
        self.groups[kwargs["group_id"]] = {
            **kwargs,
            "status": "active",
            "completed_task_count": 0,
            "current_task_seq": 0,
        }

    def ensure_task_group(self, **kwargs):
        group_id = kwargs["group_id"]
        if group_id not in self.groups:
            self.create_task_group(**kwargs)
            return
        self.groups[group_id].update({key: value for key, value in kwargs.items() if value is not None})

    def ensure_task_run(self, **kwargs):
        task_id = kwargs["task_id"]
        replace_config = kwargs.pop("replace_config", False)
        if task_id not in self.runs:
            self.create_task_run(**kwargs)
            return
        run = self.runs[task_id]
        for key, value in kwargs.items():
            if value is None or key in ("reactivate",):
                continue
            if key == "config_json" and not replace_config and run.get("config_json"):
                continue
            run[key] = value
        if kwargs.get("reactivate"):
            run["status"] = "active"

    def update_task_run_progress(self, task_id, **kwargs):
        run = self.runs[task_id]
        for key, value in kwargs.items():
            if value is not None:
                run[key] = value

    def update_task_group_progress(self, group_id, **kwargs):
        group = self.groups.setdefault(group_id, {"group_id": group_id})
        for key, value in kwargs.items():
            if value is not None:
                group[key] = value

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
    ids = iter(range(42, 80))
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


def test_task_categories_use_their_respective_numeric_protocols(monkeypatch):
    setup_bridge(monkeypatch)

    _, radar = bridge._normalize_platform_task_fields({
        "TaskName": "\u4f20\u611f\u5668\u4efb\u52a1",
        "ID": "RadarUser",
        "AIAutonomyLeve": "1",
        "Difficulty": "1",
        "Action": "task_start",
    })
    _, sa = bridge._normalize_platform_task_fields({
        "TaskName": "\u5a01\u80c1\u6392\u5e8f\u4efb\u52a1",
        "ID": "SaUser",
        "AIAutonomyLeve": "3",
        "Difficulty": "3",
        "Action": "task_start",
    })

    _, platform = bridge._normalize_platform_task_fields({
        "TaskName": "\u5e73\u53f0\u4efb\u52a1",
        "ID": "PlatformUser",
        "AIAutonomyLeve": "3",
        "Difficulty": "1",
        "Action": "task_start",
    })
    _, weapon = bridge._normalize_platform_task_fields({
        "TaskName": "\u6b66\u5668\u53d1\u5c04\u4efb\u52a1",
        "ID": "DefaultID",
        "AIAutonomyLeve": "3",
        "Difficulty": "1",
        "Action": "task_start",
    })

    assert radar["current_level"] == "L1"
    assert radar["difficulty_key"] == "high"
    assert sa["current_level"] == "L3"
    assert sa["difficulty_key"] == "low"
    assert platform["current_level"] == "L1"
    assert platform["difficulty_key"] == "low"
    assert weapon["current_level"] == "L1"
    assert weapon["difficulty_key"] == "low"


def test_numeric_autonomy_mapping_depends_on_task_category():
    config = make_config()

    assert bridge._normalize_current_level("1", config, "radar") == "L1"
    assert bridge._normalize_current_level("2", config, "sa") == "L2"
    assert bridge._normalize_current_level("3", config, "radar") == "L3"
    assert bridge._normalize_current_level("1", config, "platform_control") == "L3"
    assert bridge._normalize_current_level("3", config, "weapon_launch") == "L1"


def test_radar_and_sa_all_numeric_level_difficulty_combinations():
    config = make_config()
    expected_levels = {"1": "L1", "2": "L2", "3": "L3"}
    expected_difficulties = {"1": "high", "2": "medium", "3": "low"}
    for category in ("radar", "sa"):
        for raw_level, level in expected_levels.items():
            for raw_difficulty, difficulty in expected_difficulties.items():
                assert bridge._normalize_current_level(raw_level, config, category) == level
                assert bridge._normalize_difficulty_key(raw_difficulty, config, category) == difficulty


def test_platform_autonomy_numeric_zero_is_not_a_protocol_level(monkeypatch):
    setup_bridge(monkeypatch)
    config = make_config()
    config["current_level"] = "L2"

    assert bridge._normalize_current_level("0", config) == "L2"


def test_default_control_mode_two_is_pure_ai(monkeypatch):
    setup_bridge(monkeypatch)
    message = radar_overlay("PureAIUser")
    message["DefaultControlMode"] = "2"

    _, normalized = bridge._normalize_platform_task_fields(message)
    overlay = bridge._build_overlay(normalized, bridge.config_manager.get_config())

    assert normalized["control_mode"] == "2"
    assert normalized["include_ai"] is True
    assert normalized["manual_control_disabled"] is True
    assert normalized["pure_ai"] is True
    assert overlay["is_ai_active"] is True
    assert overlay["control_mode"] == "2"
    assert overlay["manual_control_disabled"] is True


def test_control_mode_two_uses_an_independent_progress_key(monkeypatch):
    setup_bridge(monkeypatch)
    user_id = "SameUser"

    mode_one = radar_overlay(user_id)
    mode_one["DefaultControlMode"] = "1"
    bridge.apply_platform_task_message(mode_one)
    mode_one_key = bridge.get_progress_key_for_task(user_id, "RADAR_TARGETING")

    mode_two = radar_overlay(user_id)
    mode_two["DefaultControlMode"] = "2"
    bridge.apply_platform_task_message(mode_two)
    mode_two_key = bridge.get_progress_key_for_task(user_id, "RADAR_TARGETING")

    assert mode_one_key == "RADAR_TARGETING::1-L1-medium"
    assert mode_two_key == "RADAR_TARGETING::2-L1-medium"
    assert mode_two_key != mode_one_key


def test_existing_control_modes_keep_their_previous_semantics():
    assert bridge._normalize_control_mode("0") == "0"
    assert bridge._task_mode_to_include_ai("0") is False
    assert bridge._normalize_control_mode("1") == "1"
    assert bridge._task_mode_to_include_ai("1") is True


def test_pure_ai_session_rejects_manual_task_operation_but_allows_confirmation():
    session_state = {"manual_control_disabled": True}

    rejected = MessageHandler._manual_operation_rejection(
        "target_selected", "manual", session_state
    )
    allowed = MessageHandler._manual_operation_rejection(
        "target_selected", "AI", session_state
    )
    manual_completion = MessageHandler._manual_operation_rejection(
        "task_result_confirmed", "manual", session_state
    )
    ai_completion = MessageHandler._manual_operation_rejection(
        "task_result_confirmed", "AI", session_state
    )
    manual_reset = MessageHandler._manual_operation_rejection(
        "ResetSA", "manual", session_state
    )
    confirmed_reset = MessageHandler._manual_operation_rejection(
        "ResetSA", "confirmation", session_state
    )

    assert rejected and rejected[0]["reason"] == "pure_ai_mode"
    assert allowed is None
    assert manual_completion is None
    assert ai_completion is None
    assert manual_reset and manual_reset[0]["reason"] == "pure_ai_mode"
    assert confirmed_reset is None


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


def test_overall_task_start_creates_and_starts_first_task_once(monkeypatch):
    fake_db = setup_bridge(monkeypatch)

    replies = bridge._handle_external_task(overall_start("3"), "platform_control")

    assert replies[0]["status"] == "ok"
    assert replies[0]["task_id"] == 42
    assert replies[0]["task_type"] == "PLATFORM_CONTROL"
    assert fake_db.groups[42]["expected_task_count"] == 3
    assert fake_db.groups[42]["task_type"] == "PLATFORM_CONTROL"
    assert fake_db.groups[42]["autonomy_level"] == "L1"
    assert fake_db.groups[42]["difficulty"] == "low"
    assert fake_db.runs[42]["expected_subtasks"] == 1
    assert fake_db.runs[42]["task_seq"] == 1
    assert fake_db.runs[42]["group_id"] == 42
    assert fake_db.runs[42]["completed_subtasks"] == 0
    assert replies[0]["sub_task_seq"] == 1
    assert fake_db.events[0]["event_type"] == "sub_start"
    assert fake_db.events[0]["task_id"] == 42


def test_web_overlay_entry_semantics_and_task_scoped_pending(monkeypatch):
    setup_bridge(monkeypatch)

    radar_meta = bridge.apply_platform_task_message(radar_overlay())
    radar_cached = json.loads(Path(bridge.INIT_CONFIG_PATH).read_text(encoding="utf-8"))
    sa_meta = bridge.apply_platform_task_message(sa_overlay())

    assert radar_meta["entry_mode"] == "web_overlay"
    assert radar_meta["task_type"] == "RADAR_TARGETING"
    assert radar_meta["task_category"] == "radar"
    assert radar_cached["platformTask"]["raw"]["Difficulty"] == radar_overlay()["Difficulty"]
    assert radar_cached["platformTask"]["normalized"] == radar_meta
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
    assert cached["platformTask"]["raw"]["Difficulty"] == sa_overlay()["Difficulty"]
    assert cached["platformTask"]["normalized"] == sa_meta


def test_simple_task_start_after_overall_is_ignored_as_duplicate(monkeypatch):
    fake_db = setup_bridge(monkeypatch)
    bridge._handle_external_task(overall_start("3"), "platform_control")

    replies = bridge._handle_external_task(sub_start(), "platform_control")

    assert replies[0]["sub_task_seq"] == 1
    assert fake_db.runs[42]["current_subtask_seq"] == 1
    assert len(fake_db.events) == 1
    assert replies[0]["diagnostics"]["event_role"] == "subtask_start_already_active"


def test_simple_task_start_without_overall_is_ignored(monkeypatch):
    fake_db = setup_bridge(monkeypatch)
    external = FakeExternalCollectors()

    replies = bridge._handle_external_task(
        simple_task_start(),
        "platform_control",
        external_collectors=external,
    )

    assert replies[0]["status"] == "ignored"
    assert replies[0]["event_type"] == "need_overall_config"
    assert replies[0]["diagnostics"]["event_role"] == "simple_task_start_without_overall_ignored"
    assert fake_db.runs == {}
    assert fake_db.events == []
    assert external.started == []
    assert external.markers == []


def test_weapon_simple_task_start_without_overall_starts_external_collectors(monkeypatch):
    fake_db = setup_bridge(monkeypatch)
    external = FakeExternalCollectors()

    replies = bridge._handle_external_task(
        {"TaskName": "姝﹀櫒鍙戝皠浠诲姟", "ID": "DefaultID", "Action": "sub_start"},
        "weapon_launch",
        external_collectors=external,
    )

    assert replies[0]["task_id"] == 42
    assert replies[0]["task_type"] == "WEAPON_FIRING"
    assert replies[0]["sub_task_seq"] == 1
    assert fake_db.runs[42]["task_type"] == "WEAPON_FIRING"
    assert [event["event_type"] for event in fake_db.events] == ["sub_start"]
    assert external.started[0][0] == "WEAPON_FIRING"
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
    assert fake_db.events[-1]["event_type"] == "sub_end"
    assert fake_db.events[-1]["task_id"] == 42
    assert fake_db.results[0]["task_id"] == 42
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
    assert fake_db.runs[42]["expected_subtasks"] == 1
    assert fake_db.runs[42]["status"] == "completed"
    assert fake_db.runs[43]["expected_subtasks"] == 1
    assert fake_db.runs[43]["task_seq"] == 2
    assert fake_db.runs[43]["status"] == "completed"
    assert fake_db.groups[42]["current_task_seq"] == 2
    assert fake_db.groups[42]["completed_task_count"] == 2
    assert fake_db.groups[42]["status"] == "completed"
    assert first[0]["task_id"] == 42
    assert second[0]["task_id"] == 43
    assert [event["sub_task_seq"] for event in fake_db.events if event["event_type"] == "sub_start"] == [1, 2]
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
    assert external.started[0][2] == "42"
    assert [marker["name"] for marker in external.markers] == ["sub_start", "sub_end"]
    assert external.stopped == ["42"]


def test_sub_end_prestarts_next_external_collector(monkeypatch):
    setup_bridge(monkeypatch)
    external = FakeExternalCollectors()

    bridge._handle_external_task(
        overall_start("3"),
        "platform_control",
        external_collectors=external,
    )
    bridge._handle_external_task(
        sub_start(),
        "platform_control",
        external_collectors=external,
    )

    first_end = bridge._handle_external_task(
        sub_end(),
        "platform_control",
        external_collectors=external,
    )
    duplicate_start = bridge._handle_external_task(
        simple_task_start(),
        "platform_control",
        external_collectors=external,
    )

    assert first_end[0]["task_id"] == 42
    assert first_end[0]["next_subtask_task_id"] == 43
    assert first_end[0]["task_status"] == "active"
    assert duplicate_start[0]["task_id"] == 43
    assert duplicate_start[0]["diagnostics"]["event_role"] == "subtask_start_already_active"
    assert [started[2] for started in external.started] == ["42", "43"]
    assert external.started[1][3]["message"]["Action"] == "sub_start"
    assert external.started[1][3]["message"]["_inferred_from_action"] == "previous_sub_end"
    assert [marker["name"] for marker in external.markers] == ["sub_start", "sub_end", "sub_start"]
    assert external.stopped == ["42"]


def test_simple_task_start_after_completed_overall_is_ignored(monkeypatch):
    fake_db = setup_bridge(monkeypatch)
    bridge._handle_external_task(overall_start("1"), "platform_control")
    bridge._handle_external_task(sub_start(), "platform_control")
    bridge._handle_external_task(sub_end(), "platform_control")

    replies = bridge._handle_external_task(simple_task_start(), "platform_control")

    assert replies[0]["status"] == "ignored"
    assert replies[0]["event_type"] == "need_overall_config"
    assert list(fake_db.runs) == [42]
    assert bridge._active_external_tasks == {}


def test_sub_end_without_sub_start_infers_external_start(monkeypatch):
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
    assert replies[0]["task_id"] == 42
    assert replies[0]["task_status"] == "completed"
    assert diagnostics["raw_action"] == "sub_ennd"
    assert diagnostics["action"] == "sub_end"
    assert diagnostics["action_was_normalized"] is True
    assert diagnostics["event_role"] == "subtask_end"
    assert external.started[0][2] == "42"
    assert [marker["name"] for marker in external.markers] == ["sub_start", "sub_end"]
    assert external.stopped == ["42"]


def test_overall_task_start_resumes_unfinished_task(monkeypatch):
    fake_db = setup_bridge(monkeypatch)
    bridge._handle_external_task(overall_start("3"), "platform_control")
    bridge._handle_external_task(sub_start(), "platform_control")
    bridge._handle_external_task(sub_end(), "platform_control")
    fake_db.runs[43]["task_seq"] = None
    bridge._active_external_tasks.clear()

    replies = bridge._handle_external_task(overall_start("3"), "platform_control")

    assert replies[0]["task_id"] == 43
    assert replies[0]["completed_subtasks"] == 1
    assert fake_db.runs[43]["status"] == "active"
    assert fake_db.runs[43]["task_seq"] == 2
    assert fake_db.events[-1]["event_type"] == "sub_start"


def test_overall_resume_repairs_legacy_group_and_uses_current_mode(monkeypatch):
    fake_db = setup_bridge(monkeypatch)
    bridge._handle_external_task(overall_start("1"), "platform_control")
    legacy_run = fake_db.runs[42]
    legacy_config = json.loads(legacy_run["config_json"])
    legacy_config["overall_task_id"] = None
    legacy_config["normalized"]["overall_task_id"] = None
    legacy_run["group_id"] = None
    legacy_run["config_json"] = json.dumps(legacy_config, ensure_ascii=False)
    fake_db.groups.clear()
    bridge._active_external_tasks.clear()

    current = overall_start("1")
    current["DefaultControlMode"] = "0"
    current["AIAutonomyLeve"] = "3"
    current["Difficulty"] = "3"
    replies = bridge._handle_external_task(current, "platform_control")

    repaired_config = json.loads(fake_db.runs[42]["config_json"])
    assert replies[0]["task_id"] == 42
    assert fake_db.runs[42]["group_id"] == 42
    assert fake_db.groups[42]["control_mode"] == "0"
    assert fake_db.groups[42]["is_ai_active"] is False
    assert repaired_config["overall_task_id"] == 42
    assert repaired_config["normalized"]["control_mode"] == "0"
    assert repaired_config["normalized"]["difficulty_raw"] == "3"


def test_extra_overall_task_start_while_active_is_ignored(monkeypatch):
    fake_db = setup_bridge(monkeypatch)
    bridge._handle_external_task(overall_start("3"), "platform_control")

    replies = bridge._handle_external_task(overall_start("3"), "platform_control")

    assert replies[0]["status"] == "ignored"
    assert list(fake_db.runs) == [42]
    assert len([event for event in fake_db.events if event["event_type"] == "sub_start"]) == 1


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
        "sub_start",
        "auto_closed_by_new_overall",
        "sub_start",
    ]
    assert gaze.stopped[0]["task_id"] == "42"
    assert len(gaze.started) == 2
    assert physio.stopped == 1


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
    assert sorted(fake_db.runs) == [42]
    assert fake_db.runs[42]["status"] == "completed"
    assert [event["event_type"] for event in fake_db.events] == [
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
    assert replies[0]["task_id"] == 43
    assert sorted(fake_db.runs) == [42, 43]
    assert fake_db.runs[43]["status"] == "active"


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

    assert gaze.started[0]["task_id"] == "42"
    assert gaze.started[0]["task_source"] == "platform_control"
    assert gaze.started[0]["task_name"] == "PLATFORM_CONTROL"
    assert gaze.started[0]["start_trigger"] == "sub_start"
    assert [marker["name"] for marker in gaze.markers] == ["sub_start", "sub_end"]
    assert [marker["task_id"] for marker in gaze.markers] == ["42", "42"]
    assert [marker["payload"]["gaze_task_id"] for marker in gaze.markers] == ["42", "42"]
    assert [marker["payload"]["external_task_id"] for marker in gaze.markers] == [42, 42]
    assert gaze.markers[0]["payload"]["sub_task_seq"] == 1
    assert gaze.markers[1]["payload"]["sub_task_seq"] == 1
    assert gaze.stopped[0]["task_id"] == "42"
    assert gaze.stopped[0]["end_trigger"] == "sub_end"

    assert physio.subjects[0][0] == "DefaultID"
    assert physio.started[0][0] == "PLATFORM_CONTROL"
    assert physio.started[0][2] == "42"
    assert [marker["name"] for marker in physio.markers] == ["sub_start", "sub_end"]
    assert physio.markers[-1]["payload"]["fire_success_count"] == 1
    assert physio.stopped == 1
    assert physio.cleared == 1

    assert external.started[0][0] == "PLATFORM_CONTROL"
    assert external.started[0][1] == "DefaultID"
    assert external.started[0][2] == "42"
    assert [marker["name"] for marker in external.markers] == ["sub_start", "sub_end"]
    assert external.markers[-1]["payload"]["fire_success_count"] == 1
    assert external.stopped == ["42"]
    assert external.cleared == 1


def test_external_gaze_and_physio_cover_overall_task_until_all_subtasks_complete(monkeypatch):
    setup_bridge(monkeypatch)
    gaze = FakeGaze()
    physio = FakePhysio()

    bridge._handle_external_task(overall_start("2"), "platform_control", gaze_svc=gaze, physio_svc=physio)
    bridge._handle_external_task(sub_start(), "platform_control", gaze_svc=gaze, physio_svc=physio)
    first_end = bridge._handle_external_task(sub_end(), "platform_control", gaze_svc=gaze, physio_svc=physio)

    assert first_end[0]["task_status"] == "active"
    assert first_end[0]["next_subtask_task_id"] == 43
    assert len(gaze.started) == 2
    assert gaze.stopped[0]["task_id"] == "42"
    assert physio.stopped == 1

    bridge._handle_external_task(sub_start(), "platform_control", gaze_svc=gaze, physio_svc=physio)
    second_end = bridge._handle_external_task(sub_end(), "platform_control", gaze_svc=gaze, physio_svc=physio)

    assert second_end[0]["task_status"] == "completed"
    assert len(gaze.started) == 2
    assert gaze.stopped[1]["task_id"] == "43"
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
            "42",
            "DefaultID",
            "platform_control",
            "PLATFORM_CONTROL",
            "sub_start",
            "sub_end",
            "completed",
        )
    ]
    assert [(row[0], row[1], row[2]) for row in markers] == [
        ("42", "DefaultID", "sub_start"),
        ("42", "DefaultID", "sub_end"),
    ]
    payload = json.loads(markers[0][3])
    assert "gaze_task_id" not in payload
    assert payload["external_task_id"] == 42
    assert payload["sub_task_seq"] == 1
    sub_payload = json.loads(markers[1][3])
    assert sub_payload["sub_task_seq"] == 1
