import os
import sys
import tempfile


SERVER_DIR = os.path.dirname(os.path.dirname(__file__))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from managers.database_manager import DatabaseManager
from services.trust_control import (
    APPROPRIATE,
    OVER_TRUST,
    STANDARD,
    TRUST_SUPPORT,
    UNDER_TRUST,
    build_trust_control_state,
    classify_trust_outcome,
)


def test_trust_truth_table():
    assert classify_trust_outcome("A", "A", "A")["trust_outcome"] == APPROPRIATE
    assert classify_trust_outcome("A", "B", "A")["trust_outcome"] == UNDER_TRUST
    assert classify_trust_outcome("A", "B", "B")["trust_outcome"] == APPROPRIATE
    assert classify_trust_outcome("A", "A", "B")["trust_outcome"] == OVER_TRUST


def test_radar_truth_can_contain_multiple_correct_targets():
    truth = ["enemy-1", "enemy-2"]
    assert classify_trust_outcome("enemy-2", "friend-1", truth)["trust_outcome"] == UNDER_TRUST
    assert classify_trust_outcome("friend-1", "enemy-2", truth)["trust_outcome"] == APPROPRIATE
    assert classify_trust_outcome("friend-1", "friend-1", truth)["trust_outcome"] == OVER_TRUST


def test_ui_mode_uses_any_non_appropriate_history():
    first = build_trust_control_state(
        task_group_id=1, task_type="RADAR_TARGETING", difficulty="low",
        ai_level="L1", outcomes=[],
    )
    assert first["ui_mode"] == STANDARD
    assert first["history_count"] == 0

    appropriate = build_trust_control_state(
        task_group_id=1, task_type="RADAR_TARGETING", difficulty="low",
        ai_level="L1", outcomes=[APPROPRIATE, APPROPRIATE],
    )
    assert appropriate["ui_mode"] == STANDARD

    under = build_trust_control_state(
        task_group_id=1, task_type="RADAR_TARGETING", difficulty="low",
        ai_level="L1", outcomes=[APPROPRIATE, UNDER_TRUST],
    )
    over = build_trust_control_state(
        task_group_id=1, task_type="RADAR_TARGETING", difficulty="low",
        ai_level="L1", outcomes=[APPROPRIATE, OVER_TRUST],
    )
    assert under["ui_mode"] == over["ui_mode"] == TRUST_SUPPORT


def test_ai_history_accuracy_uses_prior_settled_trials():
    first = build_trust_control_state(
        task_group_id=1, task_type="RADAR_TARGETING", difficulty="low",
        ai_level="L1", outcomes=[], ai_correct_history=[],
    )
    assert first["ai_history_accuracy"] is None
    assert first["ai_history_correct_count"] == 0
    assert first["ai_history_valid_count"] == 0
    assert first["ai_history_accuracy_series"] == []
    assert first["ai_history_correctness_series"] == []

    history = build_trust_control_state(
        task_group_id=1, task_type="RADAR_TARGETING", difficulty="low",
        ai_level="L1", outcomes=[APPROPRIATE, OVER_TRUST],
        ai_correct_history=[True, False],
    )
    assert history["ai_history_accuracy"] == 0.5
    assert history["ai_history_correct_count"] == 1
    assert history["ai_history_valid_count"] == 2
    assert history["ai_history_accuracy_series"] == [1.0, 0.5]
    assert history["ai_history_correctness_series"] == [True, False]


def test_history_isolated_by_full_condition_key():
    with tempfile.TemporaryDirectory() as temp_dir:
        db = DatabaseManager(os.path.join(temp_dir, "trust.sqlite3"))
        # Keep this persistence test synchronous so schema creation cannot
        # race the manager's background WAL writer.
        db.shutdown()
        with db.get_connection() as conn:
            db._create_trust_trial_outcomes_table(conn.cursor(), conn)
        common = {
            "trial_id": "trial-1", "task_id": 11, "task_group_id": 7,
            "user_id": "pilot", "trial_sequence": 1,
            "task_type": "RADAR_TARGETING", "difficulty": "low", "ai_level": "L1",
            "ai_recommendation": "A", "human_final_selection": "A", "ground_truth": "A",
            "ai_correct": True, "human_correct": True, "accepted_ai": True,
            "trust_outcome": APPROPRIATE, "ui_mode": STANDARD, "history_count": 0,
            "trial_completed_at_ms": 100,
        }
        assert db.record_trust_trial_outcome(common) is True
        assert db.record_trust_trial_outcome(common) is False
        assert db.get_trust_outcomes(7, "RADAR_TARGETING", "low", "L1") == [APPROPRIATE]
        assert db.get_trust_history(7, "RADAR_TARGETING", "low", "L1") == [
            {"trust_outcome": APPROPRIATE, "ai_correct": True}
        ]
        assert db.get_trust_outcomes(7, "RADAR_TARGETING", "high", "L1") == []
        assert db.get_trust_outcomes(8, "RADAR_TARGETING", "low", "L1") == []


def test_group_performance_uses_settled_trials_and_process_events():
    with tempfile.TemporaryDirectory() as temp_dir:
        db = DatabaseManager(os.path.join(temp_dir, "performance.sqlite3"))
        db.shutdown()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            db._create_task_groups_table(cursor, conn)
            db._create_task_events_table(cursor, conn)
            db._create_trust_trial_outcomes_table(cursor, conn)
            cursor.execute(
                """
                INSERT INTO task_groups (
                    group_id, task_type, user_id, status, expected_task_count,
                    completed_task_count, started_at_ms, completed_at_ms
                ) VALUES (7, 'RADAR_TARGETING', 'pilot', 'completed', 1, 1, 1000, 5000)
                """
            )
            conn.commit()

        outcome = {
            "trial_id": "trial-performance", "task_id": 21, "task_group_id": 7,
            "user_id": "pilot", "trial_sequence": 1,
            "task_type": "RADAR_TARGETING", "difficulty": "low", "ai_level": "L1",
            "ai_recommendation": "A", "human_final_selection": "B", "ground_truth": "B",
            "ai_correct": False, "human_correct": True, "accepted_ai": False,
            "trust_outcome": APPROPRIATE, "ui_mode": STANDARD, "history_count": 0,
            "ai_recommendation_shown_at_ms": 1200,
            "final_selection_confirmed_at_ms": 1800,
            "trial_completed_at_ms": 2000,
        }
        assert db.record_trust_trial_outcome(outcome) is True
        db.record_task_event(
            task_id=21, task_type="RADAR_TARGETING", user_id="pilot",
            event_type="manual_review_started", timestamp_ms=1500,
            payload_json='{"target_id":"A","extra":{"valid":true,"review_session_id":"review-1"}}',
        )
        db.record_task_event(
            task_id=21, task_type="RADAR_TARGETING", user_id="pilot",
            event_type="manual_review_ended", timestamp_ms=1650,
            payload_json='{"target_id":"A","extra":{"duration_ms":150,"review_session_id":"review-1"}}',
        )
        db.record_task_event(
            task_id=21, task_type="RADAR_TARGETING", user_id="pilot",
            event_type="detail_hidden", timestamp_ms=1700,
            payload_json='{"target_id":"B","extra":{"exposure_duration_ms":250}}',
        )

        summary = db.get_trust_group_performance(7)
        assert summary["task_group_duration_ms"] == 4000
        assert summary["completion_rate"] == 1.0
        assert summary["human_accuracy"] == 1.0
        assert summary["ai_accuracy"] == 0.0
        assert summary["effective_decision_duration_ms"] == 600
        assert summary["valid_manual_review_count"] == 1
        assert summary["manual_review_used"] is True
        assert summary["manual_review_duration_ms"] == 150
        assert summary["detail_exposure_duration_ms"] == 250
