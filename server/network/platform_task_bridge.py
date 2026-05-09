"""
平台任务 WS：解析平台包、维护 pending、供 task_start 合并；platform_task 向其它连接广播 platform_task_config。
支持外部平台（平台控制 / 武器发射）的生命周期记录和结果存储。
"""
from __future__ import annotations

import copy
import json
import time as _time
from typing import Any, Dict, List, Optional, Tuple

from managers import config_manager, db_manager, generate_task_id, get_logger

logger = get_logger("platform_task")

_pending: Optional[Dict[str, Any]] = None

# 外部任务活跃状态  key=(task_category, user_id)
_active_external_tasks: Dict[Tuple[str, str], Dict[str, Any]] = {}


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
        # 平台协议：1=低自主等级, 2=中自主等级, 3=高自主等级；
        # 本地配置使用 L0/L1/L2，因此数字协议需要转成 0-based level。
        if n <= 1:
            idx = 0
        elif n == 2:
            idx = 1
        else:
            idx = 2
        cand = f"L{idx}"
        if cand in valid:
            return cand
        if valid:
            return valid[min(idx, len(valid) - 1)]
    except ValueError:
        pass
    return default


def _normalize_difficulty_display_key(raw: Any, engine_key: str) -> str:
    """保留平台业务难度给问卷展示：1=高, 2=中, 3=低。"""
    if raw is None or str(raw).strip() == "":
        return engine_key
    s = str(raw).strip()
    sl = s.lower()
    try:
        n = int(float(s))
        if n <= 1:
            return "1"
        if n == 2:
            return "2"
        return "3"
    except ValueError:
        pass
    if sl in ("high", "medium", "low"):
        return sl
    if "高" in s:
        return "high"
    if "中" in s:
        return "medium"
    if "低" in s:
        return "low"
    return engine_key


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
    difficulty_display = _normalize_difficulty_display_key(message.get("Difficulty"), difficulty_key)
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
        "difficulty_display": difficulty_display,
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


def _handle_external_task(message_data: Dict[str, Any], category: str) -> List[Dict[str, Any]]:
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

    if action == "task_start":
        tid = generate_task_id()
        _active_external_tasks[key] = {
            "task_id": tid, "sub_task_seq": 0,
            "task_name": task_name, "gender": gender,
        }
        db_manager.record_external_task(
            task_id=tid, task_category=category, event_type="task_start",
            raw_message=raw, timestamp=ts, user_id=user_id,
            task_name=task_name, gender=gender,
        )
        logger.info("external task_start: category=%s user=%s task_id=%s",
                     category, user_id, tid)
        return [{"type": "platform_task_ack", "status": "ok",
                 "task_id": tid, "task_category": category}]

    active = _active_external_tasks.get(key)
    if not active:
        return [{"type": "platform_task_ack", "status": "error",
                 "message": f"no active {category} task for user {user_id}"}]
    tid = active["task_id"]

    if action == "sub_start":
        active["sub_task_seq"] += 1
        seq = active["sub_task_seq"]
        db_manager.record_external_task(
            task_id=tid, task_category=category, event_type="sub_start",
            raw_message=raw, timestamp=ts, user_id=user_id,
            task_name=task_name, gender=gender, sub_task_seq=seq,
        )
        logger.info("external sub_start: task_id=%s seq=%s", tid, seq)
        return [{"type": "platform_task_ack", "status": "ok",
                 "task_id": tid, "sub_task_seq": seq}]

    if action == "sub_end":
        seq = active["sub_task_seq"]
        db_manager.record_external_task(
            task_id=tid, task_category=category, event_type="sub_end",
            raw_message=raw, timestamp=ts, user_id=user_id,
            task_name=task_name, gender=gender, sub_task_seq=seq,
        )
        logger.info("external sub_end: task_id=%s seq=%s", tid, seq)

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
            )
            logger.info("external sub_end with result: task_id=%s seq=%s", tid, seq)

        return [{"type": "platform_task_ack", "status": "ok",
                 "task_id": tid, "sub_task_seq": seq}]

    if action == "task_end":
        db_manager.record_external_task(
            task_id=tid, task_category=category, event_type="task_end",
            raw_message=raw, timestamp=ts, user_id=user_id,
            task_name=task_name, gender=gender,
        )
        _active_external_tasks.pop(key, None)
        logger.info("external task_end: task_id=%s", tid)
        return [{"type": "platform_task_ack", "status": "ok",
                 "task_id": tid, "event_type": "task_end"}]

    return [{"type": "platform_task_ack", "status": "error",
             "message": f"unknown Action: {action}"}]


def handle_platform_task_result_ws(message_data: Dict[str, Any]) -> List[Dict[str, Any]]:
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

    if not active:
        logger.warning("platform_task_result: no active task for user %s, "
                       "storing with task_id=-1", user_id)
        tid = -1
        category = "unknown"
    else:
        tid = active["task_id"]
        category = matched_key[0]

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
    )

    if matched_key:
        _active_external_tasks.pop(matched_key, None)

    logger.info("platform_task_result stored: task_id=%s category=%s", tid, category)
    return [{"type": "platform_task_ack", "status": "ok",
             "task_id": tid, "event_type": "task_result"}]


async def handle_platform_task_ws(websocket_server: Any, sender_client_id: str, message_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    logger.info("RAW platform message: %s",
                json.dumps(message_data, ensure_ascii=False))

    category = _classify_task_category(message_data)
    if category in ("platform_control", "weapon_launch"):
        return _handle_external_task(message_data, category)

    # ---- 现有 radar / sa 逻辑 ----
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
