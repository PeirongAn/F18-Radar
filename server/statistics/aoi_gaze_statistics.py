"""Offline analysis for versioned experiment AOIs.

Raw gaze frames and ``gaze_aoi_snapshots`` remain the authoritative data.  This
module produces reproducible derived JSON and optional aggregate CSV files.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SERVER_DIR = SCRIPT_DIR.parent
DEFAULT_GAZE_DB = SERVER_DIR / "data" / "gaze" / "gaze_records.db"
DEFAULT_OPERATIONS_DB = SERVER_DIR / "data" / "radar_operations.db"
DEFAULT_OUTPUT_DIR = SERVER_DIR / "data" / "gaze" / "derived"
ALGORITHM_VERSION = "aoi-ivt-v2"
AOI_PRIORITY = [
    "left_ai_target",
    "right_ai_history_accuracy",
    "right_detail",
    "right_comparison",
    "right_recommendation",
    "left_candidate_list",
    "right_candidate_list",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze versioned trust-control AOIs.")
    parser.add_argument("--gaze-db", type=Path, default=DEFAULT_GAZE_DB)
    parser.add_argument("--operations-db", type=Path, default=DEFAULT_OPERATIONS_DB)
    parser.add_argument("--task-id", action="append")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--summary-csv", type=Path)
    parser.add_argument("--max-gap-ms", type=float, default=100.0)
    parser.add_argument("--velocity-threshold-deg-s", type=float, default=30.0)
    parser.add_argument("--min-fixation-ms", type=float, default=100.0)
    return parser.parse_args()


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(path)
    conn = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_tasks(conn: sqlite3.Connection, task_ids: set[str] | None) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT task_id, user_id, task_source, task_name, data_dir, start_time_us, "
        "end_time_us, status, total_frames, valid_frames FROM gaze_tasks ORDER BY start_time_us"
    ).fetchall()
    return [dict(row) for row in rows if task_ids is None or str(row["task_id"]) in task_ids]


def load_snapshots(conn: sqlite3.Connection, task_id: str) -> dict[int, dict[str, Any]]:
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='gaze_aoi_snapshots'"
    ).fetchone()
    if not table:
        return {}
    rows = conn.execute(
        "SELECT snapshot_id, revision, valid_from_us, valid_to_us, alignment_valid, "
        "display_json, regions_json FROM gaze_aoi_snapshots "
        "WHERE task_id = ? ORDER BY revision",
        (task_id,),
    ).fetchall()
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        item["display"] = _json_object(item.pop("display_json", None))
        regions = _json_value(item.pop("regions_json", None), [])
        item["regions"] = regions if isinstance(regions, list) else []
        result[int(item["revision"])] = item
    return result


def load_frames(data_dir: str) -> list[dict[str, Any]]:
    raw_path = Path(data_dir) / "raw_gaze.jsonl"
    if not raw_path.exists():
        return []
    frames = []
    with raw_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(item, dict) and isinstance(item.get("ts_us"), int):
                frames.append(item)
    return sorted(frames, key=lambda frame: frame["ts_us"])


def load_analysis_window(
    operations_db: Path,
    task_id: str,
    fallback_start_us: int | None,
    fallback_end_us: int | None,
) -> tuple[int | None, int | None, str]:
    if operations_db.exists():
        with connect_readonly(operations_db) as conn:
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='task_events'"
            ).fetchone()
            if table:
                row = conn.execute(
                    "SELECT "
                    "MIN(CASE WHEN event_type='ai_recommendation_shown' THEN timestamp_ms END), "
                    "MAX(CASE WHEN event_type='final_selection_confirmed' THEN timestamp_ms END) "
                    "FROM task_events WHERE CAST(task_id AS TEXT) = ?",
                    (str(task_id),),
                ).fetchone()
                if row and row[0] is not None and row[1] is not None and row[1] >= row[0]:
                    return int(row[0]) * 1000, int(row[1]) * 1000, "decision_window"
    return fallback_start_us, fallback_end_us, "gaze_task_fallback"


def analyze_task(
    task: dict[str, Any],
    snapshots: dict[int, dict[str, Any]],
    frames: list[dict[str, Any]],
    window_start_us: int | None,
    window_end_us: int | None,
    *,
    max_gap_ms: float,
    velocity_threshold_deg_s: float,
    min_fixation_ms: float,
    window_source: str,
) -> dict[str, Any]:
    max_gap_us = int(max_gap_ms * 1000)
    if window_start_us is None and frames:
        window_start_us = frames[0]["ts_us"]
    if window_end_us is None and frames:
        window_end_us = frames[-1]["ts_us"]
    selected = [
        frame for frame in frames
        if window_start_us is not None
        and window_end_us is not None
        and window_start_us <= frame["ts_us"] <= window_end_us
    ]
    areas = _region_areas(snapshots)
    aoi_points: dict[str, list[list[Any]]] = defaultdict(list)
    aoi_dwell_us: Counter[str] = Counter()
    aoi_sample_count: Counter[str] = Counter()
    aoi_visits: Counter[str] = Counter()
    previous_hits: set[str] = set()
    alignment_invalid_us = 0

    for index, frame in enumerate(selected):
        ts_us = int(frame["ts_us"])
        next_ts_us = selected[index + 1]["ts_us"] if index + 1 < len(selected) else ts_us
        interval_us = max(0, min(max_gap_us, int(next_ts_us) - ts_us))
        revision = frame.get("aoi_revision")
        snapshot = snapshots.get(int(revision)) if isinstance(revision, int) else None
        if snapshot and not bool(snapshot.get("alignment_valid")):
            alignment_invalid_us += interval_us
        hits = {
            str(hit) for hit in frame.get("aoi_hits", [])
            if isinstance(hit, str)
        }
        gaze = frame.get("gaze")
        for hit in sorted(hits):
            aoi_sample_count[hit] += 1
            aoi_dwell_us[hit] += interval_us
            if isinstance(gaze, list) and len(gaze) >= 2:
                aoi_points[hit].append([ts_us, gaze[0], gaze[1], revision])
            if hit not in previous_hits:
                aoi_visits[hit] += 1
        previous_hits = hits

    fixations = detect_fixations(
        selected,
        areas,
        max_gap_us=max_gap_us,
        velocity_threshold_deg_s=velocity_threshold_deg_s,
        min_fixation_us=int(min_fixation_ms * 1000),
    )
    fixation_counts = Counter(
        fixation["aoi"] for fixation in fixations if fixation.get("aoi")
    )
    first_entry: dict[str, int] = {}
    for frame in selected:
        for hit in frame.get("aoi_hits", []):
            first_entry.setdefault(str(hit), int(frame["ts_us"]))
    all_ids = sorted({*AOI_PRIORITY, *aoi_points, *aoi_dwell_us, *fixation_counts})
    metrics = {
        aoi_id: {
            "raw_gaze_points": aoi_points.get(aoi_id, []),
            "valid_sample_count": int(aoi_sample_count[aoi_id]),
            "dwell_ms": aoi_dwell_us[aoi_id] / 1000.0,
            "fixation_count": int(fixation_counts[aoi_id]),
            "visit_count": int(aoi_visits[aoi_id]),
            "first_entry_latency_ms": (
                (first_entry[aoi_id] - window_start_us) / 1000.0
                if aoi_id in first_entry and window_start_us is not None else None
            ),
        }
        for aoi_id in all_ids
    }
    scanpath = build_scanpath(fixations)
    transitions: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for item in scanpath:
        if item.get("from_aoi") and item.get("to_aoi"):
            transitions[item["from_aoi"]][item["to_aoi"]] += 1
    valid_frames = sum(1 for frame in selected if frame.get("gaze") is not None)
    versioned_frames = sum(1 for frame in selected if isinstance(frame.get("aoi_revision"), int))
    return {
        "algorithm": {
            "name": "I-VT",
            "version": ALGORITHM_VERSION,
            "velocity_threshold_deg_s": velocity_threshold_deg_s,
            "min_fixation_ms": min_fixation_ms,
            "max_sample_gap_ms": max_gap_ms,
            "aoi_assignment": "majority_primary_hit",
        },
        "task": {
            "task_id": str(task.get("task_id")),
            "user_id": task.get("user_id"),
            "task_name": task.get("task_name"),
            "status": task.get("status"),
            "raw_gaze_path": str(Path(task.get("data_dir") or "") / "raw_gaze.jsonl"),
        },
        "analysis_window": {
            "start_us": window_start_us,
            "end_us": window_end_us,
            "source": window_source,
        },
        "quality": {
            "legacy_format": not bool(snapshots),
            "frame_count": len(selected),
            "valid_frame_count": valid_frames,
            "valid_frame_ratio": _ratio(valid_frames, len(selected)),
            "versioned_frame_count": versioned_frames,
            "versioned_frame_ratio": _ratio(versioned_frames, len(selected)),
            "alignment_invalid_ms": alignment_invalid_us / 1000.0,
            "fixation_input": "per_eye_3d_gaze_ray",
        },
        "aoi_metrics": metrics,
        "fixations": fixations,
        "scanpath": scanpath,
        "transition_matrix": {key: dict(value) for key, value in transitions.items()},
    }


def detect_fixations(
    frames: list[dict[str, Any]],
    region_areas: dict[tuple[int, str], float],
    *,
    max_gap_us: int,
    velocity_threshold_deg_s: float,
    min_fixation_us: int,
) -> list[dict[str, Any]]:
    usable = []
    for frame in frames:
        direction = _gaze_direction(frame)
        gaze = frame.get("gaze")
        if direction is not None and isinstance(gaze, list) and len(gaze) >= 2:
            usable.append((frame, direction))
    if len(usable) < 2:
        return []

    groups: list[list[tuple[dict[str, Any], tuple[float, float, float]]]] = []
    current = [usable[0]]
    for previous, item in zip(usable, usable[1:]):
        previous_frame, previous_direction = previous
        frame, direction = item
        gap_us = int(frame["ts_us"]) - int(previous_frame["ts_us"])
        velocity = math.inf
        if 0 < gap_us <= max_gap_us:
            velocity = _angle_deg(previous_direction, direction) / (gap_us / 1_000_000.0)
        if velocity <= velocity_threshold_deg_s:
            current.append(item)
        else:
            groups.append(current)
            current = [item]
    groups.append(current)

    fixations = []
    for group in groups:
        start_us = int(group[0][0]["ts_us"])
        end_us = int(group[-1][0]["ts_us"])
        if end_us - start_us < min_fixation_us:
            continue
        primary_hits = [
            _primary_aoi(frame, region_areas) for frame, _direction in group
        ]
        counts = Counter(hit for hit in primary_hits if hit)
        aoi = counts.most_common(1)[0][0] if counts else None
        centroid_x = sum(float(item[0]["gaze"][0]) for item in group) / len(group)
        centroid_y = sum(float(item[0]["gaze"][1]) for item in group) / len(group)
        mean_direction = _normalize_vector(tuple(
            sum(item[1][axis] for item in group) / len(group) for axis in range(3)
        ))
        fixations.append({
            "sequence": len(fixations) + 1,
            "start_us": start_us,
            "end_us": end_us,
            "duration_ms": (end_us - start_us) / 1000.0,
            "centroid": [centroid_x, centroid_y],
            "aoi": aoi,
            "sample_count": len(group),
            "direction": list(mean_direction) if mean_direction else None,
        })
    return fixations


def build_scanpath(fixations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for previous, current in zip(fixations, fixations[1:]):
        previous_direction = tuple(previous.get("direction") or ())
        current_direction = tuple(current.get("direction") or ())
        angular_distance = (
            _angle_deg(previous_direction, current_direction)
            if len(previous_direction) == 3 and len(current_direction) == 3 else None
        )
        result.append({
            "sequence": len(result) + 1,
            "from_fixation": previous["sequence"],
            "to_fixation": current["sequence"],
            "from_aoi": previous.get("aoi"),
            "to_aoi": current.get("aoi"),
            "start_us": previous["end_us"],
            "end_us": current["start_us"],
            "duration_ms": max(0, current["start_us"] - previous["end_us"]) / 1000.0,
            "angular_distance_deg": angular_distance,
            "from_centroid": previous["centroid"],
            "to_centroid": current["centroid"],
        })
    return result


def _gaze_direction(frame: dict[str, Any]) -> tuple[float, float, float] | None:
    directions = []
    for key in ("left_eye", "right_eye"):
        eye = frame.get(key)
        if not isinstance(eye, dict) or not eye.get("gaze_valid") or not eye.get("origin_valid"):
            continue
        point = eye.get("gaze_user_mm")
        origin = eye.get("origin_user_mm")
        if not _finite_xyz(point) or not _finite_xyz(origin):
            continue
        direction = _normalize_vector(tuple(float(point[i]) - float(origin[i]) for i in range(3)))
        if direction:
            directions.append(direction)
    if not directions:
        return None
    return _normalize_vector(tuple(
        sum(direction[axis] for direction in directions) / len(directions) for axis in range(3)
    ))


def _primary_aoi(frame: dict[str, Any], areas: dict[tuple[int, str], float]) -> str | None:
    hits = [str(hit) for hit in frame.get("aoi_hits", []) if isinstance(hit, str)]
    revision = frame.get("aoi_revision")
    if not hits:
        return None
    priority = {name: index for index, name in enumerate(AOI_PRIORITY)}
    return min(
        hits,
        key=lambda hit: (
            areas.get((int(revision), hit), math.inf) if isinstance(revision, int) else math.inf,
            priority.get(hit, len(priority)),
            hit,
        ),
    )


def _region_areas(snapshots: dict[int, dict[str, Any]]) -> dict[tuple[int, str], float]:
    result = {}
    for revision, snapshot in snapshots.items():
        for region in snapshot.get("regions", []):
            if not isinstance(region, dict) or region.get("shape") != "rect":
                continue
            try:
                area = max(0.0, float(region["right"]) - float(region["left"])) * max(
                    0.0, float(region["bottom"]) - float(region["top"])
                )
            except (KeyError, TypeError, ValueError):
                continue
            result[(revision, str(region.get("id")))] = area
    return result


def _finite_xyz(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= 3
        and all(isinstance(item, (int, float)) and math.isfinite(item) for item in value[:3])
    )


def _normalize_vector(value: tuple[float, ...]) -> tuple[float, float, float] | None:
    if len(value) != 3:
        return None
    length = math.sqrt(sum(component * component for component in value))
    if length <= 0 or not math.isfinite(length):
        return None
    return tuple(component / length for component in value)  # type: ignore[return-value]


def _angle_deg(first: tuple[float, ...], second: tuple[float, ...]) -> float:
    dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(first, second))))
    return math.degrees(math.acos(dot))


def _json_value(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default


def _json_object(raw: str | None) -> dict[str, Any]:
    value = _json_value(raw, {})
    return value if isinstance(value, dict) else {}


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def summary_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for result in results:
        for aoi_id, metrics in result["aoi_metrics"].items():
            rows.append({
                "task_id": result["task"]["task_id"],
                "user_id": result["task"]["user_id"],
                "task_name": result["task"]["task_name"],
                "aoi_id": aoi_id,
                "valid_sample_count": metrics["valid_sample_count"],
                "dwell_ms": metrics["dwell_ms"],
                "fixation_count": metrics["fixation_count"],
                "visit_count": metrics["visit_count"],
                "first_entry_latency_ms": metrics["first_entry_latency_ms"],
                "valid_frame_ratio": result["quality"]["valid_frame_ratio"],
                "alignment_invalid_ms": result["quality"]["alignment_invalid_ms"],
                "algorithm_version": result["algorithm"]["version"],
            })
    return rows


def main() -> int:
    args = parse_args()
    task_ids = set(args.task_id) if args.task_id else None
    with connect_readonly(args.gaze_db) as gaze_conn:
        tasks = load_tasks(gaze_conn, task_ids)
        results = []
        for task in tasks:
            task_id = str(task["task_id"])
            snapshots = load_snapshots(gaze_conn, task_id)
            frames = load_frames(task["data_dir"])
            window_start, window_end, window_source = load_analysis_window(
                args.operations_db,
                task_id,
                task.get("start_time_us"),
                task.get("end_time_us"),
            )
            result = analyze_task(
                task,
                snapshots,
                frames,
                window_start,
                window_end,
                max_gap_ms=args.max_gap_ms,
                velocity_threshold_deg_s=args.velocity_threshold_deg_s,
                min_fixation_ms=args.min_fixation_ms,
                window_source=window_source,
            )
            results.append(result)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for result in results:
        output = args.output_dir / f"{result['task']['task_id']}_aoi_gaze.json"
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.summary_csv:
        args.summary_csv.parent.mkdir(parents=True, exist_ok=True)
        rows = summary_rows(results)
        fields = list(rows[0]) if rows else ["task_id", "aoi_id"]
        with args.summary_csv.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    print(json.dumps({"tasks_analyzed": len(results), "output_dir": str(args.output_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
