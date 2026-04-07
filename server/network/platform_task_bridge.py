"""
平台任务 WS：解析平台包、维护 pending、供 task_start 合并；platform_task 向其它连接广播 platform_task_config。
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from managers import config_manager, get_logger

logger = get_logger("platform_task")

_pending: Optional[Dict[str, Any]] = None


def _valid_levels(config: Dict[str, Any]) -> List[str]:
    return [lv.get("level") for lv in config.get("levels", []) if lv.get("level")]


def _normalize_current_level(raw: Any, config: Dict[str, Any]) -> str:
    valid = _valid_levels(config)
    default = config.get("current_level") or (valid[0] if valid else "L0")
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
        if cand in valid:
            return cand
    try:
        n = int(float(s))
        cand = f"L{n}"
        if cand in valid:
            return cand
        if valid and 0 <= n < len(valid):
            return valid[n]
    except ValueError:
        pass
    return default


def _normalize_difficulty_key(raw: Any, config: Dict[str, Any]) -> str:
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
        # 平台协议：1=高, 2=中, 3=低（与直觉相反）
        if n <= 1:
            pick = "high" if "high" in diff_levels else default
        elif n == 2:
            pick = "medium" if "medium" in diff_levels else default
        else:  # n >= 3
            pick = "low" if "low" in diff_levels else default
        if pick in diff_levels:
            return pick
    except ValueError:
        pass
    if "低" in str(raw) or s == "low":
        return "low" if "low" in diff_levels else default
    if "高" in str(raw) or s == "high":
        return "high" if "high" in diff_levels else default
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


def _build_overlay(normalized: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    gs = config.get("game_settings", {})
    diff_levels = gs.get("difficulty_levels", {}) or {}
    dkey = normalized["difficulty_key"]
    diff_conf = copy.deepcopy(diff_levels.get(dkey, {}))
    diff_conf["difficulty_name"] = dkey

    level_name = normalized["current_level"]
    ai_conf = None
    for lv in config.get("levels", []):
        if lv.get("level") == level_name:
            ai_conf = copy.deepcopy(lv)
            break

    overlay: Dict[str, Any] = {
        "difficulty_name": dkey,
        "difficulty_config": diff_conf,
        "is_ai_active": normalized["include_ai"],
        "ai_level_name": level_name,
        "ai_level_config": ai_conf,
        "audio_enabled": gs.get("audio_enabled", True),
    }
    if normalized.get("repetition_total_override") is not None:
        overlay["repetition_total_override"] = normalized["repetition_total_override"]
    return overlay


def apply_platform_task_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """校验并写入全局 pending。返回 normalized 摘要。"""
    global _pending
    task_id = message.get("ID")
    if task_id is None or str(task_id).strip() == "":
        raise ValueError("platform_task requires non-empty ID")

    cfg = config_manager.get_config()
    raw = {k: v for k, v in message.items() if k != "type"}

    ai_raw = message.get("AIAutonomyLevel")
    if ai_raw is None:
        ai_raw = message.get("AIAutonomyLeve")
    current_level = _normalize_current_level(ai_raw, cfg)
    difficulty_key = _normalize_difficulty_key(message.get("Difficulty"), cfg)
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

    normalized = {
        "task_name": message.get("TaskName"),
        "platform_task_id": message.get("ID"),
        "gender": message.get("Gender"),
        "default_control_mode": message.get("DefaultControlMode"),
        "ai_autonomy_level": current_level,
        "current_level": current_level,
        "task_mode": message.get("TaskMode"),
        "difficulty_key": difficulty_key,
        "difficulty_raw": message.get("Difficulty"),
        "task_number": message.get("TaskNumber"),
        "ai_precision": message.get("aiprecision"),
        "include_ai": include_ai,
        "is_practice": is_practice,
        "repetition_total_override": rep_override,
        "web_task_kind": _infer_web_task_kind(message),
    }
    overlay = _build_overlay(normalized, cfg)
    _pending = {"raw": raw, "normalized": normalized, "overlay": overlay}
    logger.info(
        "platform_task pending set: id=%s difficulty=%s level=%s include_ai=%s",
        normalized["platform_task_id"],
        difficulty_key,
        current_level,
        include_ai,
    )
    return normalized


def peek_pending_include_ai() -> Optional[bool]:
    if _pending and _pending.get("normalized"):
        return _pending["normalized"].get("include_ai")
    return None


def consume_pending_for_task_start() -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """返回 (scenario_overlay, platform_meta)。消费并清除 pending。"""
    global _pending
    if not _pending:
        return None, None
    overlay = copy.deepcopy(_pending.get("overlay") or {})
    meta = {
        "raw": copy.deepcopy(_pending.get("raw")),
        "normalized": copy.deepcopy(_pending.get("normalized")),
    }
    _pending = None
    return overlay, meta


async def handle_platform_task_ws(websocket_server: Any, sender_client_id: str, message_data: Dict[str, Any]) -> List[Dict[str, Any]]:
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
            "recipients": recipients,
            "normalized": normalized,
        }
    ]
