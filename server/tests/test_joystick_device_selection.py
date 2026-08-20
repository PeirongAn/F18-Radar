import json

import joystick.joystick_websocket_controller as joystick_controller
from joystick.joystick_websocket_controller import get_joystick_candidate_priority


def test_localized_warthog_stick_is_preferred_over_throttle():
    stick_priority = get_joystick_candidate_priority(
        "2轴19按钮 游戏杆 有帽子切换",
        axes=2,
        buttons=19,
        hats=1,
    )
    throttle_priority = get_joystick_candidate_priority(
        "Throttle - HOTAS Warthog",
        axes=5,
        buttons=32,
        hats=1,
    )

    assert stick_priority < throttle_priority


def test_named_joystick_remains_the_highest_priority_device():
    assert get_joystick_candidate_priority(
        "Joystick - HOTAS Warthog",
        axes=2,
        buttons=19,
        hats=1,
    ) == 0


def test_localized_capability_only_stick_requires_a_hat():
    assert get_joystick_candidate_priority(
        "2轴-19按钮游戏控制器",
        axes=2,
        buttons=19,
        hats=1,
    ) == 1
    assert get_joystick_candidate_priority(
        "2轴-19按钮游戏控制器",
        axes=2,
        buttons=19,
        hats=0,
    ) != 1


def test_throttle_is_ranked_after_other_generic_controllers():
    generic_priority = get_joystick_candidate_priority(
        "USB Game Controller",
        axes=4,
        buttons=12,
        hats=1,
    )
    throttle_priority = get_joystick_candidate_priority(
        "Throttle - HOTAS Warthog",
        axes=5,
        buttons=32,
        hats=1,
    )

    assert generic_priority < throttle_priority


def test_chinese_throttle_is_ranked_last():
    assert get_joystick_candidate_priority(
        "HOTAS Warthog 油门",
        axes=5,
        buttons=32,
        hats=1,
    ) == 100


def test_configured_name_or_guid_overrides_automatic_selection():
    assert get_joystick_candidate_priority(
        "Custom Flight Controller",
        axes=4,
        buttons=12,
        hats=1,
        preferred_name="Flight Controller",
    ) == -10
    assert get_joystick_candidate_priority(
        "Throttle - HOTAS Warthog",
        axes=5,
        buttons=32,
        hats=1,
        guid="030000004f04000004b6000000000000",
        preferred_guid="030000004F04000004B6000000000000",
    ) == -20


def test_runtime_config_supports_nested_name_and_guid(tmp_path, monkeypatch):
    (tmp_path / "init_config.json").write_text(
        json.dumps({
            "joystickDevice": {
                "name": "2轴19按钮 游戏杆 有帽子切换",
                "guid": "030000004f04000004b6000000000000",
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(joystick_controller, "CONFIG_DIR", tmp_path)

    assert joystick_controller.load_joystick_device_preference() == {
        "name": "2轴19按钮 游戏杆 有帽子切换",
        "guid": "030000004f04000004b6000000000000",
    }
