"""Deterministic AI-accuracy sampling shared by Radar and SA tasks."""

from __future__ import annotations

import hashlib
import json
import random
from typing import Any, Dict, Mapping, Sequence, Tuple


DEFAULT_ALGORITHM_VERSION = "difficulty-group-range-v1"
DEFAULT_BASE_SEED = 20260807
SELECTION_PROTOCOL_VERSION = "server-authoritative-target-v1"
VALID_DIFFICULTIES = {"low", "medium", "high"}


class AIAccuracyConfigError(ValueError):
    """Raised when an active AI task has no usable probability configuration."""


def _stable_seed(*parts: Any) -> int:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).digest()
    # SQLite INTEGER is signed, so preserve the complete first 64-bit pattern
    # using its two's-complement signed representation.
    return int.from_bytes(digest[:8], "big", signed=True)


def _rng_from_seed(seed: int) -> random.Random:
    return random.Random(seed & ((1 << 64) - 1))


def _validate_range(values: Any, label: str) -> Tuple[float, float]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise AIAccuracyConfigError(f"{label} must be a one- or two-number array")
    if len(values) not in (1, 2):
        raise AIAccuracyConfigError(f"{label} must contain one or two values")
    try:
        minimum = float(values[0])
        maximum = minimum if len(values) == 1 else float(values[1])
    except (TypeError, ValueError, OverflowError) as exc:
        raise AIAccuracyConfigError(f"{label} contains a non-numeric value") from exc
    if not (0.0 <= minimum <= maximum <= 1.0):
        raise AIAccuracyConfigError(f"{label} must satisfy 0 <= min <= max <= 1")
    return minimum, maximum


def resolve_probability_range(
    config: Mapping[str, Any], ai_level: str, difficulty: str
) -> Tuple[float, float]:
    difficulty = str(difficulty or "").strip().lower()
    if difficulty not in VALID_DIFFICULTIES:
        raise AIAccuracyConfigError(f"unsupported difficulty: {difficulty or '<empty>'}")
    levels = config.get("levels")
    if not isinstance(levels, list):
        raise AIAccuracyConfigError("levels must be an array")
    level = next(
        (item for item in levels if isinstance(item, dict) and item.get("level") == ai_level),
        None,
    )
    if level is None:
        raise AIAccuracyConfigError(f"unknown AI level: {ai_level or '<empty>'}")

    by_difficulty = level.get("decision_probability_ranges_by_difficulty")
    if by_difficulty is not None:
        if not isinstance(by_difficulty, dict) or difficulty not in by_difficulty:
            raise AIAccuracyConfigError(
                f"missing decision probability range for {ai_level}/{difficulty}"
            )
        return _validate_range(
            by_difficulty[difficulty],
            f"decision_probability_ranges_by_difficulty.{difficulty}",
        )

    if "decision_probabilities" not in level:
        raise AIAccuracyConfigError(f"missing decision probability config for {ai_level}")
    return _validate_range(level.get("decision_probabilities"), "decision_probabilities")


def build_group_accuracy(
    config: Mapping[str, Any],
    *,
    user_id: str,
    task_type: str,
    task_group_id: int,
    ai_level: str,
    difficulty: str,
) -> Dict[str, Any]:
    accuracy_config = config.get("ai_accuracy") or {}
    if not isinstance(accuracy_config, dict):
        raise AIAccuracyConfigError("ai_accuracy must be an object")
    algorithm_version = str(
        accuracy_config.get("algorithm_version") or DEFAULT_ALGORITHM_VERSION
    )
    if algorithm_version != DEFAULT_ALGORITHM_VERSION:
        raise AIAccuracyConfigError(
            f"unsupported ai_accuracy.algorithm_version: {algorithm_version}"
        )
    try:
        base_seed = int(accuracy_config.get("base_seed", DEFAULT_BASE_SEED))
    except (TypeError, ValueError, OverflowError) as exc:
        raise AIAccuracyConfigError("ai_accuracy.base_seed must be an integer") from exc

    minimum, maximum = resolve_probability_range(config, ai_level, difficulty)
    probability_seed = _stable_seed(
        base_seed,
        user_id,
        task_type,
        int(task_group_id),
        ai_level,
        difficulty,
        algorithm_version,
    )
    probability_random = _rng_from_seed(probability_seed).random()
    sampled_probability = round(
        minimum + probability_random * (maximum - minimum), 2
    )
    return {
        "algorithm_version": algorithm_version,
        "task_group_id": int(task_group_id),
        "ai_level": ai_level,
        "difficulty": difficulty,
        "probability_range": [minimum, maximum],
        "probability_seed": probability_seed,
        "probability_random": probability_random,
        "sampled_probability": sampled_probability,
    }


def build_task_decision(
    group_accuracy: Mapping[str, Any],
    *,
    task_id: int,
    task_seq: int,
    task_type: str,
) -> Dict[str, Any]:
    probability_seed = int(group_accuracy["probability_seed"])
    decision_seed = _stable_seed(probability_seed, int(task_id), int(task_seq), task_type)
    rng = _rng_from_seed(decision_seed)
    decision_random = rng.random()
    pool_random = rng.random()
    sampled_probability = float(group_accuracy["sampled_probability"])
    return {
        "task_id": int(task_id),
        "task_seq": int(task_seq),
        "decision_seed": decision_seed,
        "decision_random": decision_random,
        "pool_random": pool_random,
        "intended_correct": decision_random < sampled_probability,
    }


def bind_task_decision_selection(
    decision: Mapping[str, Any],
    *,
    correct_pool: Sequence[Any],
    incorrect_pool: Sequence[Any],
    correct_pool_empty_reason: str,
    incorrect_pool_empty_reason: str,
) -> Dict[str, Any]:
    """Bind a task decision to one canonical server-owned target.

    Pools are sorted by identifier before applying ``pool_random`` so frontend
    ordering cannot change the selected target.  When the intended pool is
    empty, the opposite pool is used and the fallback is made auditable.
    """
    normalized_correct = sorted(
        {str(item) for item in correct_pool if item is not None}
    )
    normalized_incorrect = sorted(
        {str(item) for item in incorrect_pool if item is not None}
    )
    intended_correct = bool(decision.get("intended_correct"))
    selected_pool = normalized_correct if intended_correct else normalized_incorrect
    fallback_reason = None
    if not selected_pool:
        selected_pool = normalized_incorrect if intended_correct else normalized_correct
        fallback_reason = (
            correct_pool_empty_reason
            if intended_correct
            else incorrect_pool_empty_reason
        )

    try:
        pool_random = float(decision.get("pool_random", 0.0))
    except (TypeError, ValueError, OverflowError):
        pool_random = 0.0
    pool_random = min(max(pool_random, 0.0), 1.0 - 2.220446049250313e-16)
    pool_index = int(pool_random * len(selected_pool)) if selected_pool else None
    expected_target_id = (
        selected_pool[pool_index] if pool_index is not None else None
    )
    return {
        **dict(decision),
        "selection_protocol": SELECTION_PROTOCOL_VERSION,
        "selected_pool": selected_pool,
        "fallback_reason": fallback_reason,
        "pool_index": pool_index,
        "expected_target_id": expected_target_id,
    }


def group_accuracy_from_row(row: Mapping[str, Any]) -> Dict[str, Any] | None:
    required = (
        "ai_probability_min",
        "ai_probability_max",
        "sampled_ai_probability",
        "ai_probability_seed",
        "ai_accuracy_algorithm",
    )
    if any(row.get(key) is None for key in required):
        return None
    config_json = row.get("config_json")
    if isinstance(config_json, str):
        try:
            config_json = json.loads(config_json)
        except (TypeError, ValueError):
            config_json = {}
    persisted_context: Dict[str, Any] = {}
    if isinstance(config_json, dict):
        candidate = config_json.get("ai_accuracy") or {}
        if isinstance(candidate, dict):
            persisted_context = candidate
    return {
        "algorithm_version": row["ai_accuracy_algorithm"],
        "task_group_id": int(row["group_id"]),
        "ai_level": persisted_context.get("ai_level") or row.get("autonomy_level"),
        "difficulty": persisted_context.get("difficulty") or row.get("difficulty"),
        "probability_range": [
            float(row["ai_probability_min"]),
            float(row["ai_probability_max"]),
        ],
        "probability_seed": int(row["ai_probability_seed"]),
        "probability_random": persisted_context.get("probability_random"),
        "sampled_probability": float(row["sampled_ai_probability"]),
    }
