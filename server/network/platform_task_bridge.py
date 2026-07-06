"""
平台任务 WS：解析平台包、维护 pending、供 task_start 合并；platform_task 向其它连接广播 platform_task_config。
支持外部平台（平台控制 / 武器发射）的生命周期记录和结果存储。
"""
from __future__ import annotations

import copy
import json
import os
import time as _time
from typing import Any, Dict, List, Optional, Tuple

from managers import config_manager, db_manager, generate_task_id, get_logger

logger = get_logger("platform_task")

_pending: Optional[Dict[str, Any]] = None
_active_web_task_overlays: Dict[Tuple[str, str], Dict[str, Any]] = {}

# 外部任务活跃状态  key=(task_category, user_id)
_active_external_tasks: Dict[Tuple[str, str], Dict[str, Any]] = {}

_TASK_TYPE_BY_CATEGORY = {
    "radar": "RADAR_TARGETING",
    "sa": "SA_THREAT_RESPONSE",
    "platform_control": "PLATFORM_CONTROL",
    "weapon_launch": "WEAPON_LAUNCH",
}

_WEB_KIND_BY_TASK_TYPE = {
    "RADAR_TARGETING": "radar",
    "SA_THREAT_RESPONSE": "sa",
}

PUBLIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "public"))
INIT_CONFIG_PATH = os.path.join(PUBLIC_DIR, "init_config.json")


def _valid_levels(config: Dict[str, Any]) -> List[str]:
    return [lv.get("level") for lv in config.get("levels", []) if lv.get("level")]


def _normalize_current_level(raw: Any, config: Dict[str, Any]) -> str:
    valid = _valid_levels(config)
    default = config.get("current_level") or (valid[0] if valid else "L1")
    if raw is None or str(raw).strip() == "":
        return default
    s = str(raw).strip()
    if s in valid:
        return s
    su = s.upper()
    if su in valid:
        return su
    if len(s) >= 2 and s[0].upper() == "L" and s[1:].isdigit():
        cand = "L" + s[1:]
        if cand in valid or cand == "L3":
            return cand
    try:
        n = int(float(s))
        # External platform protocol: 1=L1, 2=L2, 3=L3.
        protocol_map = {
            1: "L1",
            2: "L2",
            3: "L3",
        }
        cand = protocol_map.get(n)
        if cand:
            return cand
    except ValueError:
        pass
    return default


def _normalize_difficulty_display_key(raw: Any, engine_key: str, task_category: Optional[str] = None) -> str:
    return engine_key


def _normalize_difficulty_key(raw: Any, config: Dict[str, Any], task_category: Optional[str] = None) -> str:
    gs = config.get("game_settings", {})
    diff_levels = gs.get("difficulty_levels", {}) or {}
    keys = list(diff_levels.keys())
    default = gs.get("current_difficulty") or (keys[0] if keys else "low")
    if raw is None or str(raw).strip() == "":
        return default if default in diff_levels else (keys[0] if keys else "low")
    s = str(raw).strip().lower()
    if s in diff_levels:
        return s
    try:
        n = int(float(s))
        # All external task categories use the same protocol: 1=high, 2=medium, 3=low.
        if n <= 1:
            pick = "high"
        elif n == 2:
            pick = "medium"
        else:  # n >= 3
            pick = "low"
        return pick
    except ValueError:
        pass
    if "低" in str(raw) or s == "low":
        return "low"
    if "中" in str(raw) or s == "medium":
        return "medium"
    if "高" in str(raw) or s == "high":
        return "high"
    return default if default in diff_levels else (keys[0] if keys else "low")


def _task_mode_to_include_ai(raw: Any) -> bool:
    if raw is None or str(raw).strip() == "":
        return True
    s = str(raw).strip().lower()
    if s in ("0", "false", "manual"):
        return False
    return True


def _infer_web_task_kind(message: Dict[str, Any]) -> str:
    """Web 单任务模式：radar | sa；空字符串表示由前端 init_config 决定。"""
    explicit = message.get("WebTaskKind") or message.get("web_task_kind")
    if explicit is not None and str(explicit).strip() != "":
        e = str(explicit).strip().lower()
        if e in ("sa", "sa_threat", "navigation", "threat", "sort", "threat_response"):
            return "sa"
        if e in ("radar", "sensor", "radar_targeting", "targeting"):
            return "radar"
    tn = str(message.get("TaskName") or "").lower()
    for token in ("威胁", "threat", "排序", "sa威胁", "situation"):
        if token in tn:
            return "sa"
    for token in ("传感器", "雷达", "radar", "目标", "targeting"):
        if token in tn:
            return "radar"
    return ""


def _classify_task_category(message: Dict[str, Any]) -> str:
    """根据 TaskName 关键词推断任务类别。"""
    tn = str(message.get("TaskName") or "").lower()
    for token in ("平台控制", "平台任务", "platform_control"):
        if token in tn:
            return "platform_control"
    for token in ("武器", "发射", "weapon", "fire", "launch"):
        if token in tn:
            return "weapon_launch"
    for token in ("威胁", "threat", "排序", "sa威胁", "situation"):
        if token in tn:
            return "sa"
    for token in ("传感器", "雷达", "radar", "目标", "targeting"):
        if token in tn:
            return "radar"
    return "unknown"


def _task_type_for_category(category: str) -> str:
    return _TASK_TYPE_BY_CATEGORY.get(category, "UNKNOWN")


def _web_kind_for_task_type(task_type: str) -> str:
    return _WEB_KIND_BY_TASK_TYPE.get(task_type, "")


def _web_kind_for_category(category: str) -> str:
    return _web_kind_for_task_type(_task_type_for_category(category))


def _is_web_overlay_category(category: str) -> bool:
    return category in ("radar", "sa")


def _build_overlay(normalized: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    gs = config.get("game_settings", {})
    diff_levels = gs.get("difficulty_levels", {}) or {}
    dkey = normalized["difficulty_key"]
    diff_conf = copy.deepcopy(diff_levels.get(dkey, {}))
    if not diff_conf:
        if dkey == "high":
            diff_conf = {"name": "高", "threat_count": 10, "target_count": 10}
        elif dkey == "medium":
            diff_conf = {"name": "中", "threat_count": 8, "target_count": 8}
        elif dkey == "low":
            diff_conf = {"name": "低", "threat_count": 5, "target_count": 5}
    diff_conf["difficulty_name"] = dkey

    level_name = normalized["current_level"]
    ai_conf = None
    for lv in config.get("levels", []):
        if lv.get("level") == level_name:
            ai_conf = copy.deepcopy(lv)
            break

    overlay: Dict[str, Any] = {
        "difficulty_name": dkey,
        "difficulty_display": normalized.get("difficulty_display") or dkey,
        "difficulty_config": diff_conf,
        "is_ai_active": normalized["include_ai"],
        "autonomy_level": level_name,
        "ai_level_name": level_name,
        "ai_level_config": ai_conf,
        "audio_enabled": gs.get("audio_enabled", True),
    }
    if normalized.get("repetition_total_override") is not None:
        overlay["repetition_total_override"] = normalized["repetition_total_override"]
    return overlay


def _normalize_platform_task_fields(
    message: Dict[str, Any],
    task_category: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Validate and normalize platform fields shared by all task categories."""
    task_id = message.get("ID")
    if task_id is None or str(task_id).strip() == "":
        raise ValueError("platform_task requires non-empty ID")

    cfg = config_manager.get_config()
    raw = {k: v for k, v in message.items() if k != "type"}

    ai_raw = message.get("AIAutonomyLevel")
    if ai_raw is None:
        ai_raw = message.get("AIAutonomyLeve")
    current_level = _normalize_current_level(ai_raw, cfg)
    web_task_kind = _infer_web_task_kind(message)
    difficulty_key = _normalize_difficulty_key(message.get("Difficulty"), cfg, task_category)
    difficulty_display = _normalize_difficulty_display_key(
        message.get("Difficulty"),
        difficulty_key,
        task_category,
    )
    # DefaultControlMode: "0"=人工(manual), "1"=AI
    include_ai = _task_mode_to_include_ai(message.get("DefaultControlMode"))
    # TaskMode: "0"=练习(practice), "1"=正式(formal)
    is_practice = str(message.get("TaskMode", "1")).strip() == "0"

    rep_override: Optional[int] = None
    tn = message.get("TaskNumber")
    if tn is not None and str(tn).strip() != "":
        try:
            rep_override = max(1, int(float(str(tn).strip())))
        except ValueError:
            rep_override = None

    if web_task_kind == "sa":
        task_type = "SA_THREAT_RESPONSE"
        task_category = "sa"
    elif web_task_kind == "radar":
        task_type = "RADAR_TARGETING"
        task_category = "radar"
    else:
        task_type = None
        task_category = None

    normalized = {
        "task_name": message.get("TaskName"),
        "platform_task_id": message.get("ID"),
        "task_type": task_type,
        "task_category": task_category,
        "gender": message.get("Gender"),
        "default_control_mode": message.get("DefaultControlMode"),
        "ai_autonomy_level": current_level,
        "current_level": current_level,
        "task_mode": message.get("TaskMode"),
        "difficulty_key": difficulty_key,
        "difficulty_display": difficulty_display,
        "difficulty_raw": message.get("Difficulty"),
        "task_number": message.get("TaskNumber"),
        "ai_precision": message.get("aiprecision"),
        "include_ai": include_ai,
        "is_practice": is_practice,
        "repetition_total_override": rep_override,
        "web_task_kind": web_task_kind,
    }
    return raw, normalized


def _build_external_task_db_fields(normalized: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "default_control_mode": normalized.get("default_control_mode"),
        "autonomy_level": normalized.get("current_level") or normalized.get("ai_autonomy_level"),
        "task_mode": normalized.get("task_mode"),
        "difficulty": normalized.get("difficulty_key"),
        "difficulty_display": normalized.get("difficulty_display"),
        "task_number": normalized.get("task_number"),
        "repetition_total_override": normalized.get("repetition_total_override"),
        "is_ai_active": normalized.get("include_ai"),
        "is_practice": normalized.get("is_practice"),
        "ai_precision": normalized.get("ai_precision"),
    }


def _persist_web_init_config(raw: Dict[str, Any], normalized: Dict[str, Any]) -> None:
    """Cache the latest platform web-task start config for diagnostics/reload visibility."""
    web_kind = normalized.get("web_task_kind")
    if web_kind not in ("radar", "sa"):
        return
    try:
        config: Dict[str, Any] = {}
        if os.path.exists(INIT_CONFIG_PATH):
            with open(INIT_CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    config = loaded
        task_number = normalized.get("repetition_total_override")
        if task_number is None:
            task_number = normalized.get("task_number")
        config.update({
            "userId": str(normalized.get("platform_task_id") or ""),
            "includeAI": bool(normalized.get("include_ai")),
            "taskType": web_kind,
            "isPractice": bool(normalized.get("is_practice")),
            "taskNumber": task_number,
            "platformTask": {
                "raw": raw,
                "normalized": normalized,
            },
        })
        config.setdefault("useJoystick", True)
        with open(INIT_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info(
            "cached platform web task config to init_config.json: user=%s kind=%s taskNumber=%s",
            config.get("userId"),
            config.get("taskType"),
            config.get("taskNumber"),
        )
    except Exception as exc:
        logger.warning("failed to cache platform web task config to init_config.json: %s", exc, exc_info=True)


def _attach_entry_semantics(normalized: Dict[str, Any], category: str, entry_mode: str) -> Dict[str, Any]:
    normalized["task_category"] = category
    normalized["task_type"] = _task_type_for_category(category)
    normalized["entry_mode"] = entry_mode
    web_kind = _web_kind_for_category(category)
    if web_kind:
        normalized["web_task_kind"] = web_kind
    return normalized


def apply_platform_task_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and write radar/SA platform_task data into global pending."""
    global _pending
    raw, normalized = _normalize_platform_task_fields(message)
    category = normalized.get("task_category") or _classify_task_category(message)
    if not _is_web_overlay_category(category):
        category = "sa" if normalized.get("web_task_kind") == "sa" else "radar"
    normalized = _attach_entry_semantics(normalized, category, "web_overlay")
    _persist_web_init_config(raw, normalized)
    cfg = config_manager.get_config()
    logger.info(
        "[REMOTE_TASK_COUNT] parsed platform_task id=%s name=%s raw_TaskNumber=%s "
        "rep_override=%s web_kind=%s task_type=%s entry_mode=%s mode=%s include_ai=%s level=%s "
        "difficulty_raw=%s difficulty_key=%s task_mode=%s is_practice=%s",
        normalized["platform_task_id"],
        normalized.get("task_name"),
        normalized.get("task_number"),
        normalized.get("repetition_total_override"),
        normalized.get("web_task_kind"),
        normalized.get("task_type"),
        normalized.get("entry_mode"),
        normalized.get("default_control_mode"),
        normalized.get("include_ai"),
        normalized.get("current_level"),
        normalized.get("difficulty_raw"),
        normalized.get("difficulty_key"),
        normalized.get("task_mode"),
        normalized.get("is_practice"),
    )
    if normalized.get("repetition_total_override") is not None:
        logger.warning(
            "[REMOTE_TASK_COUNT] ===== 远端下发：共%s次任务 ===== id=%s name=%s "
            "web_kind=%s raw_TaskNumber=%s",
            normalized.get("repetition_total_override"),
            normalized["platform_task_id"],
            normalized.get("task_name"),
            normalized.get("web_task_kind"),
            normalized.get("task_number"),
        )
    overlay = _build_overlay(normalized, cfg)
    _pending = {"raw": raw, "normalized": normalized, "overlay": overlay}
    web_kind = normalized.get("web_task_kind") or ""
    _active_web_task_overlays[(str(normalized["platform_task_id"]), web_kind)] = {
        "raw": copy.deepcopy(raw),
        "normalized": copy.deepcopy(normalized),
        "overlay": copy.deepcopy(overlay),
    }
    logger.info(
        "platform_task pending set: id=%s task_type=%s entry_mode=%s difficulty=%s level=%s include_ai=%s",
        normalized["platform_task_id"],
        normalized.get("task_type"),
        normalized.get("entry_mode"),
        normalized.get("difficulty_key"),
        normalized.get("current_level"),
        normalized.get("include_ai"),
    )
    logger.info(
        "[REMOTE_TASK_COUNT] external overall task_start stored id=%s web_kind=%s "
        "task_type=%s entry_mode=%s rep_override=%s "
        "overlay_total=%s active_overlay_keys=%s",
        normalized["platform_task_id"],
        web_kind,
        normalized.get("task_type"),
        normalized.get("entry_mode"),
        normalized.get("repetition_total_override"),
        overlay.get("repetition_total_override"),
        list(_active_web_task_overlays.keys()),
    )
    return normalized


def _pending_matches_task(user_id: Optional[str], task_type: Optional[str]) -> bool:
    if not _pending or not _pending.get("normalized"):
        return False
    if not user_id and not task_type:
        return True
    normalized = _pending.get("normalized") or {}
    if user_id and str(normalized.get("platform_task_id") or "") != str(user_id):
        return False
    expected_kind = _web_kind_for_task_type(str(task_type or ""))
    if expected_kind:
        pending_kind = str(normalized.get("web_task_kind") or "")
        return pending_kind in (expected_kind, "")
    return True


def _copy_overlay_entry(entry: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    overlay = copy.deepcopy(entry.get("overlay") or {})
    meta = {
        "raw": copy.deepcopy(entry.get("raw")),
        "normalized": copy.deepcopy(entry.get("normalized")),
    }
    return overlay, meta


def peek_pending_include_ai(user_id: Optional[str] = None, task_type: Optional[str] = None) -> Optional[bool]:
    if (user_id or task_type) and not _pending_matches_task(user_id, task_type):
        logger.info(
            "[REMOTE_TASK_COUNT] peek pending include_ai miss user=%s task_type=%s pending_id=%s pending_kind=%s",
            user_id,
            task_type,
            ((_pending or {}).get("normalized") or {}).get("platform_task_id"),
            ((_pending or {}).get("normalized") or {}).get("web_task_kind"),
        )
        return None
    if _pending and _pending.get("normalized"):
        return _pending["normalized"].get("include_ai")
    return None


def consume_pending_for_task_start(
    user_id: Optional[str] = None,
    task_type: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """返回 (scenario_overlay, platform_meta)。消费并清除 pending。"""
    global _pending
    if not _pending:
        logger.info("[REMOTE_TASK_COUNT] consume pending: none")
        return None, None
    if (user_id or task_type) and not _pending_matches_task(user_id, task_type):
        normalized = _pending.get("normalized") or {}
        logger.info(
            "[REMOTE_TASK_COUNT] consume pending miss user=%s task_type=%s "
            "pending_id=%s pending_kind=%s pending_task_type=%s",
            user_id,
            task_type,
            normalized.get("platform_task_id"),
            normalized.get("web_task_kind"),
            normalized.get("task_type"),
        )
        return None, None
    overlay = copy.deepcopy(_pending.get("overlay") or {})
    meta = {
        "raw": copy.deepcopy(_pending.get("raw")),
        "normalized": copy.deepcopy(_pending.get("normalized")),
    }
    normalized = meta.get("normalized") or {}
    logger.info(
        "[REMOTE_TASK_COUNT] consume pending id=%s web_kind=%s raw_TaskNumber=%s "
        "rep_override=%s overlay_total=%s",
        normalized.get("platform_task_id"),
        normalized.get("web_task_kind"),
        normalized.get("task_number"),
        normalized.get("repetition_total_override"),
        overlay.get("repetition_total_override"),
    )
    _pending = None
    return overlay, meta


def get_active_overlay_for_task(user_id: str, task_type: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """获取当前用户最近一次平台任务配置，不消费。

    平台包只会在 web 任务开始时广播一次，但 SA/传感器任务内部可能有多次
    repetition。后续 repetition 需要继续沿用同一个难度和自主等级。
    """
    kind = _web_kind_for_task_type(task_type) or "radar"
    key = (str(user_id), kind)
    entry = _active_web_task_overlays.get(key) or _active_web_task_overlays.get((str(user_id), ""))
    if not entry:
        logger.info(
            "[REMOTE_TASK_COUNT] active overlay miss user=%s task_type=%s kind=%s keys=%s",
            user_id,
            task_type,
            kind,
            list(_active_web_task_overlays.keys()),
        )
        return None, None
    overlay, meta = _copy_overlay_entry(entry)
    normalized = meta.get("normalized") or {}
    logger.info(
        "[REMOTE_TASK_COUNT] active overlay hit user=%s task_type=%s kind=%s id=%s "
        "raw_TaskNumber=%s rep_override=%s overlay_total=%s",
        user_id,
        task_type,
        kind,
        normalized.get("platform_task_id"),
        normalized.get("task_number"),
        normalized.get("repetition_total_override"),
        overlay.get("repetition_total_override"),
    )
    return overlay, meta


def get_progress_key_for_task(user_id: str, task_type: str) -> str:
    """进度隔离键：同一用户可按 DefaultControlMode-AIAutonomyLeve-Difficulty 做多组任务。"""
    _, meta = get_active_overlay_for_task(user_id, task_type)
    normalized = (meta or {}).get("normalized") or {}
    if not normalized:
        logger.info(
            "[REMOTE_TASK_COUNT] progress key default user=%s task_type=%s progress_key=%s",
            user_id,
            task_type,
            task_type,
        )
        return task_type

    mode = normalized.get("default_control_mode")
    if mode is None or str(mode).strip() == "":
        mode = "1" if normalized.get("include_ai") else "0"
    level = normalized.get("current_level") or normalized.get("ai_autonomy_level") or "L1"
    difficulty = normalized.get("difficulty_key") or ""
    combo = f"{str(mode).strip()}-{str(level).strip()}-{str(difficulty).strip()}"
    progress_key = f"{task_type}::{combo}"
    logger.info(
        "[REMOTE_TASK_COUNT] progress key user=%s task_type=%s id=%s raw_TaskNumber=%s "
        "rep_override=%s progress_key=%s",
        user_id,
        task_type,
        normalized.get("platform_task_id"),
        normalized.get("task_number"),
        normalized.get("repetition_total_override"),
        progress_key,
    )
    return progress_key


def _merge_external_task_normalized(
    message_data: Dict[str, Any],
    active: Dict[str, Any],
) -> Dict[str, Any]:
    base_raw = copy.deepcopy(active.get("raw") or {})
    current_raw = {k: v for k, v in message_data.items() if k != "type"}
    merged_raw = {**base_raw, **current_raw}
    _, normalized = _normalize_platform_task_fields(merged_raw, active.get("task_category"))
    active["raw"] = merged_raw
    active["normalized"] = normalized
    active["task_name"] = normalized.get("task_name")
    active["gender"] = normalized.get("gender")
    return normalized


_OVERALL_TASK_START_FIELDS = {
    "Gender",
    "DefaultControlMode",
    "AIAutonomyLeve",
    "AIAutonomyLevel",
    "TaskMode",
    "Difficulty",
    "TaskNumber",
    "aiprecision",
    "AIPrecision",
}

def _task_type_for_external_category(category: str) -> str:
    return _task_type_for_category(category)


def _is_overall_task_start(message_data: Dict[str, Any]) -> bool:
    return any(key in message_data for key in _OVERALL_TASK_START_FIELDS)


def _expected_subtasks_from_normalized(normalized: Dict[str, Any]) -> int:
    value = normalized.get("repetition_total_override") or normalized.get("task_number") or 1
    try:
        return max(1, int(float(value)))
    except (TypeError, ValueError):
        return 1


def _json_dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


_EXTERNAL_ACTION_ALIASES = {
    "sub_ennd": "sub_end",
    "subend": "sub_end",
    "sub_stop": "sub_end",
    "substop": "sub_end",
}


def _normalize_external_action(raw_action: Any) -> str:
    action = str(raw_action or "task_start").strip()
    return _EXTERNAL_ACTION_ALIASES.get(action.lower(), action)


def _external_collector_names(external_collectors: Any = None) -> List[str]:
    adapters = getattr(external_collectors, "adapters", None) if external_collectors is not None else None
    if not adapters:
        return []
    return [str(getattr(adapter, "name", "") or getattr(adapter, "provider", "") or "?") for adapter in adapters]


def _external_task_diagnostics(
    message_data: Dict[str, Any],
    category: str,
    action: str,
    user_id: str,
    task_type: str,
    external_collectors: Any = None,
    active: Optional[Dict[str, Any]] = None,
    event_role: str = "",
) -> Dict[str, Any]:
    keys = sorted(str(key) for key in message_data.keys())
    is_overall = action == "task_start" and _is_overall_task_start(message_data)
    return {
        "category": category,
        "task_type": task_type,
        "user_id": user_id,
        "raw_action": str(message_data.get("Action") or ""),
        "action": action,
        "action_was_normalized": str(message_data.get("Action") or "").strip() != action,
        "event_role": event_role or ("overall_start" if is_overall else "subtask_start" if action in ("task_start", "sub_start") else action),
        "is_overall_task_start": is_overall,
        "message_keys": keys,
        "overall_fields_present": sorted(key for key in _OVERALL_TASK_START_FIELDS if key in message_data),
        "external_collectors_injected": external_collectors is not None,
        "external_collectors_enabled": bool(getattr(external_collectors, "enabled", False)) if external_collectors is not None else False,
        "external_collector_names": _external_collector_names(external_collectors),
        "active_task_id": (active or {}).get("task_id"),
        "active_overall_task_id": (active or {}).get("overall_task_id"),
        "active_subtask_task_id": (active or {}).get("current_subtask_task_id"),
        "active_subtask_seq": (active or {}).get("current_subtask_seq"),
    }


def _task_run_config(category: str, raw_fields: Dict[str, Any], normalized: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "task_category": category,
        "raw": raw_fields,
        "normalized": normalized,
    }


def _normalized_task_signature(normalized: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "platform_task_id": str(normalized.get("platform_task_id") or ""),
        "task_type": normalized.get("task_type"),
        "task_category": normalized.get("task_category"),
        "default_control_mode": normalized.get("default_control_mode"),
        "current_level": normalized.get("current_level") or normalized.get("ai_autonomy_level"),
        "task_mode": normalized.get("task_mode"),
        "difficulty_key": normalized.get("difficulty_key"),
        "difficulty_display": normalized.get("difficulty_display"),
        "difficulty_raw": normalized.get("difficulty_raw"),
        "task_number": normalized.get("task_number"),
        "ai_precision": normalized.get("ai_precision"),
        "include_ai": normalized.get("include_ai"),
        "is_practice": normalized.get("is_practice"),
        "repetition_total_override": normalized.get("repetition_total_override"),
    }


def _config_json_normalized(config_json: Any) -> Dict[str, Any]:
    if not config_json:
        return {}
    try:
        parsed = json.loads(config_json) if isinstance(config_json, str) else config_json
    except (TypeError, ValueError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    normalized = parsed.get("normalized")
    return normalized if isinstance(normalized, dict) else {}


def _config_json_raw(config_json: Any) -> Dict[str, Any]:
    if not config_json:
        return {}
    try:
        parsed = json.loads(config_json) if isinstance(config_json, str) else config_json
    except (TypeError, ValueError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    raw = parsed.get("raw")
    return raw if isinstance(raw, dict) else {}


def _result_metrics(result: Dict[str, Any]) -> Dict[str, Any]:
    fire_list = result.get("Fire") or []
    switch_list = result.get("SwitchInfo") or []
    ai_time_obj = result.get("AITIME") or {}
    return {
        "current_task_score": result.get("CurrentTaskScore"),
        "ai_control_time": result.get("AIcontrolTime"),
        "person_control_time": result.get("PersonControlTime"),
        "ai_remind_time": ai_time_obj.get("AiRemindTime"),
        "switch_count": len(switch_list),
        "fire_count": len(fire_list),
        "fire_success_count": sum(1 for item in fire_list if isinstance(item, dict) and item.get("FireResult")),
    }


def _active_from_task_run(
    run: Dict[str, Any],
    category: str,
    raw_fields: Dict[str, Any],
    normalized: Dict[str, Any],
) -> Dict[str, Any]:
    task_id = int(run["task_id"])
    return {
        "task_id": task_id,
        "overall_task_id": task_id,
        "task_type": run.get("task_type") or _task_type_for_external_category(category),
        "task_category": category,
        "user_id": run.get("user_id") or str(normalized.get("platform_task_id") or ""),
        "expected_subtasks": int(run.get("expected_subtasks") or _expected_subtasks_from_normalized(normalized)),
        "completed_subtasks": int(run.get("completed_subtasks") or 0),
        "current_subtask_seq": int(run.get("current_subtask_seq") or 0),
        "task_name": normalized.get("task_name"),
        "gender": normalized.get("gender"),
        "raw": copy.deepcopy(raw_fields),
        "normalized": copy.deepcopy(normalized),
        "gaze_task_id": str(run["task_id"]),
    }


def _load_active_external_task(
    category: str,
    user_id: str,
    raw_fields: Dict[str, Any],
    normalized: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    task_type = _task_type_for_external_category(category)
    key = (category, user_id)
    active = _active_external_tasks.get(key)
    if active:
        return active
    run = db_manager.find_active_task_run(user_id, task_type)
    if not run:
        return None
    active = _active_from_task_run(run, category, raw_fields, normalized)
    _active_external_tasks[key] = active
    return active


def _find_active_external_task_for_user(
    user_id: str,
    exclude_key: Optional[Tuple[str, str]] = None,
) -> Tuple[Optional[Tuple[str, str]], Optional[Dict[str, Any]]]:
    for active_key, active in _active_external_tasks.items():
        if active_key == exclude_key:
            continue
        if active_key[1] == user_id:
            return active_key, active

    for category in ("platform_control", "weapon_launch"):
        candidate_key = (category, user_id)
        if candidate_key == exclude_key:
            continue
        task_type = _task_type_for_external_category(category)
        run = db_manager.find_active_task_run(user_id, task_type)
        if not run:
            continue
        raw_fields = {}
        normalized = {
            "platform_task_id": user_id,
            "task_name": run.get("task_type") or task_type,
        }
        active = _active_from_task_run(run, category, raw_fields, normalized)
        _active_external_tasks[candidate_key] = active
        return candidate_key, active
    return None, None


def _external_marker_payload(
    active: Dict[str, Any],
    category: str,
    event_type: str,
    sub_task_seq: Optional[int],
    message_data: Dict[str, Any],
    timestamp_ms: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "source": "F18-Radar",
        "task_id": active.get("task_id"),
        "task_type": active.get("task_type"),
        "task_category": category,
        "platform_task_id": active.get("user_id"),
        "user_id": active.get("user_id"),
        "event_type": event_type,
        "sub_task_seq": sub_task_seq,
        "expected_subtasks": active.get("expected_subtasks"),
        "completed_subtasks": active.get("completed_subtasks"),
        "message": message_data,
    }
    if timestamp_ms is not None:
        payload["timestamp_ms"] = int(timestamp_ms)
        payload["timestamp_us"] = int(timestamp_ms) * 1000
    if extra:
        payload.update(extra)
    return payload


def _start_external_marker_context(
    active: Dict[str, Any],
    category: str,
    message_data: Dict[str, Any],
    timestamp_ms: Optional[int] = None,
    gaze_svc: Any = None,
    physio_svc: Any = None,
    external_collectors: Any = None,
    event_type: str = "overall_start",
    sub_task_seq: Optional[int] = None,
) -> None:
    payload = _external_marker_payload(active, category, event_type, sub_task_seq, message_data, timestamp_ms)
    user_id = str(active.get("user_id") or "")
    task_type = str(active.get("task_type") or _task_type_for_external_category(category))
    if gaze_svc is not None:
        gaze_task_id = str(active.get("task_id"))
        active["gaze_task_id"] = gaze_task_id
        try:
            gaze_svc.start_task(
                bbox=[],
                screen_size=None,
                task_id=gaze_task_id,
                user_id=user_id,
                task_source=category,
                task_name=task_type,
                system_time=(int(timestamp_ms) * 1000) if timestamp_ms is not None else None,
                start_trigger=event_type,
            )
            _record_external_gaze_marker(gaze_svc, active, event_type, payload, timestamp_ms=timestamp_ms)
        except Exception as e:
            active.pop("gaze_task_id", None)
            logger.warning("gaze external %s start_task failed: %s", event_type, e, exc_info=True)
    if physio_svc is not None:
        try:
            physio_svc.set_subject(user_id, {"source": "F18-Radar", "last_task_type": task_type})
            physio_run_id = str(active.get("gaze_task_id") or active.get("task_id"))
            physio_svc.start_task(task_type, payload, run_id=physio_run_id)
            physio_svc.marker(event_type, payload)
        except Exception as e:
            logger.warning("physio external start_task failed: %s", e, exc_info=True)
    if external_collectors is not None:
        try:
            external_run_id = str(active.get("gaze_task_id") or active.get("task_id"))
            logger.warning(
                "[EXTERNAL_COLLECTOR_DIAG] start_task event=%s task_type=%s user=%s run_id=%s collectors=%s",
                event_type,
                task_type,
                user_id,
                external_run_id,
                _external_collector_names(external_collectors),
            )
            external_collectors.start_task(task_type, user_id, external_run_id, payload)
            external_collectors.marker(event_type, payload)
        except Exception as e:
            logger.warning("external collector %s failed: %s", event_type, e, exc_info=True)
    elif event_type in ("task_start", "sub_start"):
        logger.warning(
            "[EXTERNAL_COLLECTOR_DIAG] no external_collectors injected for event=%s task_type=%s user=%s task_id=%s",
            event_type,
            task_type,
            user_id,
            active.get("task_id"),
        )


def _record_external_gaze_marker(
    gaze_svc: Any,
    active: Dict[str, Any],
    event_type: str,
    payload: Dict[str, Any],
    timestamp_ms: Optional[int] = None,
) -> None:
    active_gaze_task_id = active.get("gaze_task_id")
    try:
        getter = getattr(gaze_svc, "get_active_task_id", None)
        if callable(getter):
            active_gaze_task_id = active_gaze_task_id or getter()
    except Exception as e:
        logger.warning("gaze active task lookup failed: %s", e, exc_info=True)

    marker_task_id = active_gaze_task_id or active.get("task_id")
    payload["external_task_id"] = active.get("task_id")
    if active_gaze_task_id:
        payload["gaze_task_id"] = active_gaze_task_id
    try:
        kwargs = {
            "payload": payload,
            "task_id": marker_task_id,
            "user_id": str(active.get("user_id") or ""),
        }
        if timestamp_ms is not None:
            kwargs["system_time"] = int(timestamp_ms) * 1000
        marker = gaze_svc.record_marker(
            event_type,
            **kwargs,
        )
        if isinstance(marker, dict) and marker.get("task_id"):
            payload["gaze_task_id"] = marker.get("task_id")
    except Exception as e:
        logger.warning("gaze external marker failed: event=%s error=%s", event_type, e, exc_info=True)


def _emit_external_marker(
    active: Dict[str, Any],
    category: str,
    event_type: str,
    sub_task_seq: Optional[int],
    message_data: Dict[str, Any],
    gaze_svc: Any = None,
    physio_svc: Any = None,
    external_collectors: Any = None,
    timestamp_ms: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    payload = _external_marker_payload(active, category, event_type, sub_task_seq, message_data, timestamp_ms, extra)
    if gaze_svc is not None:
        _record_external_gaze_marker(gaze_svc, active, event_type, payload, timestamp_ms=timestamp_ms)
    if physio_svc is not None:
        try:
            physio_svc.marker(event_type, payload)
        except Exception as e:
            logger.warning("physio external marker failed: event=%s error=%s", event_type, e, exc_info=True)
    if external_collectors is not None:
        try:
            external_collectors.marker(event_type, payload)
        except Exception as e:
            logger.warning("external collector marker failed: event=%s error=%s", event_type, e, exc_info=True)


def _stop_external_gaze_task(
    active: Dict[str, Any],
    event_type: str,
    gaze_svc: Any = None,
    timestamp_ms: Optional[int] = None,
) -> None:
    if gaze_svc is None or not active.get("gaze_task_id"):
        return
    try:
        kwargs = {"task_id": str(active.get("gaze_task_id")), "end_trigger": event_type}
        if timestamp_ms is not None:
            kwargs["system_time"] = int(timestamp_ms) * 1000
        gaze_svc.stop_task(**kwargs)
        active.pop("gaze_task_id", None)
    except Exception as e:
        logger.warning("gaze external stop_task failed: %s", e, exc_info=True)


def _stop_external_marker_context(
    active: Dict[str, Any],
    category: str,
    event_type: str,
    message_data: Dict[str, Any],
    gaze_svc: Any = None,
    physio_svc: Any = None,
    external_collectors: Any = None,
    sub_task_seq: Optional[int] = None,
    timestamp_ms: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    _emit_external_marker(
        active,
        category,
        event_type,
        sub_task_seq,
        message_data,
        gaze_svc,
        physio_svc,
        external_collectors,
        timestamp_ms=timestamp_ms,
        extra=extra,
    )
    _stop_external_gaze_task(active, event_type, gaze_svc=gaze_svc, timestamp_ms=timestamp_ms)
    if physio_svc is not None:
        try:
            physio_svc.stop_task()
            physio_svc.clear_subject()
        except Exception as e:
            logger.warning("physio external stop_task failed: %s", e, exc_info=True)
    if external_collectors is not None:
        try:
            stop_id = str(active.get("gaze_task_id") or active.get("task_id") or "")
            logger.warning(
                "[EXTERNAL_COLLECTOR_DIAG] stop_task event=%s task_id=%s collectors=%s",
                event_type,
                stop_id,
                _external_collector_names(external_collectors),
            )
            external_collectors.stop_task(stop_id)
            external_collectors.clear_subject()
        except Exception as e:
            logger.warning("external collector stop_task failed: %s", e, exc_info=True)


def _close_external_active_task(
    active_key: Tuple[str, str],
    active: Dict[str, Any],
    event_type: str,
    message_data: Dict[str, Any],
    timestamp_ms: int,
    raw_message_json: str,
    gaze_svc: Any = None,
    physio_svc: Any = None,
    external_collectors: Any = None,
) -> None:
    category, user_id = active_key
    tid = active.get("task_id")
    task_type = active.get("task_type") or _task_type_for_external_category(category)
    seq = int(active.get("current_subtask_seq") or active.get("completed_subtasks") or 0) or None
    db_manager.record_task_event(
        task_id=tid,
        task_type=task_type,
        user_id=user_id,
        event_type=event_type,
        sub_task_seq=seq,
        timestamp_ms=timestamp_ms,
        payload_json=_json_dump({"task_category": category, "reason": event_type}),
        raw_message_json=raw_message_json,
    )
    db_manager.update_task_run_progress(
        task_id=tid,
        status="completed",
        completed_at_ms=timestamp_ms,
        raw_message_json=raw_message_json,
    )
    if active.get("current_subtask_task_id") or active.get("gaze_task_id"):
        _stop_external_marker_context(
            active,
            category,
            event_type,
            message_data,
            gaze_svc=gaze_svc,
            physio_svc=physio_svc,
            external_collectors=external_collectors,
            sub_task_seq=seq,
            timestamp_ms=timestamp_ms,
        )
    _active_external_tasks.pop(active_key, None)
    logger.warning(
        "[REMOTE_TASK_COUNT] external active task auto-closed by new overall "
        "old_category=%s old_task_id=%s user=%s event_type=%s",
        category,
        tid,
        user_id,
        event_type,
    )


def _handle_overall_stop_compat_if_needed(
    message_data: Dict[str, Any],
    category: str,
    user_id: str,
    task_type: str,
    raw_fields: Dict[str, Any],
    normalized: Dict[str, Any],
    timestamp_ms: int,
    raw_message_json: str,
    gaze_svc: Any = None,
    physio_svc: Any = None,
) -> Optional[List[Dict[str, Any]]]:
    finder = getattr(db_manager, "find_recent_completed_task_run", None)
    if not callable(finder):
        return None
    recent = finder(user_id, task_type)
    if not recent:
        return None
    recent_config = recent.get("config_json")
    try:
        recent_config_obj = json.loads(recent_config) if isinstance(recent_config, str) else recent_config
    except (TypeError, ValueError):
        recent_config_obj = {}
    if isinstance(recent_config_obj, dict) and recent_config_obj.get("overall_task_id") is not None:
        return None
    recent_raw = _config_json_raw(recent.get("config_json"))
    if recent_raw != raw_fields:
        return None
    recent_normalized = _config_json_normalized(recent.get("config_json"))
    if _normalized_task_signature(recent_normalized) != _normalized_task_signature(normalized):
        return None

    tid = int(recent["task_id"])
    payload = _task_run_config(category, raw_fields, normalized)
    payload["compat_reason"] = "duplicate_identical_overall_start_after_completed_run"
    db_manager.record_task_event(
        task_id=tid,
        task_type=task_type,
        user_id=user_id,
        event_type="overall_stop_compat",
        timestamp_ms=timestamp_ms,
        payload_json=_json_dump(payload),
        raw_message_json=raw_message_json,
    )
    marker_payload = _external_marker_payload(
        {
            "task_id": tid,
            "task_type": task_type,
            "task_category": category,
            "user_id": user_id,
            "expected_subtasks": recent.get("expected_subtasks"),
            "completed_subtasks": recent.get("completed_subtasks"),
            "gaze_task_id": str(tid),
        },
        category,
        "overall_stop_compat",
        None,
        message_data,
        timestamp_ms,
        {"compat_reason": "duplicate_identical_overall_start_after_completed_run"},
    )
    if gaze_svc is not None:
        try:
            gaze_svc.record_marker(
                "overall_stop_compat",
                payload=marker_payload,
                task_id=str(tid),
                user_id=user_id,
                system_time=timestamp_ms * 1000,
            )
        except Exception as e:
            logger.warning("gaze overall_stop_compat marker failed: %s", e, exc_info=True)
    if physio_svc is not None:
        try:
            physio_svc.marker("overall_stop_compat", marker_payload)
        except Exception as e:
            logger.warning("physio overall_stop_compat marker failed: %s", e, exc_info=True)
    logger.warning(
        "[REMOTE_TASK_COUNT] compat overall_stop consumed duplicate full task_start "
        "category=%s user=%s task_id=%s reason=duplicate_identical_overall_start",
        category,
        user_id,
        tid,
    )
    return [{
        "type": "platform_task_ack",
        "status": "ok",
        "task_id": tid,
        "task_type": task_type,
        "task_category": category,
        "entry_mode": "external_lifecycle",
        "event_type": "overall_stop_compat",
        "compat": True,
    }]


def _handle_external_task_legacy(message_data: Dict[str, Any], category: str) -> List[Dict[str, Any]]:
    """处理外部平台任务（平台控制 / 武器发射）的生命周期事件。"""
    user_id = str(message_data.get("ID") or "").strip()
    if not user_id:
        return [{"type": "platform_task_ack", "status": "error",
                 "message": "external task requires non-empty ID"}]

    action = str(message_data.get("Action") or "task_start").strip()
    task_name = message_data.get("TaskName")
    gender = message_data.get("Gender")
    ts = int(_time.time() * 1000)
    raw = json.dumps(message_data, ensure_ascii=False)
    key = (category, user_id)
    logger.info(
        "[REMOTE_TASK_COUNT] external event received category=%s user=%s action=%s "
        "active_before=%s active_keys=%s",
        category,
        user_id,
        action,
        _active_external_tasks.get(key),
        list(_active_external_tasks.keys()),
    )

    if action == "task_start":
        raw_fields, normalized = _normalize_platform_task_fields(message_data, category)
        db_fields = _build_external_task_db_fields(normalized)
        tid = generate_task_id()
        _active_external_tasks[key] = {
            "task_id": tid, "sub_task_seq": 0,
            "task_name": normalized.get("task_name"), "gender": normalized.get("gender"),
            "raw": copy.deepcopy(raw_fields), "normalized": copy.deepcopy(normalized),
        }
        db_manager.record_external_task(
            task_id=tid, task_category=category, event_type="task_start",
            raw_message=raw, timestamp=ts, user_id=user_id,
            task_name=normalized.get("task_name"), gender=normalized.get("gender"),
            **db_fields,
        )
        logger.info("external task_start: category=%s user=%s task_id=%s",
                     category, user_id, tid)
        logger.warning(
            "[REMOTE_TASK_COUNT] ===== 外部任务开始 ===== category=%s user=%s "
            "task_id=%s TaskNumber=%s",
            category,
            user_id,
            tid,
            message_data.get("TaskNumber"),
        )
        logger.info(
            "[REMOTE_TASK_COUNT] external task_start stored category=%s user=%s "
            "task_id=%s sub_task_seq=%s active_keys=%s",
            category,
            user_id,
            tid,
            _active_external_tasks[key]["sub_task_seq"],
            list(_active_external_tasks.keys()),
        )
        return [{"type": "platform_task_ack", "status": "ok",
                 "task_id": tid, "task_category": category}]

    active = _active_external_tasks.get(key)
    if not active:
        logger.warning(
            "[REMOTE_TASK_COUNT] external event missing active category=%s user=%s "
            "action=%s active_keys=%s",
            category,
            user_id,
            action,
            list(_active_external_tasks.keys()),
        )
        return [{"type": "platform_task_ack", "status": "error",
                 "message": f"no active {category} task for user {user_id}"}]
    tid = active["task_id"]
    normalized = _merge_external_task_normalized(message_data, active)
    db_fields = _build_external_task_db_fields(normalized)
    task_name = normalized.get("task_name")
    gender = normalized.get("gender")

    if action == "sub_start":
        active["sub_task_seq"] += 1
        seq = active["sub_task_seq"]
        db_manager.record_external_task(
            task_id=tid, task_category=category, event_type="sub_start",
            raw_message=raw, timestamp=ts, user_id=user_id,
            task_name=task_name, gender=gender, sub_task_seq=seq,
            **db_fields,
        )
        logger.info("external sub_start: task_id=%s seq=%s", tid, seq)
        logger.warning(
            "[REMOTE_TASK_COUNT] ===== 第%s次任务开始 ===== category=%s user=%s task_id=%s",
            seq,
            category,
            user_id,
            tid,
        )
        logger.info(
            "[REMOTE_TASK_COUNT] external sub_start category=%s user=%s task_id=%s "
            "sub_task_seq=%s",
            category,
            user_id,
            tid,
            seq,
        )
        return [{"type": "platform_task_ack", "status": "ok",
                 "task_id": tid, "sub_task_seq": seq}]

    if action == "sub_end":
        seq = active["sub_task_seq"]
        db_manager.record_external_task(
            task_id=tid, task_category=category, event_type="sub_end",
            raw_message=raw, timestamp=ts, user_id=user_id,
            task_name=task_name, gender=gender, sub_task_seq=seq,
            **db_fields,
        )
        logger.info("external sub_end: task_id=%s seq=%s", tid, seq)
        logger.warning(
            "[REMOTE_TASK_COUNT] ===== 第%s次任务结束 ===== category=%s user=%s task_id=%s",
            seq,
            category,
            user_id,
            tid,
        )
        logger.info(
            "[REMOTE_TASK_COUNT] external sub_end category=%s user=%s task_id=%s "
            "sub_task_seq=%s has_result=%s",
            category,
            user_id,
            tid,
            seq,
            isinstance(message_data.get("result"), dict),
        )

        result = message_data.get("result")
        if result and isinstance(result, dict):
            fire_list = result.get("Fire") or []
            switch_list = result.get("SwitchInfo") or []
            ai_time_obj = result.get("AITIME") or {}
            db_manager.record_external_task_result(
                task_id=tid, task_category=category,
                raw_message=json.dumps(result, ensure_ascii=False),
                timestamp=ts, user_id=user_id,
                ai_control_time=result.get("AIcontrolTime"),
                person_control_time=result.get("PersonControlTime"),
                ai_remind_time=ai_time_obj.get("AiRemindTime"),
                switch_count=len(switch_list),
                fire_count=len(fire_list),
                fire_success_count=sum(1 for f in fire_list if f.get("FireResult")),
                **db_fields,
            )
            logger.info("external sub_end with result: task_id=%s seq=%s", tid, seq)
            logger.info(
                "[REMOTE_TASK_COUNT] external sub_end result metrics task_id=%s seq=%s "
                "switch_count=%s fire_count=%s fire_success_count=%s",
                tid,
                seq,
                len(switch_list),
                len(fire_list),
                sum(1 for f in fire_list if f.get("FireResult")),
            )

        return [{"type": "platform_task_ack", "status": "ok",
                 "task_id": tid, "sub_task_seq": seq}]

    if action == "task_end":
        db_manager.record_external_task(
            task_id=tid, task_category=category, event_type="task_end",
            raw_message=raw, timestamp=ts, user_id=user_id,
            task_name=task_name, gender=gender,
            **db_fields,
        )
        _active_external_tasks.pop(key, None)
        logger.info("external task_end: task_id=%s", tid)
        logger.warning(
            "[REMOTE_TASK_COUNT] ===== 外部任务结束 ===== category=%s user=%s "
            "task_id=%s 共%s次子任务",
            category,
            user_id,
            tid,
            active.get("sub_task_seq"),
        )
        logger.info(
            "[REMOTE_TASK_COUNT] external task_end category=%s user=%s task_id=%s "
            "final_sub_task_seq=%s active_keys=%s",
            category,
            user_id,
            tid,
            active.get("sub_task_seq"),
            list(_active_external_tasks.keys()),
        )
        return [{"type": "platform_task_ack", "status": "ok",
                 "task_id": tid, "event_type": "task_end"}]

    return [{"type": "platform_task_ack", "status": "error",
             "message": f"unknown Action: {action}"}]


def _handle_platform_task_result_ws_legacy(message_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """处理外部平台任务结果消息。"""
    logger.info("RAW platform_task_result: %s",
                json.dumps(message_data, ensure_ascii=False))

    user_id = str(message_data.get("ID") or "").strip()
    if not user_id:
        return [{"type": "platform_task_ack", "status": "error",
                 "message": "platform_task_result requires non-empty ID"}]

    active = None
    matched_key = None
    for k, v in _active_external_tasks.items():
        if k[1] == user_id:
            active = v
            matched_key = k
            break
    logger.info(
        "[REMOTE_TASK_COUNT] platform_task_result lookup user=%s matched_key=%s "
        "active=%s active_keys=%s",
        user_id,
        matched_key,
        active,
        list(_active_external_tasks.keys()),
    )

    if not active:
        logger.warning("platform_task_result: no active task for user %s, "
                       "storing with task_id=-1", user_id)
        tid = -1
        category = "unknown"
    else:
        tid = active["task_id"]
        category = matched_key[0]
    if active:
        normalized = _merge_external_task_normalized(message_data, active)
        db_fields = _build_external_task_db_fields(normalized)
    else:
        try:
            _, normalized = _normalize_platform_task_fields(message_data, category)
            db_fields = _build_external_task_db_fields(normalized)
        except ValueError:
            db_fields = {}

    ts = int(_time.time() * 1000)
    raw = json.dumps(message_data, ensure_ascii=False)

    fire_list = message_data.get("Fire") or []
    switch_list = message_data.get("SwitchInfo") or []
    ai_time_obj = message_data.get("AITIME") or {}

    db_manager.record_external_task_result(
        task_id=tid, task_category=category, raw_message=raw, timestamp=ts,
        user_id=user_id,
        ai_control_time=message_data.get("AIcontrolTime"),
        person_control_time=message_data.get("PersonControlTime"),
        ai_remind_time=ai_time_obj.get("AiRemindTime"),
        switch_count=len(switch_list),
        fire_count=len(fire_list),
        fire_success_count=sum(1 for f in fire_list if f.get("FireResult")),
        **db_fields,
    )

    if matched_key:
        _active_external_tasks.pop(matched_key, None)

    logger.info("platform_task_result stored: task_id=%s category=%s", tid, category)
    logger.info(
        "[REMOTE_TASK_COUNT] platform_task_result stored task_id=%s category=%s "
        "switch_count=%s fire_count=%s fire_success_count=%s active_keys=%s",
        tid,
        category,
        len(switch_list),
        len(fire_list),
        sum(1 for f in fire_list if f.get("FireResult")),
        list(_active_external_tasks.keys()),
    )
    return [{"type": "platform_task_ack", "status": "ok",
             "task_id": tid, "event_type": "task_result"}]


def _handle_external_task(
    message_data: Dict[str, Any],
    category: str,
    gaze_svc: Any = None,
    physio_svc: Any = None,
    external_collectors: Any = None,
) -> List[Dict[str, Any]]:
    user_id = str(message_data.get("ID") or "").strip()
    if not user_id:
        return [{"type": "platform_task_ack", "status": "error",
                 "message": "external task requires non-empty ID"}]

    raw_action = str(message_data.get("Action") or "task_start").strip()
    action = _normalize_external_action(raw_action)
    ts = int(_time.time() * 1000)
    raw = _json_dump(message_data)
    key = (category, user_id)
    task_type = _task_type_for_external_category(category)
    logger.info(
        "[REMOTE_TASK_COUNT] external event received category=%s user=%s action=%s raw_action=%s "
        "active_before=%s active_keys=%s",
        category,
        user_id,
        action,
        raw_action,
        _active_external_tasks.get(key),
        list(_active_external_tasks.keys()),
    )
    if raw_action != action:
        logger.warning(
            "[EXTERNAL_COLLECTOR_DIAG] normalized external Action raw=%s normalized=%s",
            raw_action,
            action,
        )
    logger.warning(
        "[EXTERNAL_COLLECTOR_DIAG] received %s",
        _json_dump(_external_task_diagnostics(
            message_data,
            category,
            action,
            user_id,
            task_type,
            external_collectors=external_collectors,
            active=_active_external_tasks.get(key),
            event_role="received",
        )),
    )

    if action in ("task_start", "sub_start"):
        raw_fields, normalized = _normalize_platform_task_fields(message_data, category)
        normalized = _attach_entry_semantics(normalized, category, "external_lifecycle")
        if action == "task_start" and _is_overall_task_start(message_data):
            if key in _active_external_tasks:
                active = _active_external_tasks[key]
                logger.warning(
                    "[REMOTE_TASK_COUNT] ignore extra overall task_start while active "
                    "category=%s user=%s task_id=%s active_keys=%s",
                    category,
                    user_id,
                    active.get("task_id"),
                    list(_active_external_tasks.keys()),
                )
                return [{"type": "platform_task_ack", "status": "ignored",
                         "task_id": active.get("task_id"), "task_type": task_type,
                         "task_category": category, "entry_mode": "external_lifecycle",
                         "event_type": "overall_start",
                         "diagnostics": _external_task_diagnostics(
                             message_data,
                             category,
                             action,
                             user_id,
                             task_type,
                             external_collectors=external_collectors,
                             active=active,
                             event_role="overall_start_ignored",
                         )}]

            compat_reply = _handle_overall_stop_compat_if_needed(
                message_data,
                category,
                user_id,
                task_type,
                raw_fields,
                normalized,
                timestamp_ms=ts,
                raw_message_json=raw,
                gaze_svc=gaze_svc,
                physio_svc=physio_svc,
            )
            if compat_reply is not None:
                return compat_reply

            old_key, old_active = _find_active_external_task_for_user(user_id, exclude_key=key)
            if old_key and old_active:
                _close_external_active_task(
                    old_key,
                    old_active,
                    "auto_closed_by_new_overall",
                    message_data,
                    timestamp_ms=ts,
                    raw_message_json=raw,
                    gaze_svc=gaze_svc,
                    physio_svc=physio_svc,
                    external_collectors=external_collectors,
                )

            expected = _expected_subtasks_from_normalized(normalized)
            run = db_manager.find_active_task_run(user_id, task_type)
            if run:
                active = _active_from_task_run(run, category, raw_fields, normalized)
                _active_external_tasks[key] = active
                tid = active["task_id"]
                logger.info(
                    "[REMOTE_TASK_COUNT] external overall task_start resumed "
                    "category=%s task_type=%s entry_mode=%s user=%s task_id=%s "
                    "completed=%s current_seq=%s total=%s",
                    category,
                    task_type,
                    normalized.get("entry_mode"),
                    user_id,
                    tid,
                    active.get("completed_subtasks"),
                    active.get("current_subtask_seq"),
                    active.get("expected_subtasks"),
                )
            else:
                tid = generate_task_id()
                active = {
                    "task_id": tid,
                    "overall_task_id": tid,
                    "task_type": task_type,
                    "task_category": category,
                    "user_id": user_id,
                    "expected_subtasks": expected,
                    "completed_subtasks": 0,
                    "current_subtask_seq": 0,
                    "task_name": normalized.get("task_name"),
                    "gender": normalized.get("gender"),
                    "raw": copy.deepcopy(raw_fields),
                    "normalized": copy.deepcopy(normalized),
                }
                _active_external_tasks[key] = active
                db_manager.create_task_run(
                    task_id=tid,
                    task_type=task_type,
                    user_id=user_id,
                    expected_subtasks=expected,
                    started_at_ms=ts,
                    config_json=_json_dump(_task_run_config(category, raw_fields, normalized)),
                    raw_message_json=raw,
                )
                logger.info(
                    "[REMOTE_TASK_COUNT] external overall task_start stored "
                    "category=%s task_type=%s entry_mode=%s user=%s task_id=%s total=%s",
                    category,
                    task_type,
                    normalized.get("entry_mode"),
                    user_id,
                    tid,
                    expected,
                )

            db_manager.record_task_event(
                task_id=tid,
                task_type=task_type,
                user_id=user_id,
                event_type="overall_start",
                timestamp_ms=ts,
                payload_json=_json_dump(_task_run_config(category, raw_fields, normalized)),
                raw_message_json=raw,
            )
            return [{"type": "platform_task_ack", "status": "ok",
                     "task_id": tid, "task_type": task_type,
                     "task_category": category, "entry_mode": "external_lifecycle",
                     "expected_subtasks": active.get("expected_subtasks"),
                     "completed_subtasks": active.get("completed_subtasks"),
                     "diagnostics": _external_task_diagnostics(
                         message_data,
                         category,
                         action,
                         user_id,
                         task_type,
                         external_collectors=external_collectors,
                         active=active,
                         event_role="overall_start",
                     )}]

        active = _load_active_external_task(category, user_id, raw_fields, normalized)
        if not active:
            expected = _expected_subtasks_from_normalized(normalized)
            active = {
                "task_id": None,
                "overall_task_id": None,
                "task_type": task_type,
                "task_category": category,
                "user_id": user_id,
                "expected_subtasks": expected,
                "completed_subtasks": 0,
                "current_subtask_seq": 0,
                "task_name": normalized.get("task_name"),
                "gender": normalized.get("gender"),
                "raw": copy.deepcopy(raw_fields),
                "normalized": copy.deepcopy(normalized),
            }
            _active_external_tasks[key] = active
            logger.info(
                "[REMOTE_TASK_COUNT] external implicit context from simple task_start "
                "category=%s task_type=%s user=%s total=%s",
                category,
                task_type,
                user_id,
                expected,
            )

        active["current_subtask_seq"] = int(active.get("current_subtask_seq") or 0) + 1
        seq = active["current_subtask_seq"]
        overall_tid = active.get("overall_task_id")
        tid = generate_task_id()
        active["task_id"] = tid
        active["current_subtask_task_id"] = tid
        db_manager.create_task_run(
            task_id=tid,
            task_type=task_type,
            user_id=user_id,
            expected_subtasks=1,
            started_at_ms=ts,
            config_json=_json_dump({
                **_task_run_config(category, active.get("raw") or raw_fields, active.get("normalized") or normalized),
                "overall_task_id": overall_tid,
                "sub_task_seq": seq,
            }),
            raw_message_json=raw,
        )
        if overall_tid is not None:
            db_manager.update_task_run_progress(task_id=overall_tid, current_subtask_seq=seq, raw_message_json=raw)
        db_manager.record_task_event(
            task_id=tid,
            task_type=task_type,
            user_id=user_id,
            event_type="sub_start",
            sub_task_seq=seq,
            timestamp_ms=ts,
            payload_json=_json_dump({"task_category": category, "sub_task_seq": seq}),
            raw_message_json=raw,
        )
        _start_external_marker_context(
            active,
            category,
            message_data,
            timestamp_ms=ts,
            gaze_svc=gaze_svc,
            physio_svc=physio_svc,
            external_collectors=external_collectors,
            event_type="sub_start",
            sub_task_seq=seq,
        )
        logger.info(
            "[REMOTE_TASK_COUNT] external sub_start stored category=%s user=%s task_id=%s sub_task_seq=%s",
            category,
            user_id,
            tid,
            seq,
        )
        return [{"type": "platform_task_ack", "status": "ok",
                 "task_id": tid, "task_type": task_type,
                 "task_category": category, "entry_mode": "external_lifecycle",
                 "sub_task_seq": seq,
                 "diagnostics": _external_task_diagnostics(
                     message_data,
                     category,
                     action,
                     user_id,
                     task_type,
                     external_collectors=external_collectors,
                     active=active,
                     event_role="subtask_start",
                 )}]

    try:
        raw_fields, normalized = _normalize_platform_task_fields(message_data, category)
        normalized = _attach_entry_semantics(normalized, category, "external_lifecycle")
    except ValueError:
        raw_fields = {k: v for k, v in message_data.items() if k != "type"}
        normalized = _attach_entry_semantics(
            {"platform_task_id": user_id, "task_name": message_data.get("TaskName")},
            category,
            "external_lifecycle",
        )

    active = _load_active_external_task(category, user_id, raw_fields, normalized)
    if not active:
        logger.warning(
            "[REMOTE_TASK_COUNT] external event missing active category=%s user=%s "
            "action=%s active_keys=%s",
            category,
            user_id,
            action,
            list(_active_external_tasks.keys()),
        )
        return [{"type": "platform_task_ack", "status": "error",
                 "message": f"no active {category} task for user {user_id}",
                 "diagnostics": _external_task_diagnostics(
                     message_data,
                     category,
                     action,
                     user_id,
                     task_type,
                     external_collectors=external_collectors,
                     active=None,
                     event_role="missing_active",
                 )}]

    if action == "sub_end":
        completed_before = int(active.get("completed_subtasks") or 0)
        current_seq = int(active.get("current_subtask_seq") or 0)
        seq = current_seq if current_seq > completed_before else completed_before + 1
        active["current_subtask_seq"] = seq
        overall_tid = active.get("overall_task_id")
        tid = active.get("current_subtask_task_id")
        had_active_subtask = tid is not None
        if tid is None:
            tid = generate_task_id()
            active["task_id"] = tid
            active["current_subtask_task_id"] = tid
            db_manager.create_task_run(
                task_id=tid,
                task_type=task_type,
                user_id=user_id,
                expected_subtasks=1,
                started_at_ms=ts,
                config_json=_json_dump({
                    **_task_run_config(category, active.get("raw") or raw_fields, active.get("normalized") or normalized),
                    "overall_task_id": overall_tid,
                    "sub_task_seq": seq,
                }),
                raw_message_json=raw,
            )
        result = message_data.get("result") if isinstance(message_data.get("result"), dict) else {}
        db_manager.record_task_event(
            task_id=tid,
            task_type=task_type,
            user_id=user_id,
            event_type="sub_end",
            sub_task_seq=seq,
            timestamp_ms=ts,
            payload_json=_json_dump({"task_category": category, "sub_task_seq": seq, "has_result": bool(result)}),
            raw_message_json=raw,
        )
        if result:
            metrics = _result_metrics(result)
            db_manager.record_subtask_result(
                task_id=tid,
                task_type=task_type,
                user_id=user_id,
                sub_task_seq=seq,
                result_json=_json_dump(result),
                timestamp_ms=ts,
                **metrics,
            )
        completed = completed_before + 1
        active["completed_subtasks"] = completed
        expected = int(active.get("expected_subtasks") or 0)
        status = "completed" if expected and completed >= expected else "active"
        db_manager.update_task_run_progress(
            task_id=tid,
            completed_subtasks=1,
            current_subtask_seq=seq,
            status="completed",
            completed_at_ms=ts,
            raw_message_json=raw,
        )
        if overall_tid is not None:
            db_manager.update_task_run_progress(
                task_id=overall_tid,
                completed_subtasks=completed,
                current_subtask_seq=seq,
                status=status,
                completed_at_ms=ts if status == "completed" else None,
                raw_message_json=raw,
            )
        if status == "completed":
            active["task_id"] = tid
        if had_active_subtask:
            _stop_external_marker_context(
                active,
                category,
                "sub_end",
                message_data,
                gaze_svc=gaze_svc,
                physio_svc=physio_svc,
                external_collectors=external_collectors,
                sub_task_seq=seq,
                timestamp_ms=ts,
                extra=metrics if result else None,
            )
        else:
            logger.warning(
                "[EXTERNAL_COLLECTOR_DIAG] skip collector stop for %s task_id=%s: no active subtask start was recorded",
                action,
                tid,
            )
        if status == "completed":
            _active_external_tasks.pop(key, None)
        else:
            active.pop("current_subtask_task_id", None)
            active.pop("gaze_task_id", None)
            active["task_id"] = overall_tid
        logger.info(
            "[REMOTE_TASK_COUNT] external sub_end stored category=%s user=%s task_id=%s "
            "overall_task_id=%s sub_task_seq=%s completed=%s total=%s status=%s has_result=%s",
            category,
            user_id,
            tid,
            overall_tid,
            seq,
            completed,
            expected,
            status,
            bool(result),
        )
        return [{"type": "platform_task_ack", "status": "ok",
                 "task_id": tid, "overall_task_id": overall_tid, "task_type": task_type,
                 "task_category": category, "entry_mode": "external_lifecycle",
                 "sub_task_seq": seq, "completed_subtasks": completed,
                 "expected_subtasks": expected, "task_status": status,
                 "diagnostics": _external_task_diagnostics(
                     message_data,
                     category,
                     action,
                     user_id,
                     task_type,
                     external_collectors=external_collectors,
                     active=active,
                     event_role="subtask_end" if had_active_subtask else "subtask_end_without_start",
                 )}]

    tid = active.get("current_subtask_task_id") or active.get("overall_task_id") or active.get("task_id")

    if action == "task_end":
        overall_tid = active.get("overall_task_id")
        if active.get("current_subtask_task_id"):
            db_manager.update_task_run_progress(
                task_id=active["current_subtask_task_id"],
                status="completed",
                completed_at_ms=ts,
                raw_message_json=raw,
            )
        if overall_tid is not None and overall_tid != tid:
            db_manager.update_task_run_progress(
                task_id=overall_tid,
                status="completed",
                completed_at_ms=ts,
                raw_message_json=raw,
            )
        db_manager.record_task_event(
            task_id=tid,
            task_type=task_type,
            user_id=user_id,
            event_type="task_end",
            timestamp_ms=ts,
            payload_json=_json_dump({"task_category": category, "overall_task_id": overall_tid}),
            raw_message_json=raw,
        )
        if active.get("current_subtask_task_id"):
            active["task_id"] = active["current_subtask_task_id"]
        _stop_external_marker_context(
            active,
            category,
            "task_end",
            message_data,
            gaze_svc=gaze_svc,
            physio_svc=physio_svc,
            external_collectors=external_collectors,
            timestamp_ms=ts,
        )
        _active_external_tasks.pop(key, None)
        logger.info(
            "[REMOTE_TASK_COUNT] external task_end category=%s user=%s task_id=%s overall_task_id=%s "
            "final_sub_task_seq=%s active_keys=%s",
            category,
            user_id,
            tid,
            overall_tid,
            active.get("current_subtask_seq"),
            list(_active_external_tasks.keys()),
        )
        return [{"type": "platform_task_ack", "status": "ok",
                 "task_id": tid, "overall_task_id": overall_tid, "task_type": task_type,
                 "task_category": category, "entry_mode": "external_lifecycle",
                 "event_type": "task_end"}]

    return [{"type": "platform_task_ack", "status": "error",
             "message": f"unknown Action: {action}"}]


def handle_platform_task_result_ws(
    message_data: Dict[str, Any],
    gaze_svc: Any = None,
    physio_svc: Any = None,
    external_collectors: Any = None,
) -> List[Dict[str, Any]]:
    logger.info("RAW platform_task_result: %s", json.dumps(message_data, ensure_ascii=False))
    user_id = str(message_data.get("ID") or "").strip()
    if not user_id:
        return [{"type": "platform_task_ack", "status": "error",
                 "message": "platform_task_result requires non-empty ID"}]

    matched_key = None
    active = None
    for candidate_key, candidate_active in _active_external_tasks.items():
        if candidate_key[1] == user_id:
            matched_key = candidate_key
            active = candidate_active
            break
    if not active:
        return [{"type": "platform_task_ack", "status": "error",
                 "message": f"no active task for user {user_id}"}]

    category = matched_key[0]
    task_type = active.get("task_type") or _task_type_for_external_category(category)
    ts = int(_time.time() * 1000)
    raw = _json_dump(message_data)
    seq = int(active.get("current_subtask_seq") or active.get("completed_subtasks") or 0)
    if seq <= 0:
        seq = 1
    overall_tid = active.get("overall_task_id")
    tid = active.get("current_subtask_task_id")
    if tid is None:
        tid = generate_task_id()
        active["task_id"] = tid
        active["current_subtask_task_id"] = tid
        db_manager.create_task_run(
            task_id=tid,
            task_type=task_type,
            user_id=user_id,
            expected_subtasks=1,
            started_at_ms=ts,
            config_json=_json_dump({
                **_task_run_config(category, active.get("raw") or {}, active.get("normalized") or {}),
                "overall_task_id": overall_tid,
                "sub_task_seq": seq,
            }),
            raw_message_json=raw,
        )
    result = {k: v for k, v in message_data.items() if k not in ("type", "TaskName", "ID")}
    db_manager.record_task_event(
        task_id=tid,
        task_type=task_type,
        user_id=user_id,
        event_type="task_result",
        sub_task_seq=seq,
        timestamp_ms=ts,
        payload_json=_json_dump({"task_category": category, "sub_task_seq": seq}),
        raw_message_json=raw,
    )
    db_manager.record_subtask_result(
        task_id=tid,
        task_type=task_type,
        user_id=user_id,
        sub_task_seq=seq,
        result_json=_json_dump(result),
        timestamp_ms=ts,
        **_result_metrics(result),
    )
    db_manager.update_task_run_progress(task_id=tid, status="completed", completed_at_ms=ts, raw_message_json=raw)
    if overall_tid is not None:
        completed = int(active.get("completed_subtasks") or 0) + 1
        active["completed_subtasks"] = completed
        db_manager.update_task_run_progress(
            task_id=overall_tid,
            completed_subtasks=completed,
            current_subtask_seq=seq,
            status="completed",
            completed_at_ms=ts,
            raw_message_json=raw,
        )
    _stop_external_marker_context(
        active,
        category,
        "task_result",
        message_data,
        gaze_svc=gaze_svc,
        physio_svc=physio_svc,
        external_collectors=external_collectors,
        sub_task_seq=seq,
        timestamp_ms=ts,
    )
    _active_external_tasks.pop(matched_key, None)
    logger.info("[REMOTE_TASK_COUNT] platform_task_result stored task_id=%s overall_task_id=%s category=%s active_keys=%s",
                tid, overall_tid, category, list(_active_external_tasks.keys()))
    return [{"type": "platform_task_ack", "status": "ok",
             "task_id": tid, "overall_task_id": overall_tid, "task_type": task_type,
             "task_category": category, "entry_mode": "external_lifecycle",
             "event_type": "task_result"}]


async def handle_platform_task_ws(
    websocket_server: Any,
    sender_client_id: str,
    message_data: Dict[str, Any],
    gaze_svc: Any = None,
    physio_svc: Any = None,
    external_collectors: Any = None,
) -> List[Dict[str, Any]]:
    logger.info("RAW platform message: %s",
                json.dumps(message_data, ensure_ascii=False))
    if str(message_data.get("Action") or "task_start").strip() == "task_start":
        logger.info(
            "TASK_START WebSocket fields: %s",
            json.dumps(message_data, ensure_ascii=False, sort_keys=True),
        )

    category = _classify_task_category(message_data)
    if category in ("platform_control", "weapon_launch"):
        return _handle_external_task(
            message_data,
            category,
            gaze_svc=gaze_svc,
            physio_svc=physio_svc,
            external_collectors=external_collectors,
        )

    if not _is_web_overlay_category(category):
        return [{"type": "platform_task_ack", "status": "error",
                 "message": f"unknown task category for TaskName: {message_data.get('TaskName')}"}]

    # ---- radar / sa 入口：外部包是 overall task_start 定义，真实开始由 Web 任务入口触发 ----
    try:
        normalized = apply_platform_task_message(message_data)
    except ValueError as e:
        return [{"type": "platform_task_ack", "status": "error", "message": str(e)}]

    global _pending
    relay = {
        "type": "platform_task_config",
        "raw": _pending["raw"],
        "normalized": _pending["normalized"],
        "autostart": True,
        "userId": str(_pending["normalized"].get("platform_task_id", "")),
    }
    recipients = await websocket_server.broadcast_to_clients_except(relay, sender_client_id)
    logger.info("platform_task_config broadcast to %s client(s) (excluded sender)", recipients)
    return [
        {
            "type": "platform_task_ack",
            "status": "ok",
            "entry_mode": "web_overlay",
            "task_type": normalized.get("task_type"),
            "task_category": normalized.get("task_category"),
            "recipients": recipients,
            "normalized": normalized,
        }
    ]
