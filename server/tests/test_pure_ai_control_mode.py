import asyncio
import json
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
logging.raiseExceptions = False

from core.message_handler import MessageHandler
from network import platform_task_bridge as bridge


def base_config():
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


def radar_start(control_mode="2"):
    return {
        "TaskName": "radar",
        "WebTaskKind": "radar",
        "ID": "pure-ai-user",
        "DefaultControlMode": control_mode,
        "AIAutonomyLeve": "2",
        "Difficulty": "2",
        "TaskMode": "1",
        "TaskNumber": "3",
        "Action": "task_start",
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, "1"),
        ("", "1"),
        ("0", "0"),
        (False, "0"),
        ("manual", "0"),
        ("1", "1"),
        ("legacy-ai-value", "1"),
        ("2", "2"),
        ("pure_ai", "2"),
        ("pure-ai", "2"),
        ("ai_only", "2"),
        ("ai-only", "2"),
    ],
)
def test_control_mode_normalization_matrix(raw, expected):
    assert bridge._normalize_control_mode(raw) == expected
    assert bridge._task_mode_to_include_ai(raw) is (expected != "0")


@pytest.mark.parametrize(
    ("mode", "include_ai", "manual_disabled"),
    [("0", False, False), ("1", True, False), ("2", True, True)],
)
def test_platform_normalization_preserves_all_three_modes(
    monkeypatch, mode, include_ai, manual_disabled
):
    monkeypatch.setattr(bridge.config_manager, "get_config", base_config)

    raw, normalized = bridge._normalize_platform_task_fields(radar_start(mode))
    overlay = bridge._build_overlay(normalized, base_config())

    assert raw["DefaultControlMode"] == mode
    assert normalized["default_control_mode"] == mode
    assert normalized["control_mode"] == mode
    assert normalized["include_ai"] is include_ai
    assert normalized["manual_control_disabled"] is manual_disabled
    assert normalized["pure_ai"] is manual_disabled
    assert overlay["control_mode"] == mode
    assert overlay["is_ai_active"] is include_ai
    assert overlay["manual_control_disabled"] is manual_disabled


def test_pure_ai_mode_is_persisted_for_frontend_autostart(monkeypatch, tmp_path):
    init_config = tmp_path / "init_config.json"
    init_config.write_text(json.dumps({"useJoystick": True}), encoding="utf-8")
    monkeypatch.setattr(bridge, "INIT_CONFIG_PATH", str(init_config))
    monkeypatch.setattr(bridge.config_manager, "get_config", base_config)

    raw, normalized = bridge._normalize_platform_task_fields(radar_start("2"))
    bridge._persist_web_init_config(raw, normalized)

    persisted = json.loads(init_config.read_text(encoding="utf-8"))
    assert persisted["includeAI"] is True
    assert persisted["controlMode"] == "2"
    assert persisted["manualControlDisabled"] is True
    assert persisted["useJoystick"] is True
    assert persisted["taskNumber"] == 3
    assert persisted["platformTask"]["normalized"]["pure_ai"] is True


@pytest.mark.parametrize(
    ("normalized", "message", "expected_mode"),
    [
        ({"control_mode": "2"}, {"control_mode": "0"}, "2"),
        ({"default_control_mode": "2"}, {"control_mode": "0"}, "2"),
        ({}, {"control_mode": "2"}, "2"),
        ({}, {"manual_control_disabled": True}, "2"),
        ({}, {"include_ai": True}, "1"),
        ({}, {"is_ai_active": True}, "1"),
        ({}, {}, "0"),
    ],
)
def test_session_control_mode_uses_protocol_precedence(normalized, message, expected_mode):
    session_state = {}

    mode, manual_disabled = MessageHandler._set_control_mode_session(
        session_state, message, normalized
    )

    assert mode == expected_mode
    assert manual_disabled is (expected_mode == "2")
    assert session_state == {
        "control_mode": expected_mode,
        "manual_control_disabled": expected_mode == "2",
    }


def test_control_mode_is_copied_into_scenario_and_questionnaire_context():
    scenario = {"repetition_info": {"current": 1, "total": 2}}

    MessageHandler._apply_control_mode_to_scenario(scenario, "0", False)

    assert scenario["control_mode"] == "0"
    assert scenario["manual_control_disabled"] is False
    assert scenario["repetition_info"]["control_mode"] == "0"
    assert scenario["repetition_info"]["manual_control_disabled"] is False


@pytest.mark.parametrize(
    "message_type",
    [
        "settings_update",
        "antenna_adjusted",
        "target_selected",
        "threat_clicked",
        "record_operation",
        "record_bulk_operations",
        "ResetSA",
        "user_take_control",
    ],
)
def test_pure_ai_rejects_every_manual_task_operation_at_dispatch(message_type):
    handler = MessageHandler()
    result = asyncio.run(
        handler.handle_client_message(
            json.dumps({"type": message_type, "event_owner": "manual"}),
            {"manual_control_disabled": True},
        )
    )

    assert result == [{
        "type": "operation_rejected",
        "status": "forbidden",
        "reason": "pure_ai_mode",
        "operation_type": message_type,
        "message": "Manual operation is disabled while DefaultControlMode is 2.",
    }]


@pytest.mark.parametrize("event_owner", ["AI", "ai", " Ai "])
def test_pure_ai_allows_ai_owned_task_operations(event_owner):
    assert MessageHandler._manual_operation_rejection(
        "target_selected", event_owner, {"manual_control_disabled": True}
    ) is None


def test_pure_ai_allows_only_the_explicit_sa_confirmation_reset():
    session = {"manual_control_disabled": True}

    assert MessageHandler._manual_operation_rejection(
        "ResetSA", "confirmation", session
    ) is None
    assert MessageHandler._manual_operation_rejection(
        "ResetSA", "manual", session
    )[0]["reason"] == "pure_ai_mode"


@pytest.mark.parametrize("event_owner", ["manual", "AI", "confirmation", ""])
def test_result_confirmation_is_never_blocked_by_pure_ai_guard(event_owner):
    assert MessageHandler._manual_operation_rejection(
        "task_result_confirmed",
        event_owner,
        {"manual_control_disabled": True},
    ) is None


@pytest.mark.parametrize(
    ("mode", "level", "difficulty", "expected"),
    [
        ("0", "L1", "low", "RADAR_TARGETING::0-L1-low"),
        ("1", "L1", "low", "RADAR_TARGETING::1-L1-low"),
        ("2", "L1", "low", "RADAR_TARGETING::2-L1-low"),
        ("2", "L3", "low", "RADAR_TARGETING::2-L3-low"),
        ("2", "L3", "high", "RADAR_TARGETING::2-L3-high"),
    ],
)
def test_progress_key_isolates_mode_autonomy_and_difficulty(
    monkeypatch, mode, level, difficulty, expected
):
    monkeypatch.setattr(
        bridge,
        "get_active_overlay_for_task",
        lambda user_id, task_type: (
            {},
            {"normalized": {
                "control_mode": mode,
                "current_level": level,
                "difficulty_key": difficulty,
            }},
        ),
    )

    assert bridge.get_progress_key_for_task("same-user", "RADAR_TARGETING") == expected


def test_progress_key_falls_back_to_task_type_without_platform_overlay(monkeypatch):
    monkeypatch.setattr(
        bridge,
        "get_active_overlay_for_task",
        lambda user_id, task_type: (None, None),
    )

    assert bridge.get_progress_key_for_task("local-user", "RADAR_TARGETING") == "RADAR_TARGETING"
