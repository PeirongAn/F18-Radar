import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
logging.raiseExceptions = False

from managers.task_manager import TaskScenarioManager


def make_config():
    return {
        "current_level": "L0",
        "levels": [{"level": "L0", "name": "L0"}],
        "game_settings": {
            "practice_repetitions": 1,
            "max_repetitions": 1,
            "current_difficulty": "low",
            "difficulty_levels": {
                "low": {"name": "low", "threat_count": 1, "target_count": 1}
            },
            "audio_enabled": True,
        },
    }


def make_manager():
    TaskScenarioManager.clear_practice_cache("tasknumber_user", "SA_THREAT_RESPONSE")
    return TaskScenarioManager(
        make_config(),
        "tasknumber_user",
        "SA_THREAT_RESPONSE",
        is_practice=True,
        is_ai_active_request=False,
    )


def seed_completed_manual_scenario(manager, current=3, total=3):
    manager.current_scenario = {
        "is_ai_active": False,
        "audio_enabled": True,
        "ai_level_name": None,
        "ai_level_config": None,
        "difficulty_name": "low",
        "difficulty_config": {"name": "low", "difficulty_name": "low"},
        "scenario_info": {"index": 1, "total": 1},
        "repetition_info": {
            "current": current,
            "total": total,
            "is_practice": True,
            "difficulty": "low",
            "engine_difficulty": "low",
            "is_ai_active": False,
        },
        "max_repetitions_override": total,
    }
    manager.repetition_counter = current
    manager.max_repetitions = total
    manager.manual_queue = []
    manager.ai_queue = []
    manager.active_queue = manager.manual_queue
    manager._practice_memory_cache[
        (manager.user_id, manager.progress_task_type)
    ] = {
        "current_scenario": manager.current_scenario,
        "repetition_counter": current,
        "ai_queue": [],
        "manual_queue": [],
        "is_completed": True,
        "is_manual_completed": True,
        "is_ai_completed": False,
    }


def test_tasknumber_can_expand_without_resetting_progress():
    manager = make_manager()
    seed_completed_manual_scenario(manager, current=3, total=3)

    manager.apply_platform_overlay({"repetition_total_override": 5})
    next_scenario = manager.get_next_task_parameters(False)

    assert next_scenario != "ALL_COMPLETED"
    assert next_scenario["repetition_info"]["current"] == 4
    assert next_scenario["repetition_info"]["total"] == 5
    assert next_scenario["max_repetitions_override"] == 5


def test_tasknumber_can_shrink_when_new_total_keeps_current_progress():
    manager = make_manager()
    seed_completed_manual_scenario(manager, current=3, total=5)

    manager.apply_platform_overlay({"repetition_total_override": 4})

    assert manager.repetition_counter == 3
    assert manager.max_repetitions == 4
    assert manager.current_scenario["repetition_info"]["total"] == 4
    assert manager.current_scenario["max_repetitions_override"] == 4


def test_tasknumber_can_shrink_to_current_progress_boundary():
    manager = make_manager()
    seed_completed_manual_scenario(manager, current=3, total=5)

    manager.apply_platform_overlay({"repetition_total_override": 3})

    assert manager.repetition_counter == 3
    assert manager.max_repetitions == 3
    assert manager.current_scenario["repetition_info"]["total"] == 3
    assert manager.current_scenario["max_repetitions_override"] == 3


def test_tasknumber_does_not_shrink_below_current_progress():
    manager = make_manager()
    seed_completed_manual_scenario(manager, current=4, total=5)

    manager.apply_platform_overlay({"repetition_total_override": 3})

    assert manager.repetition_counter == 4
    assert manager.max_repetitions == 5
    assert manager.current_scenario["repetition_info"]["total"] == 5
    assert manager.current_scenario["max_repetitions_override"] == 5


def test_equal_runtime_total_is_persisted_as_scenario_override():
    manager = make_manager()
    seed_completed_manual_scenario(manager, current=1, total=1)
    manager.current_scenario.pop("max_repetitions_override")
    manager.max_repetitions = 30
    manager.current_scenario["repetition_info"]["total"] = 30

    manager.apply_repetition_override(30, overwrite=True)

    assert manager.current_scenario["max_repetitions_override"] == 30
    assert manager.current_scenario["repetition_info"]["total"] == 30

    # ResetSA creates another manager and refreshes the config. The scenario
    # marker must keep the explicit task count instead of falling back to 1.
    manager.config["game_settings"]["practice_repetitions"] = 1
    manager.pending_repetition_override = None
    manager._refresh_config()
    assert manager.max_repetitions == 30


def test_reset_sa_keeps_explicit_count_after_first_round():
    manager = make_manager()
    manager.max_repetitions = 30
    manager.apply_repetition_override(30, overwrite=True)
    first_scenario = manager.get_next_task_parameters(False)
    manager.apply_repetition_override(30, overwrite=True)
    manager.mark_task_completed()

    assert first_scenario["repetition_info"]["current"] == 1
    assert first_scenario["repetition_info"]["total"] == 30

    # Mirror _handle_sa_operations on the following ResetSA request: a fresh
    # manager loads the stored scenario before asking for the next round.
    reloaded = TaskScenarioManager(
        make_config(),
        "tasknumber_user",
        "SA_THREAT_RESPONSE",
        is_practice=True,
        is_ai_active_request=False,
    )
    second_scenario = reloaded.get_next_task_parameters(False)

    assert second_scenario["repetition_info"]["current"] == 2
    assert second_scenario["repetition_info"]["total"] == 30
    assert second_scenario["max_repetitions_override"] == 30
