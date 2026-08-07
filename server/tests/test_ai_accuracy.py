import asyncio
import json
import os
import sqlite3
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from managers.database_manager import DatabaseManager
from network.http_server import HTTPServer
from services.ai_accuracy import (
    AIAccuracyConfigError,
    SELECTION_PROTOCOL_VERSION,
    bind_task_decision_selection,
    build_group_accuracy,
    build_task_decision,
    resolve_probability_range,
)


MATRIX = {
    "L1": {"low": (0.40, 0.50), "medium": (0.35, 0.45), "high": (0.30, 0.40)},
    "L2": {"low": (0.80, 0.90), "medium": (0.75, 0.85), "high": (0.70, 0.80)},
    "L3": {"low": (0.99, 1.00), "medium": (0.97, 0.99), "high": (0.94, 0.97)},
}


def accuracy_config():
    return {
        "ai_accuracy": {
            "algorithm_version": "difficulty-group-range-v1",
            "base_seed": 20260807,
        },
        "levels": [
            {
                "level": level,
                "decision_probability_ranges_by_difficulty": values,
            }
            for level, values in MATRIX.items()
        ],
    }


def test_public_and_dist_configs_match_the_matrix():
    repository_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    with open(os.path.join(repository_root, "public", "agent_level.json"), encoding="utf-8") as source:
        public_config = json.load(source)
    with open(os.path.join(repository_root, "dist", "agent_level.json"), encoding="utf-8") as source:
        dist_config = json.load(source)
    assert public_config == dist_config
    assert public_config["ai_accuracy"] == {
        "algorithm_version": "difficulty-group-range-v1",
        "base_seed": 20260807,
    }
    for level, difficulties in MATRIX.items():
        configured = next(item for item in public_config["levels"] if item["level"] == level)
        assert {
            difficulty: tuple(bounds)
            for difficulty, bounds in configured["decision_probability_ranges_by_difficulty"].items()
        } == difficulties


@pytest.mark.parametrize(
    "level,difficulty,expected",
    [(level, difficulty, bounds) for level, values in MATRIX.items() for difficulty, bounds in values.items()],
)
def test_all_level_difficulty_ranges(level, difficulty, expected):
    assert resolve_probability_range(accuracy_config(), level, difficulty) == expected


def test_matrix_is_monotonic_by_level_and_difficulty():
    config = accuracy_config()
    for difficulty in ("low", "medium", "high"):
        assert resolve_probability_range(config, "L1", difficulty)[1] < resolve_probability_range(config, "L2", difficulty)[0]
        assert resolve_probability_range(config, "L2", difficulty)[1] < resolve_probability_range(config, "L3", difficulty)[0]
    for level in ("L1", "L2", "L3"):
        assert resolve_probability_range(config, level, "low")[0] >= resolve_probability_range(config, level, "medium")[0]
        assert resolve_probability_range(config, level, "medium")[0] >= resolve_probability_range(config, level, "high")[0]


def test_legacy_single_value_and_range_are_supported():
    assert resolve_probability_range({"levels": [{"level": "L1", "decision_probabilities": [0.4]}]}, "L1", "high") == (0.4, 0.4)
    assert resolve_probability_range({"levels": [{"level": "L1", "decision_probabilities": [0.3, 0.5]}]}, "L1", "low") == (0.3, 0.5)


@pytest.mark.parametrize("values", [[], [0.7, 0.6], [-0.1, 0.5], [0.5, 1.1], [0.1, 0.2, 0.3]])
def test_invalid_ranges_are_rejected(values):
    with pytest.raises(AIAccuracyConfigError):
        resolve_probability_range({"levels": [{"level": "L1", "decision_probabilities": values}]}, "L1", "low")


def test_unknown_algorithm_version_is_rejected():
    config = accuracy_config()
    config["ai_accuracy"]["algorithm_version"] = "future-unimplemented-version"
    with pytest.raises(AIAccuracyConfigError):
        build_group_accuracy(
            config, user_id="pilot", task_type="RADAR_TARGETING", task_group_id=1,
            ai_level="L1", difficulty="low",
        )


def test_group_and_task_randomness_is_reproducible_and_shared():
    kwargs = dict(
        user_id="pilot-1", task_type="RADAR_TARGETING", task_group_id=22,
        ai_level="L2", difficulty="high",
    )
    first = build_group_accuracy(accuracy_config(), **kwargs)
    second = build_group_accuracy(accuracy_config(), **kwargs)
    assert first == second
    assert 0.70 <= first["sampled_probability"] <= 0.80
    decisions = [
        build_task_decision(first, task_id=1000 + seq, task_seq=seq, task_type="RADAR_TARGETING")
        for seq in range(1, 21)
    ]
    assert len({item["decision_seed"] for item in decisions}) == 20
    assert all(first["sampled_probability"] == second["sampled_probability"] for _ in decisions)


def test_task_decision_binds_one_canonical_server_target():
    decision = {"intended_correct": False, "pool_random": 0.5}
    bound = bind_task_decision_selection(
        decision,
        correct_pool=["enemy-2", "enemy-1"],
        incorrect_pool=["friend-3", "friend-1", "friend-2"],
        correct_pool_empty_reason="enemy_pool_empty",
        incorrect_pool_empty_reason="friendly_pool_empty",
    )
    assert bound["selection_protocol"] == SELECTION_PROTOCOL_VERSION
    assert bound["selected_pool"] == ["friend-1", "friend-2", "friend-3"]
    assert bound["pool_index"] == 1
    assert bound["expected_target_id"] == "friend-2"


def test_sampling_means_converge_for_groups_and_rounds():
    config = accuracy_config()
    group_samples = [
        build_group_accuracy(
            config, user_id="pilot", task_type="RADAR_TARGETING", task_group_id=group_id,
            ai_level="L2", difficulty="high",
        )["sampled_probability"]
        for group_id in range(1, 100001)
    ]
    assert abs(sum(group_samples) / len(group_samples) - 0.75) < 0.005

    group = build_group_accuracy(
        config, user_id="pilot", task_type="SA_THREAT_RESPONSE", task_group_id=8,
        ai_level="L2", difficulty="medium",
    )
    correct = sum(
        build_task_decision(group, task_id=task_id, task_seq=task_id, task_type="SA_THREAT_RESPONSE")["intended_correct"]
        for task_id in range(1, 100001)
    )
    assert abs(correct / 100000 - group["sampled_probability"]) <= 0.005


def test_database_persists_group_sample_and_aggregates_audit(tmp_path):
    manager = DatabaseManager(str(tmp_path / "ai-accuracy.db"))
    try:
        manager.initialize_database()
        manager.ensure_task_group(
            group_id=22, task_type="RADAR_TARGETING", user_id="pilot", expected_task_count=2,
            difficulty="high", autonomy_level="L2", is_ai_active=True,
        )
        group_context = build_group_accuracy(
            accuracy_config(), user_id="pilot", task_type="RADAR_TARGETING",
            task_group_id=22, ai_level="L2", difficulty="high",
        )
        first_saved = manager.save_task_group_ai_accuracy(22, group_context)
        changed_context = {**group_context, "sampled_probability": 0.01}
        second_saved = manager.save_task_group_ai_accuracy(22, changed_context)
        assert second_saved["sampled_ai_probability"] == first_saved["sampled_ai_probability"]

        for seq, correct in ((1, True), (2, False)):
            task_id = 100 + seq
            manager.ensure_task_run(
                task_id=task_id, task_type="RADAR_TARGETING", user_id="pilot",
                group_id=22, task_seq=seq,
            )
            decision = build_task_decision(
                group_context, task_id=task_id, task_seq=seq, task_type="RADAR_TARGETING"
            )
            selected_id = "enemy-1" if correct else "friend-1"
            manager.record_operation({
                "task_id": task_id,
                "operationType": "target_selected",
                "timestamp": 1000 + seq,
                "isActive": True,
                "parameters": {
                    "target_id": selected_id,
                    "is_correct": correct,
                    "ai_decision": {
                        **group_context,
                        **decision,
                        "selection_protocol": SELECTION_PROTOCOL_VERSION,
                        "selected_pool": [selected_id],
                        "expected_target_id": selected_id,
                        "actual_selection": selected_id,
                        "is_correct": correct,
                    },
                },
                "user_id": "pilot",
                "event_owner": "AI",
            }, False, wait_for_commit=True)

        result = manager.get_ai_accuracy(22, include_decisions=True)
        assert result["valid_decision_count"] == 2
        assert result["correct_count"] == 1
        assert result["incorrect_count"] == 1
        assert result["actual_accuracy"] == 0.5
        assert result["audit_complete"] is True
        assert result["semantic_mismatch_count"] == 0
        assert len(result["decisions"]) == 2
    finally:
        manager.shutdown()


def test_historical_group_is_reported_as_untracked(tmp_path):
    manager = DatabaseManager(str(tmp_path / "legacy-accuracy.db"))
    try:
        manager.initialize_database()
        manager.ensure_task_group(
            group_id=9, task_type="SA_THREAT_RESPONSE", user_id="legacy", expected_task_count=1,
            difficulty="low", autonomy_level="L1", is_ai_active=True,
        )
        result = manager.get_ai_accuracy(9)
        assert result["algorithm_version"] == "legacy_untracked"
        assert result["sampled_probability"] is None
        assert result["actual_accuracy"] is None
        assert result["audit_complete"] is False
    finally:
        manager.shutdown()


def test_semantic_target_mismatch_marks_audit_incomplete(tmp_path):
    manager = DatabaseManager(str(tmp_path / "semantic-mismatch.db"))
    try:
        manager.initialize_database()
        manager.ensure_task_group(
            group_id=30, task_type="RADAR_TARGETING", user_id="pilot",
            expected_task_count=1, difficulty="high", autonomy_level="L2",
            is_ai_active=True,
        )
        group_context = build_group_accuracy(
            accuracy_config(), user_id="pilot", task_type="RADAR_TARGETING",
            task_group_id=30, ai_level="L2", difficulty="high",
        )
        manager.save_task_group_ai_accuracy(30, group_context)
        manager.ensure_task_run(
            task_id=301, task_type="RADAR_TARGETING", user_id="pilot",
            group_id=30, task_seq=1,
        )
        manager.record_operation({
            "task_id": 301,
            "operationType": "target_selected",
            "timestamp": 1001,
            "isActive": True,
            "parameters": {
                "target_id": "enemy-1",
                "is_correct": True,
                "ai_decision": {
                    **group_context,
                    "selected_pool": ["friend-1"],
                    "actual_selection": "enemy-1",
                    "is_correct": True,
                },
            },
            "user_id": "pilot",
            "event_owner": "AI",
        }, False, wait_for_commit=True)

        result = manager.get_ai_accuracy(30)
        assert result["semantic_mismatch_task_ids"] == [301]
        assert result["semantic_mismatch_count"] == 1
        assert result["audit_complete"] is False
    finally:
        manager.shutdown()


def test_existing_task_groups_schema_gets_nullable_accuracy_columns(tmp_path):
    db_path = tmp_path / "migration.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE task_groups (
                group_id INTEGER PRIMARY KEY, task_type TEXT, user_id TEXT,
                status TEXT, started_at_ms INTEGER
            )
        """)
    manager = DatabaseManager(str(db_path))
    try:
        manager.initialize_database()
        with manager.get_connection() as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(task_groups)")}
        assert {
            "ai_probability_min", "ai_probability_max", "sampled_ai_probability",
            "ai_probability_seed", "ai_accuracy_algorithm",
        } <= columns
    finally:
        manager.shutdown()


def test_ai_accuracy_http_validation_and_not_found(monkeypatch):
    server = HTTPServer.__new__(HTTPServer)
    server.logger = SimpleNamespace(error=lambda *_args, **_kwargs: None)

    missing = asyncio.run(server.ai_accuracy_handler(SimpleNamespace(query={})))
    assert missing.status == 400
    invalid = asyncio.run(server.ai_accuracy_handler(SimpleNamespace(query={"task_group_id": "x"})))
    assert invalid.status == 400

    handler_db_manager = HTTPServer.ai_accuracy_handler.__globals__["db_manager"]
    monkeypatch.setattr(handler_db_manager, "get_ai_accuracy", lambda *_args: None)
    absent = asyncio.run(server.ai_accuracy_handler(SimpleNamespace(query={"task_group_id": "999"})))
    assert absent.status == 404
