"""Unified trust-control measurement helpers.

The classifier deliberately depends only on the AI recommendation, the human
final selection and ground truth.  Process data (gaze, focus, review, latency)
is stored separately and never changes the outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional


APPROPRIATE = "appropriate"
UNDER_TRUST = "under_trust"
OVER_TRUST = "over_trust"
STANDARD = "standard"
TRUST_SUPPORT = "trust_support"


def _identity(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("id", "target_id", "targetId", "value"):
            if value.get(key) is not None:
                return str(value[key])
    return "" if value is None else str(value)


def _identity_set(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set, frozenset)):
        return {identity for item in value if (identity := _identity(item))}
    identity = _identity(value)
    return {identity} if identity else set()


def classify_trust_outcome(
    ai_recommendation: Any,
    human_final_selection: Any,
    ground_truth: Any,
) -> Dict[str, Any]:
    """Return the trial truth-table result or raise for incomplete input."""
    ai_id = _identity(ai_recommendation)
    human_id = _identity(human_final_selection)
    truth_ids = _identity_set(ground_truth)
    if not ai_id or not human_id or not truth_ids:
        raise ValueError("ai_recommendation, human_final_selection and ground_truth are required")

    ai_correct = ai_id in truth_ids
    human_correct = human_id in truth_ids
    accepted_ai = human_id == ai_id
    if ai_correct:
        outcome = APPROPRIATE if accepted_ai else UNDER_TRUST
    else:
        outcome = OVER_TRUST if accepted_ai else APPROPRIATE
    return {
        "ai_correct": ai_correct,
        "human_correct": human_correct,
        "accepted_ai": accepted_ai,
        "trust_outcome": outcome,
    }


def summarize_outcomes(
    outcomes: Iterable[str],
    ai_correct_history: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    values = [value for value in outcomes if value in {APPROPRIATE, UNDER_TRUST, OVER_TRUST}]
    total = len(values)
    appropriate = values.count(APPROPRIATE)
    under = values.count(UNDER_TRUST)
    over = values.count(OVER_TRUST)
    divisor = total or 1
    ai_correct_values = [bool(value) for value in (ai_correct_history or [])]
    ai_history_valid_count = len(ai_correct_values)
    ai_history_correct_count = sum(ai_correct_values)
    running_correct = 0
    ai_history_accuracy_series = []
    for index, is_correct in enumerate(ai_correct_values, start=1):
        running_correct += int(is_correct)
        ai_history_accuracy_series.append(running_correct / index)
    return {
        "history_count": total,
        "ui_mode": TRUST_SUPPORT if under or over else STANDARD,
        "appropriate_rate": appropriate / divisor if total else 0.0,
        "under_trust_rate": under / divisor if total else 0.0,
        "over_trust_rate": over / divisor if total else 0.0,
        "direction_index": (under - over) / divisor if total else 0.0,
        "ai_history_accuracy": (
            ai_history_correct_count / ai_history_valid_count
            if ai_history_valid_count else None
        ),
        "ai_history_correct_count": ai_history_correct_count,
        "ai_history_valid_count": ai_history_valid_count,
        "ai_history_accuracy_series": ai_history_accuracy_series,
        "ai_history_correctness_series": ai_correct_values,
    }


def build_condition_key(
    task_group_id: Any,
    task_type: Any,
    difficulty: Any,
    ai_level: Any,
) -> Dict[str, Any]:
    return {
        "task_group_id": task_group_id,
        "task_type": str(task_type or ""),
        "difficulty": str(difficulty or ""),
        "ai_level": str(ai_level or ""),
    }


def build_trust_control_state(
    *,
    task_group_id: Any,
    task_type: Any,
    difficulty: Any,
    ai_level: Any,
    outcomes: Iterable[str],
    ai_correct_history: Optional[Iterable[Any]] = None,
    disclose_ai_reliability: bool = False,
) -> Dict[str, Any]:
    return {
        "condition_key": build_condition_key(task_group_id, task_type, difficulty, ai_level),
        **summarize_outcomes(outcomes, ai_correct_history),
        "disclose_ai_reliability": bool(disclose_ai_reliability),
    }
