import json
import math
import os
import sys
from statistics import fmean

import pytest


SERVER_DIR = os.path.dirname(os.path.dirname(__file__))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from services.ai_accuracy_curve import (
    AccuracyCurveConfigError,
    calculate_expected_accuracy,
    initialize_curves,
    resolve_curve,
    resolve_curve_seed,
)
from core.message_handler import MessageHandler
from managers import db_manager


AI_LEVELS = [
    {"level": "L1", "decision_probabilities": [0.3, 0.5]},
    {"level": "L2", "decision_probabilities": [0.7, 0.9]},
    {"level": "L3", "decision_probabilities": [0.95, 1.0]},
]


def test_curves_are_stable_bounded_and_match_expected_means():
    first = initialize_curves(AI_LEVELS, seed=20260730)
    second = initialize_curves(AI_LEVELS, seed=20260730)

    assert first == second
    expected = {
        "L1": (0.3, 0.5, 0.4),
        "L2": (0.7, 0.9, 0.8),
        "L3": (0.95, 1.0, 0.975),
    }
    for ai_level, (lower, upper, mean) in expected.items():
        curve = first[ai_level]
        assert len(curve["series"]) == 12
        assert min(curve["series"]) >= lower - 1e-12
        assert max(curve["series"]) <= upper + 1e-12
        assert fmean(curve["series"]) == pytest.approx(mean, abs=1e-12)
        assert curve["accuracy"] == pytest.approx(mean, abs=1e-12)
        assert curve["source"] == "ai_level_probability_range"


def test_seed_changes_shape_without_changing_statistics():
    first = initialize_curves(AI_LEVELS, seed=1)
    second = initialize_curves(AI_LEVELS, seed=2)

    assert first["L1"]["series"] != second["L1"]["series"]
    assert fmean(first["L1"]["series"]) == pytest.approx(0.4)
    assert fmean(second["L1"]["series"]) == pytest.approx(0.4)


def test_curve_resolution_only_depends_on_ai_level():
    initialize_curves(AI_LEVELS, seed=9)
    canonical = resolve_curve("L2")

    assert resolve_curve("l2") == canonical
    assert resolve_curve("2") == canonical
    assert resolve_curve("2.0") == canonical
    assert resolve_curve("unknown") is None


def test_radar_and_sa_receive_the_same_curve_for_the_same_ai_level(monkeypatch):
    initialize_curves(AI_LEVELS, seed=9)
    monkeypatch.setattr(db_manager, "get_trust_history", lambda *_args: [])
    handler = MessageHandler()

    radar = handler._build_trust_control_state(
        1,
        "RADAR_TARGETING",
        {"difficulty_name": "high", "ai_level_name": "L2"},
        "pilot-a",
    )
    sa = handler._build_trust_control_state(
        2,
        "SA_THREAT_RESPONSE",
        {"difficulty_name": "low", "ai_level_name": "L2"},
        "pilot-b",
    )

    assert radar["condition_key"]["difficulty"] == "high"
    assert sa["condition_key"]["difficulty"] == "low"
    assert radar["ai_statistical_accuracy"] == sa["ai_statistical_accuracy"]
    assert radar["ai_statistical_accuracy_series"] == sa["ai_statistical_accuracy_series"]
    assert radar["ai_statistical_accuracy_curve_seed"] == 9


def test_seed_precedence_and_validation():
    assert resolve_curve_seed(11, "22") == 11
    assert resolve_curve_seed(None, "22") == 22
    assert resolve_curve_seed(None, None) == 20260730
    with pytest.raises(AccuracyCurveConfigError, match="must be an integer"):
        resolve_curve_seed(None, "not-an-integer")


def test_invalid_probability_configuration_is_rejected():
    with pytest.raises(AccuracyCurveConfigError, match="missing AI level"):
        initialize_curves(AI_LEVELS[:2], seed=1)
    with pytest.raises(AccuracyCurveConfigError, match=r"within \[0, 1\]"):
        initialize_curves(
            [
                *AI_LEVELS[:2],
                {"level": "L3", "decision_probabilities": [0.95, 1.1]},
            ],
            seed=1,
        )
    with pytest.raises(AccuracyCurveConfigError, match="at least 2"):
        initialize_curves(AI_LEVELS, seed=1, point_count=1)
    with pytest.raises(AccuracyCurveConfigError, match="one fixed value or two"):
        initialize_curves(
            [
                *AI_LEVELS[:2],
                {"level": "L3", "decision_probabilities": [0.95, 0.975, 1.0]},
            ],
            seed=1,
        )


def test_expected_accuracy_uses_probability_range_midpoint():
    assert calculate_expected_accuracy([0.3, 0.5]) == pytest.approx(0.4)
    assert calculate_expected_accuracy([1.0]) == pytest.approx(1.0)


def test_default_agent_config_uses_l3_fluctuation_range():
    config_path = os.path.abspath(
        os.path.join(SERVER_DIR, "..", "public", "agent_level.json")
    )
    with open(config_path, "r", encoding="utf-8") as config_file:
        config = json.load(config_file)
    l3_config = next(level for level in config["levels"] if level["level"] == "L3")

    assert l3_config["decision_probabilities"] == [0.95, 1.0]
    assert math.isclose(
        calculate_expected_accuracy(l3_config["decision_probabilities"]),
        0.975,
    )
