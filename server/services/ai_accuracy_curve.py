"""Stable AI-level accuracy curves generated once at service startup."""

from __future__ import annotations

import hashlib
import math
import random
from statistics import fmean
from typing import Any, Dict, Iterable, Mapping, Optional


DEFAULT_CURVE_SEED = 20260730
DEFAULT_POINT_COUNT = 12
REQUIRED_AI_LEVELS = ("L1", "L2", "L3")
CURVE_SOURCE = "ai_level_probability_range"


class AccuracyCurveConfigError(ValueError):
    """Raised when AI-level probability ranges cannot produce valid curves."""


_curves: Dict[str, Dict[str, Any]] = {}
_curve_seed: Optional[int] = None


def normalize_ai_level(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    numeric_aliases = {
        "1": "L1",
        "1.0": "L1",
        "2": "L2",
        "2.0": "L2",
        "3": "L3",
        "3.0": "L3",
    }
    return numeric_aliases.get(normalized, normalized)


def _probability_bounds(probabilities: Optional[Iterable[Any]]) -> tuple[float, float]:
    values = []
    for value in probabilities or []:
        if isinstance(value, bool):
            raise AccuracyCurveConfigError("decision probability must be numeric, not boolean")
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise AccuracyCurveConfigError(
                f"decision probability is not numeric: {value!r}"
            ) from exc
        if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
            raise AccuracyCurveConfigError(
                f"decision probability must be within [0, 1]: {value!r}"
            )
        values.append(numeric)
    if not values:
        raise AccuracyCurveConfigError("decision_probabilities must not be empty")
    if len(values) > 2:
        raise AccuracyCurveConfigError(
            "decision_probabilities must contain one fixed value or two range bounds"
        )
    return min(values), max(values)


def calculate_expected_accuracy(probabilities: Optional[Iterable[Any]]) -> float:
    lower_bound, upper_bound = _probability_bounds(probabilities)
    return (lower_bound + upper_bound) / 2.0


def resolve_curve_seed(
    cli_seed: Optional[int],
    env_seed: Optional[str],
    default_seed: int = DEFAULT_CURVE_SEED,
) -> int:
    if cli_seed is not None:
        return int(cli_seed)
    if env_seed not in (None, ""):
        try:
            return int(str(env_seed).strip())
        except ValueError as exc:
            raise AccuracyCurveConfigError(
                f"AI_ACCURACY_CURVE_SEED must be an integer: {env_seed!r}"
            ) from exc
    return int(default_seed)


def _level_seed(seed: int, ai_level: str) -> int:
    digest = hashlib.sha256(f"{seed}:{ai_level}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


def _generate_series(
    lower_bound: float,
    upper_bound: float,
    *,
    ai_level: str,
    seed: int,
    point_count: int,
) -> list[float]:
    if point_count < 2:
        raise AccuracyCurveConfigError("accuracy curve point_count must be at least 2")

    mean = (lower_bound + upper_bound) / 2.0
    amplitude = (upper_bound - lower_bound) / 2.0
    if amplitude == 0:
        return [mean] * point_count

    rng = random.Random(_level_seed(seed, ai_level))
    phase1 = rng.uniform(0.0, math.tau)
    phase2 = rng.uniform(0.0, math.tau)
    raw_values = []
    for index in range(point_count):
        angle = math.tau * index / point_count
        raw_values.append(
            0.65 * math.sin(angle + phase1)
            + 0.25 * math.sin(2.0 * angle + phase2)
            + 0.10 * rng.uniform(-1.0, 1.0)
        )

    raw_mean = fmean(raw_values)
    centered = [value - raw_mean for value in raw_values]
    scale = max(abs(value) for value in centered)
    if scale == 0:
        return [mean] * point_count

    normalized = [value / scale for value in centered]
    series = [mean + amplitude * value for value in normalized]

    # Floating-point arithmetic may leave a minute residual. Applying the same
    # correction to every point keeps the configured mean exact without
    # changing the curve shape or exceeding its symmetric bounds.
    correction = mean - fmean(series)
    series = [value + correction for value in series]

    tolerance = 1e-12
    if any(
        value < lower_bound - tolerance or value > upper_bound + tolerance
        for value in series
    ):
        raise AccuracyCurveConfigError(
            f"generated {ai_level} curve exceeds configured probability bounds"
        )
    if not math.isclose(fmean(series), mean, rel_tol=0.0, abs_tol=1e-12):
        raise AccuracyCurveConfigError(
            f"generated {ai_level} curve mean does not match expected accuracy"
        )
    return series


def initialize_curves(
    ai_levels: Iterable[Mapping[str, Any]],
    seed: int,
    point_count: int = DEFAULT_POINT_COUNT,
) -> Dict[str, Dict[str, Any]]:
    levels_by_name: Dict[str, Mapping[str, Any]] = {}
    for level_config in ai_levels or []:
        if not isinstance(level_config, Mapping):
            raise AccuracyCurveConfigError("AI level configuration must be an object")
        ai_level = normalize_ai_level(level_config.get("level"))
        if ai_level in levels_by_name:
            raise AccuracyCurveConfigError(f"duplicate AI level configuration: {ai_level}")
        levels_by_name[ai_level] = level_config

    missing = [level for level in REQUIRED_AI_LEVELS if level not in levels_by_name]
    if missing:
        raise AccuracyCurveConfigError(
            f"missing AI level configuration: {', '.join(missing)}"
        )

    generated: Dict[str, Dict[str, Any]] = {}
    for ai_level in REQUIRED_AI_LEVELS:
        probabilities = levels_by_name[ai_level].get("decision_probabilities")
        lower_bound, upper_bound = _probability_bounds(probabilities)
        series = _generate_series(
            lower_bound,
            upper_bound,
            ai_level=ai_level,
            seed=int(seed),
            point_count=int(point_count),
        )
        generated[ai_level] = {
            "accuracy": fmean(series),
            "series": series,
            "ai_level": ai_level,
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "seed": int(seed),
            "source": CURVE_SOURCE,
        }

    global _curves, _curve_seed
    _curves = generated
    _curve_seed = int(seed)
    return {level: _copy_curve(curve) for level, curve in generated.items()}


def _copy_curve(curve: Mapping[str, Any]) -> Dict[str, Any]:
    copied = dict(curve)
    copied["series"] = list(curve.get("series") or [])
    return copied


def resolve_curve(ai_level: Any) -> Optional[Dict[str, Any]]:
    curve = _curves.get(normalize_ai_level(ai_level))
    return _copy_curve(curve) if curve is not None else None


def get_initialized_curves() -> Dict[str, Dict[str, Any]]:
    return {level: _copy_curve(curve) for level, curve in _curves.items()}


def get_curve_seed() -> Optional[int]:
    return _curve_seed
