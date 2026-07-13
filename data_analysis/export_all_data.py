from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "server" / "data" / "radar_operations.db"
DEFAULT_OUTPUT = REPO_ROOT / "data_analysis" / "output" / "all_data.db"
DEFAULT_REPORT = REPO_ROOT / "data_analysis" / "output" / "quality_report.json"

QUESTIONNAIRE_TASK_MAP = {
    "RADAR_TARGETING": "sensor",
    "SA_THREAT_RESPONSE": "threat",
    "PLATFORM_CONTROL": "platform",
    "WEAPON_FIRING": "weapon",
    "WEAPON_LAUNCH": "weapon",
}

RUNTIME_TASK_MAP = {
    "RADAR_TARGETING": "sensor",
    "SA_THREAT_RESPONSE": "threat",
    "PLATFORM_CONTROL": "platform",
    "WEAPON_FIRING": "weapon",
    "WEAPON_LAUNCH": "weapon",
}

QUESTIONNAIRE_TO_RUNTIME_TASK = {
    "RADAR_TARGETING": "RADAR_TARGETING",
    "SA_THREAT_RESPONSE": "SA_THREAT_RESPONSE",
    "PLATFORM_CONTROL": "PLATFORM_CONTROL",
    "WEAPON_FIRING": "WEAPON_FIRING",
    "WEAPON_LAUNCH": "WEAPON_FIRING",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export server/data/radar_operations.db to an SFY-style all_data.db."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def parse_json(raw: Any, default: Any = None) -> Any:
    if raw is None:
        return {} if default is None else default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {} if default is None else default


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "ai"}


def bool_text(value: Any) -> str | None:
    if value is None:
        return None
    return "true" if truthy(value) else "false"


def audio_text(value: Any) -> str | None:
    if value is None:
        return None
    return "1" if truthy(value) else "0"


def ai_level_for_row(is_ai_active: Any, level: Any) -> str | None:
    if not truthy(is_ai_active):
        return None
    return str(level) if level is not None else None


def ms_delta(end_ms: Any, start_ms: Any) -> int | None:
    if end_ms is None or start_ms is None:
        return None
    try:
        return int(end_ms) - int(start_ms)
    except (TypeError, ValueError):
        return None


def seconds_total(*values: Any) -> float:
    total = 0.0
    for value in values:
        try:
            total += float(value or 0)
        except (TypeError, ValueError):
            continue
    return total


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if not table_exists(conn, table_name):
        return set()
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")}


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE questionnaire_statistics (
            user_id TEXT,
            task_name TEXT,
            difficulty_level TEXT,
            ai_level TEXT,
            audio_enabled TEXT,
            q1_score INTEGER,
            q2_score INTEGER,
            q3_score INTEGER,
            q4_score INTEGER,
            q5_score INTEGER,
            q6_score INTEGER,
            q7_score INTEGER
        );

        CREATE TABLE sensor_task_statistics_plus (
            user_id TEXT,
            difficulty_level TEXT,
            ai_level TEXT,
            audio_enabled TEXT,
            repetition_count TEXT,
            radar_settings_time TEXT,
            antenna_settings_time TEXT,
            ai_select_time TEXT,
            ai_target_id TEXT,
            ai_is_correct TEXT,
            person_select_time TEXT,
            person_target_id TEXT,
            person_is_correct TEXT,
            total_task_time TEXT,
            selection_method TEXT
        );

        CREATE TABLE threat_task_statistics_plus (
            user_id TEXT,
            difficulty_level TEXT,
            ai_level TEXT,
            audio_enabled TEXT,
            repetition_count TEXT,
            ai_select_time TEXT,
            ai_target_id TEXT,
            ai_is_correct TEXT,
            person_select_time TEXT,
            person_target_id TEXT,
            person_is_correct TEXT,
            total_task_time TEXT,
            selection_method TEXT
        );

        CREATE TABLE platform_statistics (
            user_id TEXT,
            difficulty_level TEXT,
            ai_level TEXT,
            audio_enabled TEXT,
            repetition_count INTEGER,
            is_correct TEXT,
            current_mode TEXT,
            current_times REAL,
            distance REAL,
            ai_control_time REAL,
            person_control_time REAL
        );

        CREATE TABLE weapon_statistics (
            user_id TEXT,
            difficulty_level TEXT,
            ai_level TEXT,
            audio_enabled TEXT,
            repetition_count INTEGER,
            ai_remind_time REAL,
            current_times REAL,
            fire_result TEXT,
            ai_control_time REAL,
            person_control_time REAL
        );
        """
    )
    conn.commit()


def load_operations(src: sqlite3.Connection) -> dict[int, list[sqlite3.Row]]:
    operations: dict[int, list[sqlite3.Row]] = {}
    if not table_exists(src, "user_operations"):
        return operations
    for row in src.execute("SELECT * FROM user_operations ORDER BY task_id, timestamp, id"):
        operations.setdefault(int(row["task_id"]), []).append(row)
    return operations


def first_operation(rows: list[sqlite3.Row], operation_type: str) -> sqlite3.Row | None:
    return next((row for row in rows if row["operation_type"] == operation_type), None)


def last_operation(rows: list[sqlite3.Row], operation_type: str) -> sqlite3.Row | None:
    for row in reversed(rows):
        if row["operation_type"] == operation_type:
            return row
    return None


def last_operation_by_owner(rows: list[sqlite3.Row], operation_type: str, owner: str) -> sqlite3.Row | None:
    for row in reversed(rows):
        if row["operation_type"] == operation_type and str(row["event_owner"] or "") == owner:
            return row
    return None


def last_operation_not_owner(rows: list[sqlite3.Row], operation_type: str, owner: str) -> sqlite3.Row | None:
    for row in reversed(rows):
        if row["operation_type"] == operation_type and str(row["event_owner"] or "") != owner:
            return row
    return None


def latest_row(*rows: sqlite3.Row | None) -> sqlite3.Row | None:
    present = [row for row in rows if row is not None]
    if not present:
        return None
    return max(present, key=lambda row: int(row["timestamp"] or 0))


def operation_param(row: sqlite3.Row | None, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    params = parse_json(row["parameters"])
    return params.get(key, default) if isinstance(params, dict) else default


def export_sensor_and_threat(src: sqlite3.Connection, dst: sqlite3.Connection) -> dict[str, int]:
    counts = {"sensor_task_statistics_plus": 0, "threat_task_statistics_plus": 0}
    if not table_exists(src, "task_settings"):
        return counts

    operations = load_operations(src)
    rows = src.execute(
        """
        SELECT task_id, user_id, task_type, repetition_count, is_ai_active,
               ai_level_name, difficulty_name, audio_enabled
        FROM task_settings
        WHERE task_type IN ('RADAR_TARGETING', 'SA_THREAT_RESPONSE')
        ORDER BY task_id
        """
    ).fetchall()

    for setting in rows:
        task_id = int(setting["task_id"])
        ops = operations.get(task_id, [])
        common = {
            "user_id": setting["user_id"],
            "difficulty_level": setting["difficulty_name"],
            "ai_level": ai_level_for_row(setting["is_ai_active"], setting["ai_level_name"]),
            "audio_enabled": audio_text(setting["audio_enabled"]),
            "repetition_count": str(setting["repetition_count"]),
        }

        if setting["task_type"] == "RADAR_TARGETING":
            task_start = first_operation(ops, "task_start")
            settings_update = first_operation(ops, "settings_update")
            antenna = first_operation(ops, "antenna_adjusted")
            ai_target = last_operation_by_owner(ops, "target_selected", "AI")
            person_target = last_operation_not_owner(ops, "target_selected", "AI")
            final_target = latest_row(ai_target, person_target)
            final_owner = (final_target["event_owner"] if final_target else None) or None
            values = {
                **common,
                "radar_settings_time": ms_delta(settings_update["timestamp"], settings_update["receive_timestamp"])
                if settings_update else None,
                "antenna_settings_time": ms_delta(antenna["timestamp"], antenna["receive_timestamp"])
                if antenna else None,
                "ai_select_time": ms_delta(ai_target["timestamp"], ai_target["receive_timestamp"])
                if ai_target else None,
                "ai_target_id": operation_param(ai_target, "target_id"),
                "ai_is_correct": ai_target["is_correct"] if ai_target else None,
                "person_select_time": ms_delta(person_target["timestamp"], person_target["receive_timestamp"])
                if person_target else None,
                "person_target_id": operation_param(person_target, "target_id"),
                "person_is_correct": person_target["is_correct"] if person_target else None,
                "total_task_time": ms_delta(final_target["timestamp"], task_start["timestamp"])
                if final_target and task_start else None,
                "selection_method": final_owner,
            }
            dst.execute(
                """
                INSERT INTO sensor_task_statistics_plus VALUES (
                    :user_id, :difficulty_level, :ai_level, :audio_enabled, :repetition_count,
                    :radar_settings_time, :antenna_settings_time,
                    :ai_select_time, :ai_target_id, :ai_is_correct,
                    :person_select_time, :person_target_id, :person_is_correct,
                    :total_task_time, :selection_method
                )
                """,
                values,
            )
            counts["sensor_task_statistics_plus"] += 1

        if setting["task_type"] == "SA_THREAT_RESPONSE":
            task_start = first_operation(ops, "SwitchSA") or first_operation(ops, "ResetSA")
            ai_click = last_operation_by_owner(ops, "threat_clicked", "AI")
            person_click = last_operation_not_owner(ops, "threat_clicked", "AI")
            final_click = latest_row(ai_click, person_click)
            final_owner = (final_click["event_owner"] if final_click else None) or None
            values = {
                **common,
                "ai_select_time": ms_delta(ai_click["timestamp"], ai_click["receive_timestamp"])
                if ai_click else None,
                "ai_target_id": operation_param(ai_click, "threat_id"),
                "ai_is_correct": ai_click["is_correct"] if ai_click else None,
                "person_select_time": ms_delta(person_click["timestamp"], person_click["receive_timestamp"])
                if person_click else None,
                "person_target_id": operation_param(person_click, "threat_id"),
                "person_is_correct": person_click["is_correct"] if person_click else None,
                "total_task_time": ms_delta(final_click["timestamp"], task_start["timestamp"])
                if final_click and task_start else None,
                "selection_method": final_owner,
            }
            dst.execute(
                """
                INSERT INTO threat_task_statistics_plus VALUES (
                    :user_id, :difficulty_level, :ai_level, :audio_enabled, :repetition_count,
                    :ai_select_time, :ai_target_id, :ai_is_correct,
                    :person_select_time, :person_target_id, :person_is_correct,
                    :total_task_time, :selection_method
                )
                """,
                values,
            )
            counts["threat_task_statistics_plus"] += 1

    dst.commit()
    return counts


def normalized_from_config(raw_config: Any) -> dict[str, Any]:
    config = parse_json(raw_config)
    normalized = config.get("normalized") if isinstance(config, dict) else {}
    return normalized if isinstance(normalized, dict) else {}


def overall_task_id_from_config(raw_config: Any) -> int | None:
    config = parse_json(raw_config)
    if not isinstance(config, dict):
        return None
    value = config.get("overall_task_id")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def first_item(items: Any) -> dict[str, Any]:
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return items[0]
    return {}


def export_platform_and_weapon(src: sqlite3.Connection, dst: sqlite3.Connection) -> dict[str, int]:
    counts = {"platform_statistics": 0, "weapon_statistics": 0}
    if not (table_exists(src, "task_runs") and table_exists(src, "task_subtask_results")):
        return counts

    rows = src.execute(
        """
        SELECT tr.task_id, tr.task_type, tr.user_id, tr.config_json,
               sr.sub_task_seq, sr.result_json, sr.current_task_score,
               sr.ai_control_time, sr.person_control_time, sr.ai_remind_time
        FROM task_runs tr
        JOIN task_subtask_results sr ON sr.task_id = tr.task_id
        WHERE tr.task_type IN ('PLATFORM_CONTROL', 'WEAPON_FIRING', 'WEAPON_LAUNCH')
        ORDER BY tr.task_id, sr.sub_task_seq
        """
    ).fetchall()

    for row in rows:
        normalized = normalized_from_config(row["config_json"])
        result = parse_json(row["result_json"])
        current_records = result.get("CurrentRedcord") if isinstance(result, dict) else []
        fire_records = result.get("Fire") if isinstance(result, dict) else []
        current_record = first_item(current_records)
        fire_record = first_item(fire_records)
        include_ai = normalized.get("include_ai")
        ai_level = ai_level_for_row(include_ai, normalized.get("current_level") or normalized.get("ai_autonomy_level"))
        common = {
            "user_id": row["user_id"],
            "difficulty_level": normalized.get("difficulty_key"),
            "ai_level": ai_level,
            "audio_enabled": audio_text(normalized.get("audio_enabled")),
            "repetition_count": int(row["sub_task_seq"] or 0),
            "ai_control_time": float(row["ai_control_time"] or 0),
            "person_control_time": float(row["person_control_time"] or 0),
        }

        if row["task_type"] == "PLATFORM_CONTROL":
            current_mode = result.get("ConfigControlMode") or current_record.get("CurrentMode") if isinstance(result, dict) else None
            dst.execute(
                """
                INSERT INTO platform_statistics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    common["user_id"],
                    common["difficulty_level"],
                    common["ai_level"],
                    common["audio_enabled"],
                    common["repetition_count"],
                    bool_text((row["current_task_score"] or 0) > 0),
                    current_mode,
                    seconds_total(row["ai_control_time"], row["person_control_time"]),
                    current_record.get("Distance"),
                    common["ai_control_time"],
                    common["person_control_time"],
                ),
            )
            counts["platform_statistics"] += 1

        if row["task_type"] in ("WEAPON_FIRING", "WEAPON_LAUNCH"):
            dst.execute(
                """
                INSERT INTO weapon_statistics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    common["user_id"],
                    common["difficulty_level"],
                    common["ai_level"],
                    common["audio_enabled"],
                    common["repetition_count"],
                    float(row["ai_remind_time"] or 0),
                    fire_record.get("CurrentTime") or seconds_total(row["ai_control_time"], row["person_control_time"]),
                    bool_text(fire_record.get("FireResult")),
                    common["ai_control_time"],
                    common["person_control_time"],
                ),
            )
            counts["weapon_statistics"] += 1

    dst.commit()
    return counts


def build_questionnaire_match_index(src: sqlite3.Connection) -> dict[tuple[str, str, int], dict[str, Any]]:
    index: dict[tuple[str, str, int], dict[str, Any]] = {}

    if table_exists(src, "task_settings"):
        for row in src.execute(
            """
            SELECT task_id, user_id, task_type, repetition_count, is_ai_active,
                   ai_level_name, difficulty_name, audio_enabled
            FROM task_settings
            ORDER BY task_id
            """
        ):
            runtime_task = row["task_type"]
            key = (row["user_id"], runtime_task, int(row["repetition_count"] or 0))
            candidate = {
                "task_id": row["task_id"],
                "runtime_task_type": runtime_task,
                "task_name": RUNTIME_TASK_MAP.get(runtime_task),
                "difficulty_level": row["difficulty_name"],
                "ai_level": ai_level_for_row(row["is_ai_active"], row["ai_level_name"]),
                "audio_enabled": audio_text(row["audio_enabled"]),
                "is_ai_active": truthy(row["is_ai_active"]),
                "source_table": "task_settings",
            }
            # Prefer AI rows when the same repetition has both manual and AI records.
            if key not in index or candidate["is_ai_active"]:
                index[key] = candidate

    if table_exists(src, "task_runs") and table_exists(src, "task_subtask_results"):
        for row in src.execute(
            """
            SELECT tr.task_id, tr.user_id, tr.task_type, tr.config_json, sr.sub_task_seq
            FROM task_runs tr
            JOIN task_subtask_results sr ON sr.task_id = tr.task_id
            ORDER BY tr.task_id, sr.sub_task_seq
            """
        ):
            runtime_task = row["task_type"]
            if runtime_task in ("PLATFORM_CONTROL", "WEAPON_FIRING", "WEAPON_LAUNCH") and overall_task_id_from_config(row["config_json"]) is None:
                continue
            normalized = normalized_from_config(row["config_json"])
            key = (row["user_id"], runtime_task, int(row["sub_task_seq"] or 0))
            candidate = {
                "task_id": row["task_id"],
                "runtime_task_type": runtime_task,
                "task_name": RUNTIME_TASK_MAP.get(runtime_task),
                "difficulty_level": normalized.get("difficulty_key"),
                "ai_level": ai_level_for_row(
                    normalized.get("include_ai"),
                    normalized.get("current_level") or normalized.get("ai_autonomy_level"),
                ),
                "audio_enabled": audio_text(normalized.get("audio_enabled")),
                "is_ai_active": truthy(normalized.get("include_ai")),
                "source_table": "task_runs",
            }
            if key not in index or candidate["is_ai_active"]:
                index[key] = candidate
            if runtime_task == "WEAPON_LAUNCH":
                legacy_key = (row["user_id"], "WEAPON_FIRING", int(row["sub_task_seq"] or 0))
                legacy_candidate = {**candidate, "runtime_task_type": "WEAPON_FIRING"}
                if legacy_key not in index or legacy_candidate["is_ai_active"]:
                    index[legacy_key] = legacy_candidate

    return index


def build_questionnaire_task_id_index(src: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    index: dict[int, dict[str, Any]] = {}

    if table_exists(src, "task_settings"):
        for row in src.execute(
            """
            SELECT task_id, user_id, task_type, is_ai_active,
                   ai_level_name, difficulty_name, audio_enabled
            FROM task_settings
            ORDER BY task_id
            """
        ):
            runtime_task = row["task_type"]
            index[int(row["task_id"])] = {
                "task_id": row["task_id"],
                "runtime_task_type": runtime_task,
                "task_name": RUNTIME_TASK_MAP.get(runtime_task),
                "difficulty_level": row["difficulty_name"],
                "ai_level": ai_level_for_row(row["is_ai_active"], row["ai_level_name"]),
                "audio_enabled": audio_text(row["audio_enabled"]),
                "is_ai_active": truthy(row["is_ai_active"]),
                "source_table": "task_settings",
            }

    if table_exists(src, "task_runs"):
        for row in src.execute(
            """
            SELECT task_id, user_id, task_type, config_json
            FROM task_runs
            ORDER BY task_id
            """
        ):
            runtime_task = QUESTIONNAIRE_TO_RUNTIME_TASK.get(row["task_type"], row["task_type"])
            if runtime_task in ("PLATFORM_CONTROL", "WEAPON_FIRING") and overall_task_id_from_config(row["config_json"]) is None:
                continue
            normalized = normalized_from_config(row["config_json"])
            index[int(row["task_id"])] = {
                "task_id": row["task_id"],
                "runtime_task_type": runtime_task,
                "task_name": RUNTIME_TASK_MAP.get(runtime_task),
                "difficulty_level": normalized.get("difficulty_key"),
                "ai_level": ai_level_for_row(
                    normalized.get("include_ai"),
                    normalized.get("current_level") or normalized.get("ai_autonomy_level"),
                ),
                "audio_enabled": audio_text(normalized.get("audio_enabled")),
                "is_ai_active": truthy(normalized.get("include_ai")),
                "source_table": "task_runs",
            }

    return index


def answer_score(answers: dict[str, Any], index: int) -> int | None:
    value = answers.get(str(index), answers.get(index))
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def export_questionnaires(src: sqlite3.Connection, dst: sqlite3.Connection) -> tuple[int, list[dict[str, Any]]]:
    if not table_exists(src, "questionnaire_responses"):
        return 0, []

    match_index = build_questionnaire_match_index(src)
    task_id_index = build_questionnaire_task_id_index(src)
    questionnaire_columns = table_columns(src, "questionnaire_responses")
    report_rows: list[dict[str, Any]] = []
    inserted = 0

    for row in src.execute("SELECT * FROM questionnaire_responses ORDER BY id"):
        questionnaire_task = row["task_type"]
        runtime_task = QUESTIONNAIRE_TO_RUNTIME_TASK.get(questionnaire_task, questionnaire_task)
        repetition = int(row["repetition_current"] or 0)
        key = (row["user_id"], runtime_task, repetition)
        row_task_id = row["task_id"] if "task_id" in questionnaire_columns else None
        match = task_id_index.get(int(row_task_id)) if row_task_id else None
        if not match:
            match = match_index.get(key)
        report = {
            "questionnaire_id": row["id"],
            "user_id": row["user_id"],
            "questionnaire_task_type": questionnaire_task,
            "runtime_task_type": runtime_task,
            "repetition_current": repetition,
            "source": row["source"],
            "questionnaire_is_practice_ignored": row["is_practice"],
            "status": "unmatched",
            "matched_task_id": None,
        }

        if not match or not match.get("task_name"):
            report_rows.append(report)
            continue

        answers = parse_json(row["answers_json"])
        values = (
            row["user_id"],
            match["task_name"],
            match["difficulty_level"],
            match["ai_level"],
            match["audio_enabled"],
            answer_score(answers, 1),
            answer_score(answers, 2),
            answer_score(answers, 3),
            answer_score(answers, 4),
            answer_score(answers, 5),
            answer_score(answers, 6),
            answer_score(answers, 7),
        )
        dst.execute("INSERT INTO questionnaire_statistics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
        inserted += 1
        report["status"] = "matched"
        report["matched_task_id"] = match["task_id"]
        report["matched_source_table"] = match["source_table"]
        report["resolved_difficulty_level"] = match["difficulty_level"]
        report["resolved_ai_level"] = match["ai_level"]
        report["resolved_audio_enabled"] = match["audio_enabled"]
        report_rows.append(report)

    dst.commit()
    return inserted, report_rows


def write_report(
    report_path: Path,
    source: Path,
    output: Path,
    table_counts: dict[str, int],
    questionnaire_rows: list[dict[str, Any]],
) -> None:
    matched = [row for row in questionnaire_rows if row["status"] == "matched"]
    unmatched = [row for row in questionnaire_rows if row["status"] != "matched"]
    report = {
        "source_db": str(source),
        "output_db": str(output),
        "table_counts": table_counts,
        "questionnaire_matching": {
            "total": len(questionnaire_rows),
            "matched": len(matched),
            "unmatched": len(unmatched),
            "rules": [
                "questionnaire_responses.is_practice is ignored",
                "questionnaire_responses.task_id matches task_runs/task_settings first when present",
                "radar/SA match user_id + task_type + repetition_current to task_settings",
                "platform/weapon match user_id + task_type + repetition_current to task_runs + task_subtask_results",
                "legacy WEAPON_LAUNCH rows normalize to WEAPON_FIRING",
            ],
            "rows": questionnaire_rows,
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def export_database(source: Path, output: Path, report: Path, overwrite: bool = False) -> dict[str, Any]:
    source = source.resolve()
    output = output.resolve()
    report = report.resolve()

    if not source.exists():
        raise FileNotFoundError(source)
    if output.exists() and not overwrite:
        raise FileExistsError(f"{output} exists; pass overwrite=True to replace it")

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with connect(source) as src, connect(output) as dst:
        create_schema(dst)
        table_counts: dict[str, int] = {}
        table_counts.update(export_sensor_and_threat(src, dst))
        table_counts.update(export_platform_and_weapon(src, dst))
        questionnaire_count, questionnaire_rows = export_questionnaires(src, dst)
        table_counts["questionnaire_statistics"] = questionnaire_count

    write_report(report, source, output, table_counts, questionnaire_rows)

    matched = sum(1 for row in questionnaire_rows if row["status"] == "matched")
    unmatched = len(questionnaire_rows) - matched
    return {
        "source_db": str(source),
        "output_db": str(output),
        "report": str(report),
        "tables": table_counts,
        "questionnaires": {
            "total": len(questionnaire_rows),
            "matched": matched,
            "unmatched": unmatched,
        },
    }


def main() -> int:
    args = parse_args()
    result = export_database(args.source, args.output, args.report, overwrite=args.overwrite)

    print(f"exported: {result['output_db']}")
    print(f"report:   {result['report']}")
    print(
        "questionnaires: "
        f"matched={result['questionnaires']['matched']} "
        f"unmatched={result['questionnaires']['unmatched']}"
    )
    for table, count in sorted(result["tables"].items()):
        print(f"{table}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
