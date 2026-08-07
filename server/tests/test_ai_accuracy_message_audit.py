import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.message_handler import MessageHandler


def _context(task_id):
    return {
        str(task_id): {
            "task_type": "SA_THREAT_RESPONSE",
            "ai_accuracy": {
                "algorithm_version": "difficulty-group-range-v1",
                "task_group_id": 22,
                "ai_level": "L2",
                "difficulty": "high",
                "probability_range": [0.7, 0.8],
                "probability_seed": 10,
                "probability_random": 0.4,
                "sampled_probability": 0.74,
            },
            "ai_decision": {
                "task_id": task_id,
                "task_seq": 1,
                "decision_seed": 11,
                "decision_random": 0.2,
                "pool_random": 0.3,
                "intended_correct": True,
                "selection_protocol": "server-authoritative-target-v1",
                "selected_pool": ["highest"],
                "fallback_reason": None,
                "pool_index": 0,
                "expected_target_id": "highest",
            },
        }
    }


def test_sa_ai_selection_uses_server_truth_and_persists_audit(monkeypatch):
    handler = MessageHandler()
    handler._set_current_task("SA_THREAT_RESPONSE", 77, 1000)
    handler.current_session["user_id"] = "pilot"
    session_state = {
        "is_practice": False,
        "sa_threat_truth": {
            "task_id": 77,
            "threat_ids": ["highest", "other"],
            "highest_priority_threat_id": "highest",
        },
        "ai_decision_contexts": _context(77),
    }
    recorded = []

    def record_operation(operation, is_practice, wait_for_commit=False):
        recorded.append((operation, is_practice, wait_for_commit))
        return True

    handler_db_manager = MessageHandler._handle_threat_clicked.__globals__["db_manager"]
    monkeypatch.setattr(handler_db_manager, "record_operation", record_operation)
    result = asyncio.run(handler._handle_threat_clicked({
        "task_id": 77,
        "threat_id": "highest",
        "is_highest_priority": False,
        "event_owner": "AI",
        "ai_decision_outcome": {
            "selected_pool": ["other"],
            "fallback_reason": "client_value_must_not_override_server",
            "selection_protocol": "server-authoritative-target-v1",
            "expected_target_id": "highest",
        },
    }, session_state, "AI"))

    assert result[0]["type"] == "threat_clicked_recorded"
    assert recorded[0][2] is True
    parameters = recorded[0][0]["parameters"]
    assert parameters["is_correct"] is True
    assert parameters["ai_decision"]["task_group_id"] == 22
    assert parameters["ai_decision"]["selected_pool"] == ["highest"]
    assert parameters["ai_decision"]["actual_selection"] == "highest"


def test_sa_ai_selection_write_failure_is_reported(monkeypatch):
    handler = MessageHandler()
    handler._set_current_task("SA_THREAT_RESPONSE", 78, 1000)
    session_state = {
        "is_practice": False,
        "sa_threat_truth": {
            "task_id": 78,
            "threat_ids": ["highest"],
            "highest_priority_threat_id": "highest",
        },
        "ai_decision_contexts": _context(78),
    }

    def fail(*_args, **_kwargs):
        raise RuntimeError("disk unavailable")

    handler_db_manager = MessageHandler._handle_threat_clicked.__globals__["db_manager"]
    monkeypatch.setattr(handler_db_manager, "record_operation", fail)
    result = asyncio.run(handler._handle_threat_clicked({
        "task_id": 78,
        "threat_id": "highest",
        "event_owner": "AI",
        "ai_decision_outcome": {
            "selection_protocol": "server-authoritative-target-v1",
            "expected_target_id": "highest",
        },
    }, session_state, "AI"))
    assert result[0]["type"] == "threat_clicked_record_failed"
    assert result[0]["reason"] == "database_write_failed"


def test_practice_group_accuracy_is_session_only_and_shared(monkeypatch):
    handler = MessageHandler()
    globals_ = MessageHandler._prepare_ai_accuracy.__globals__
    config = {
        "ai_accuracy": {"algorithm_version": "difficulty-group-range-v1", "base_seed": 7},
        "levels": [{
            "level": "L1",
            "decision_probability_ranges_by_difficulty": {
                "low": [0.4, 0.5], "medium": [0.35, 0.45], "high": [0.3, 0.4],
            },
        }],
    }
    monkeypatch.setattr(globals_["config_manager"], "get_config", lambda: config)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("practice accuracy must not access persistent group accuracy")

    monkeypatch.setattr(globals_["db_manager"], "get_task_group", forbidden)
    monkeypatch.setattr(globals_["db_manager"], "save_task_group_ai_accuracy", forbidden)
    session_state = {"is_practice": True}
    scenario = {"is_ai_active": True, "ai_level_name": "L1", "difficulty_name": "low"}
    first_group, first_decision = handler._prepare_ai_accuracy(
        session_state, current_scenario=scenario, user_id="practice", task_type="RADAR_TARGETING",
        task_group_id=9, task_id=101, task_seq=1,
    )
    second_group, second_decision = handler._prepare_ai_accuracy(
        session_state, current_scenario=scenario, user_id="practice", task_type="RADAR_TARGETING",
        task_group_id=9, task_id=102, task_seq=2,
    )
    assert first_group == second_group
    assert first_decision["decision_seed"] != second_decision["decision_seed"]
