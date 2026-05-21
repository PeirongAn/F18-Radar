"""Calculate gaze statistics for SA threat ranking tasks.

The script reads:
  - server/data/gaze/gaze_records.db
  - server/data/gaze/users/{user_id}/{YYYYMMDD}/{task_id}/raw_gaze.jsonl
  - server/data/radar_operations.db, when present, for task metadata

It outputs one row per gaze target visibility window.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
SERVER_DIR = SCRIPT_DIR.parent
DEFAULT_GAZE_DB = SERVER_DIR / "data" / "gaze" / "gaze_records.db"
DEFAULT_OPERATIONS_DB = SERVER_DIR / "data" / "radar_operations.db"
DEFAULT_TASK_NAME = "SA_THREAT_RESPONSE"


@dataclass(frozen=True)
class Frame:
    ts_us: int
    valid: bool
    in_region: bool


@dataclass(frozen=True)
class TargetWindow:
    target_window_id: int
    task_id: str
    user_id: str
    task_source: str
    task_name: str
    data_dir: str
    task_start_us: int | None
    task_end_us: int | None
    task_status: str
    target_appear_us: int
    target_disappear_us: int | None
    auto_closed: int
    bbox_json: str | None
    normalized_bbox_json: str | None


OUTPUT_FIELDS = [
    "target_window_id",
    "task_id",
    "user_id",
    "task_source",
    "is_ai_active",
    "ai_level",
    "difficulty",
    "audio_enabled",
    "repetition_count",
    "task_status",
    "target_appear_time_us",
    "target_disappear_time_us",
    "target_window_closed",
    "target_visible_ms",
    "look_at_target_ms",
    "look_ratio",
    "window_frame_count",
    "valid_frame_count",
    "in_region_frame_count",
    "valid_frame_ratio",
    "in_region_valid_ratio",
    "feedback_count",
    "selected_threat_id",
    "selected_threat_label",
    "selected_event_owner",
    "selected_is_correct",
    "threat_click_delta_ms",
    "raw_gaze_path",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate gaze dwell statistics for SA threat ranking target windows."
    )
    parser.add_argument("--gaze-db", type=Path, default=DEFAULT_GAZE_DB)
    parser.add_argument("--operations-db", type=Path, default=DEFAULT_OPERATIONS_DB)
    parser.add_argument("--task-name", default=DEFAULT_TASK_NAME)
    parser.add_argument("--task-id", action="append", help="Limit to one or more task ids.")
    parser.add_argument("--user-id", action="append", help="Limit to one or more user ids.")
    parser.add_argument(
        "--include-open",
        action="store_true",
        help="Include target windows without disappear_time_us by using task end or last raw frame time.",
    )
    parser.add_argument(
        "--max-gap-ms",
        type=float,
        default=100.0,
        help="Cap one frame interval at this many milliseconds when estimating dwell time.",
    )
    parser.add_argument(
        "--format",
        choices=("csv", "json"),
        default="csv",
        help="Output format.",
    )
    parser.add_argument("--output", type=Path, help="Output file. Defaults to stdout.")
    return parser.parse_args()


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(path)
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_target_windows(
    gaze_db: Path,
    task_name: str,
    task_ids: set[str] | None,
    user_ids: set[str] | None,
    include_open: bool,
) -> list[TargetWindow]:
    where = ["g.task_name = ?"]
    params: list[Any] = [task_name]

    if task_ids:
        where.append(f"gt.task_id IN ({','.join('?' for _ in task_ids)})")
        params.extend(sorted(task_ids))
    if user_ids:
        where.append(f"g.user_id IN ({','.join('?' for _ in user_ids)})")
        params.extend(sorted(user_ids))
    if not include_open:
        where.append("gt.disappear_time_us IS NOT NULL")

    sql = f"""
        SELECT
            gt.id AS target_window_id,
            gt.task_id,
            g.user_id,
            g.task_source,
            g.task_name,
            g.data_dir,
            g.start_time_us AS task_start_us,
            g.end_time_us AS task_end_us,
            g.status AS task_status,
            gt.appear_time_us AS target_appear_us,
            gt.disappear_time_us AS target_disappear_us,
            gt.auto_closed,
            gt.bbox_json,
            gt.normalized_bbox_json
        FROM gaze_targets gt
        JOIN gaze_tasks g ON g.task_id = gt.task_id
        WHERE {' AND '.join(where)}
        ORDER BY CAST(gt.task_id AS INTEGER), gt.appear_time_us, gt.id
    """

    with connect_readonly(gaze_db) as conn:
        return [TargetWindow(**dict(row)) for row in conn.execute(sql, params)]


def load_feedback_events(gaze_db: Path) -> dict[str, list[int]]:
    if not gaze_db.exists():
        return {}
    with connect_readonly(gaze_db) as conn:
        rows = conn.execute(
            "SELECT task_id, event_time_ms FROM gaze_feedback_events ORDER BY task_id, event_time_ms"
        ).fetchall()
    events: dict[str, list[int]] = {}
    for row in rows:
        events.setdefault(str(row["task_id"]), []).append(int(row["event_time_ms"]) * 1000)
    return events


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def load_task_settings(operations_db: Path) -> dict[str, dict[str, Any]]:
    if not operations_db.exists():
        return {}
    with connect_readonly(operations_db) as conn:
        if not table_exists(conn, "task_settings"):
            return {}
        rows = conn.execute(
            """
            SELECT task_id, is_ai_active, ai_level_name, difficulty_name,
                   audio_enabled, repetition_count, event_owner, task_type
            FROM task_settings
            """
        ).fetchall()
    return {str(row["task_id"]): dict(row) for row in rows}


def load_threat_clicks(operations_db: Path) -> dict[str, list[dict[str, Any]]]:
    if not operations_db.exists():
        return {}
    with connect_readonly(operations_db) as conn:
        if not table_exists(conn, "user_operations"):
            return {}
        rows = conn.execute(
            """
            SELECT task_id, timestamp, user_id, event_owner, parameters
            FROM user_operations
            WHERE operation_type = 'threat_clicked'
            ORDER BY task_id, timestamp
            """
        ).fetchall()

    clicks: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        params = parse_json_object(row["parameters"])
        task_id = str(row["task_id"])
        clicks.setdefault(task_id, []).append(
            {
                "timestamp_us": int(row["timestamp"]) * 1000,
                "user_id": row["user_id"],
                "event_owner": row["event_owner"],
                "parameters": params,
            }
        )
    return clicks


def parse_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def nearest_click(clicks: list[dict[str, Any]], appear_us: int) -> dict[str, Any] | None:
    if not clicks:
        return None
    return min(clicks, key=lambda item: abs(int(item["timestamp_us"]) - appear_us))


def load_frames(data_dir: str, task_id: str) -> list[Frame]:
    raw_path = Path(data_dir) / "raw_gaze.jsonl"
    if not raw_path.exists():
        return []

    frames: list[Frame] = []
    with raw_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(item.get("task_id")) != str(task_id):
                continue
            ts_us = item.get("ts_us")
            if not isinstance(ts_us, int):
                continue
            frames.append(
                Frame(
                    ts_us=ts_us,
                    valid=bool(item.get("valid")),
                    in_region=bool(item.get("in_region")),
                )
            )
    return sorted(frames, key=lambda frame: frame.ts_us)


def estimate_last_frame_delta_us(frames: list[Frame]) -> int:
    deltas = [
        next_frame.ts_us - frame.ts_us
        for frame, next_frame in zip(frames, frames[1:])
        if next_frame.ts_us > frame.ts_us
    ]
    if not deltas:
        return 0
    return int(median(deltas))


def last_frame_time_us(frames: list[Frame]) -> int | None:
    if not frames:
        return None
    return max(frame.ts_us for frame in frames)


def calculate_window_stats(
    frames: list[Frame],
    start_us: int,
    end_us: int,
    max_gap_us: int,
) -> dict[str, Any]:
    window_frame_count = 0
    valid_frame_count = 0
    in_region_frame_count = 0
    look_us = 0
    fallback_delta_us = estimate_last_frame_delta_us(frames)

    for index, frame in enumerate(frames):
        if start_us <= frame.ts_us < end_us:
            window_frame_count += 1
            if frame.valid:
                valid_frame_count += 1
            if frame.valid and frame.in_region:
                in_region_frame_count += 1

        if index + 1 < len(frames):
            next_ts_us = frames[index + 1].ts_us
        elif fallback_delta_us > 0:
            next_ts_us = frame.ts_us + fallback_delta_us
        else:
            continue

        if next_ts_us <= frame.ts_us:
            continue
        if max_gap_us > 0 and next_ts_us - frame.ts_us > max_gap_us:
            next_ts_us = frame.ts_us + max_gap_us

        if next_ts_us <= start_us or frame.ts_us >= end_us:
            continue

        if frame.valid and frame.in_region:
            overlap_start = max(frame.ts_us, start_us)
            overlap_end = min(next_ts_us, end_us)
            if overlap_end > overlap_start:
                look_us += overlap_end - overlap_start

    visible_us = max(0, end_us - start_us)
    look_ms = look_us / 1000.0
    visible_ms = visible_us / 1000.0
    return {
        "target_visible_ms": visible_ms,
        "look_at_target_ms": look_ms,
        "look_ratio": safe_ratio(look_ms, visible_ms),
        "window_frame_count": window_frame_count,
        "valid_frame_count": valid_frame_count,
        "in_region_frame_count": in_region_frame_count,
        "valid_frame_ratio": safe_ratio(valid_frame_count, window_frame_count),
        "in_region_valid_ratio": safe_ratio(in_region_frame_count, valid_frame_count),
    }


def safe_ratio(numerator: float | int, denominator: float | int) -> float:
    if not denominator:
        return 0.0
    return float(numerator) / float(denominator)


def feedback_count_in_window(feedback_events_us: Iterable[int], start_us: int, end_us: int) -> int:
    return sum(1 for event_us in feedback_events_us if start_us <= event_us < end_us)


def build_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    task_ids = set(args.task_id) if args.task_id else None
    user_ids = set(args.user_id) if args.user_id else None
    max_gap_us = int(args.max_gap_ms * 1000)

    windows = load_target_windows(
        args.gaze_db,
        args.task_name,
        task_ids,
        user_ids,
        args.include_open,
    )
    feedback_events = load_feedback_events(args.gaze_db)
    task_settings = load_task_settings(args.operations_db)
    threat_clicks = load_threat_clicks(args.operations_db)

    frame_cache: dict[str, list[Frame]] = {}
    output_rows: list[dict[str, Any]] = []

    for window in windows:
        if window.task_id not in frame_cache:
            frame_cache[window.task_id] = load_frames(window.data_dir, window.task_id)
        frames = frame_cache[window.task_id]

        end_us = window.target_disappear_us
        window_closed = end_us is not None
        if end_us is None and args.include_open:
            end_us = window.task_end_us or last_frame_time_us(frames)
        if end_us is None or end_us <= window.target_appear_us:
            continue

        stats = calculate_window_stats(
            frames,
            window.target_appear_us,
            int(end_us),
            max_gap_us,
        )

        settings = task_settings.get(window.task_id, {})
        click = nearest_click(threat_clicks.get(window.task_id, []), window.target_appear_us)
        click_params = click.get("parameters", {}) if click else {}
        click_delta_ms = ""
        if click:
            click_delta_ms = (int(click["timestamp_us"]) - window.target_appear_us) / 1000.0

        row = {
            "target_window_id": window.target_window_id,
            "task_id": window.task_id,
            "user_id": window.user_id,
            "task_source": window.task_source,
            "is_ai_active": settings.get("is_ai_active", ""),
            "ai_level": settings.get("ai_level_name", ""),
            "difficulty": settings.get("difficulty_name", ""),
            "audio_enabled": settings.get("audio_enabled", ""),
            "repetition_count": settings.get("repetition_count", ""),
            "task_status": window.task_status,
            "target_appear_time_us": window.target_appear_us,
            "target_disappear_time_us": end_us,
            "target_window_closed": int(window_closed),
            "feedback_count": feedback_count_in_window(
                feedback_events.get(window.task_id, []),
                window.target_appear_us,
                int(end_us),
            ),
            "selected_threat_id": click_params.get("threat_id", ""),
            "selected_threat_label": click_params.get("label", ""),
            "selected_event_owner": click.get("event_owner", "") if click else "",
            "selected_is_correct": click_params.get("is_correct", ""),
            "threat_click_delta_ms": click_delta_ms,
            "raw_gaze_path": str(Path(window.data_dir) / "raw_gaze.jsonl"),
        }
        row.update(stats)
        output_rows.append(round_row_values(row))

    return output_rows


def round_row_values(row: dict[str, Any]) -> dict[str, Any]:
    rounded = dict(row)
    for key in (
        "target_visible_ms",
        "look_at_target_ms",
        "look_ratio",
        "valid_frame_ratio",
        "in_region_valid_ratio",
        "threat_click_delta_ms",
    ):
        value = rounded.get(key)
        if isinstance(value, float):
            rounded[key] = round(value, 6)
    return rounded


def write_output(rows: list[dict[str, Any]], args: argparse.Namespace) -> None:
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fh = args.output.open("w", encoding="utf-8", newline="")
        close_fh = True
    else:
        fh = sys.stdout
        close_fh = False

    try:
        if args.format == "json":
            json.dump(rows, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
            return

        writer = csv.DictWriter(fh, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    finally:
        if close_fh:
            fh.close()


def main() -> int:
    args = parse_args()
    try:
        rows = build_rows(args)
        write_output(rows, args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
