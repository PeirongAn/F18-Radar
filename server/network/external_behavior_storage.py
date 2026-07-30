from __future__ import annotations

import json
import math
import re
import time
from typing import Any, Dict, Optional

from managers import db_manager, get_logger


SUPPORTED_TASK_TYPES = {"PLATFORM_CONTROL", "WEAPON_FIRING"}
SUPPORTED_OWNERS = {"User", "AI"}
SUPPORTED_SIDES = {"Our", "Enemy"}
LEGACY_BEHAVIOR_TYPES = {
    "fire": "fire",
    "leftpedal": "left_pedal",
    "rightpedal": "right_pedal",
    "accelerator": "accelerator",
    "switchmode": "switch_mode",
    "joystick": "joystick",
    "okbutton": "ok_button",
}


class ExternalBehaviorError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _normalize_task_type(value: Any) -> str:
    task_type = str(value or "").strip().upper()
    if task_type == "WEAPON_LAUNCH":
        task_type = "WEAPON_FIRING"
    if task_type not in SUPPORTED_TASK_TYPES:
        raise ExternalBehaviorError(
            "UNSUPPORTED_TASK_TYPE",
            "task_type must be PLATFORM_CONTROL or WEAPON_FIRING",
        )
    return task_type


def _normalize_behavior_type(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ExternalBehaviorError("UNSUPPORTED_BEHAVIOR_TYPE", "data.type is required")
    legacy = LEGACY_BEHAVIOR_TYPES.get(raw.replace("_", "").lower())
    if legacy:
        return legacy
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", raw).replace("-", "_").lower()
    snake = re.sub(r"_+", "_", snake).strip("_")
    if not snake or not re.fullmatch(r"[a-z][a-z0-9_]*", snake):
        raise ExternalBehaviorError(
            "UNSUPPORTED_BEHAVIOR_TYPE",
            "data.type must contain a stable behavior name",
        )
    return snake


def _optional_timestamp(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ExternalBehaviorError(
            "INVALID_TIMESTAMP",
            "data.timestamp must be a Unix millisecond integer or null",
        )
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        raise ExternalBehaviorError(
            "INVALID_TIMESTAMP",
            "data.timestamp must be a Unix millisecond integer or null",
        )
    if timestamp <= 0:
        raise ExternalBehaviorError(
            "INVALID_TIMESTAMP",
            "data.timestamp must be greater than zero",
        )
    return timestamp


def _validate_numeric_posture(pose_data: Any) -> list:
    if not isinstance(pose_data, list) or not pose_data:
        raise ExternalBehaviorError(
            "INVALID_POSE_DATA",
            "data.pose_data must be a non-empty array",
        )
    for index, pose in enumerate(pose_data):
        if not isinstance(pose, dict):
            raise ExternalBehaviorError(
                "INVALID_POSE_DATA",
                f"pose_data[{index}] must be an object",
            )
        if str(pose.get("Side") or "").strip() not in SUPPORTED_SIDES:
            raise ExternalBehaviorError(
                "INVALID_POSE_DATA",
                f"pose_data[{index}].Side must be Our or Enemy",
            )
        if not str(pose.get("ID") or "").strip():
            raise ExternalBehaviorError(
                "INVALID_POSE_DATA",
                f"pose_data[{index}].ID is required",
            )
        posture = pose.get("posture")
        if not isinstance(posture, dict) or not posture:
            raise ExternalBehaviorError(
                "INVALID_POSE_DATA",
                f"pose_data[{index}].posture must be a non-empty object",
            )
        for name, value in posture.items():
            if isinstance(value, bool):
                raise ExternalBehaviorError(
                    "INVALID_POSE_DATA",
                    f"pose_data[{index}].posture.{name} must be numeric",
                )
            try:
                number = float(value)
            except (TypeError, ValueError):
                raise ExternalBehaviorError(
                    "INVALID_POSE_DATA",
                    f"pose_data[{index}].posture.{name} must be numeric",
                )
            if not math.isfinite(number):
                raise ExternalBehaviorError(
                    "INVALID_POSE_DATA",
                    f"pose_data[{index}].posture.{name} must be finite",
                )
    try:
        return json.loads(json.dumps(pose_data, ensure_ascii=False))
    except (TypeError, ValueError):
        raise ExternalBehaviorError(
            "INVALID_POSE_DATA",
            "data.pose_data must be JSON serializable",
        )


def _validate_message(message: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(message, dict) or message.get("type") != "external_behavior_record":
        raise ExternalBehaviorError(
            "INVALID_PAYLOAD",
            "message type must be external_behavior_record",
        )
    schema_version = str(message.get("schema_version") or "").strip()
    client_event_id = str(message.get("client_event_id") or "").strip()
    data = message.get("data")
    if not schema_version:
        raise ExternalBehaviorError("INVALID_PAYLOAD", "schema_version is required")
    if not client_event_id:
        raise ExternalBehaviorError("INVALID_PAYLOAD", "client_event_id is required")
    if not isinstance(data, dict):
        raise ExternalBehaviorError("INVALID_PAYLOAD", "data must be a JSON object")

    user_id = str(data.get("PlayerID") or "").strip()
    if not user_id:
        raise ExternalBehaviorError("INVALID_PAYLOAD", "data.PlayerID is required")
    task_type = _normalize_task_type(data.get("task_type"))
    behavior_type = _normalize_behavior_type(data.get("type"))
    owner = str(data.get("owner") or "").strip()
    if owner not in SUPPORTED_OWNERS:
        raise ExternalBehaviorError("INVALID_OWNER", "data.owner must be User or AI")
    button = data.get("button")
    if button in ("", None):
        button = None
    elif not isinstance(button, str):
        raise ExternalBehaviorError("INVALID_BUTTON", "data.button must be a string or null")

    requested_task_id = data.get("task_id")
    if requested_task_id in ("", None):
        requested_task_id = None
    else:
        try:
            requested_task_id = int(requested_task_id)
        except (TypeError, ValueError):
            raise ExternalBehaviorError(
                "INVALID_PAYLOAD",
                "data.task_id must be an integer or null",
            )

    return {
        "schema_version": schema_version,
        "client_event_id": client_event_id,
        "user_id": user_id,
        "task_type": task_type,
        "requested_task_id": requested_task_id,
        "button": button,
        "behavior_type": behavior_type,
        "owner": owner,
        "is_active": not behavior_type.endswith("_end"),
        "source_timestamp_ms": _optional_timestamp(data.get("timestamp")),
        "pose_data": _validate_numeric_posture(data.get("pose_data")),
    }


class ExternalBehaviorStore:
    def __init__(self, database_manager=None):
        self.db = database_manager or db_manager
        self.logger = get_logger("external_behavior")

    def _resolve_task(self, normalized: Dict[str, Any]) -> Dict[str, Any]:
        user_id = normalized["user_id"]
        task_type = normalized["task_type"]
        requested_task_id = normalized["requested_task_id"]
        if requested_task_id is not None:
            run = self.db.get_task_run(requested_task_id)
            if (
                not run
                or run.get("status") != "active"
                or str(run.get("user_id") or "") != user_id
                or str(run.get("task_type") or "") != task_type
            ):
                raise ExternalBehaviorError(
                    "TASK_ID_MISMATCH",
                    "data.task_id does not match the current active user and task type",
                )
            return run

        try:
            from network.platform_task_bridge import get_active_external_task_context

            context = get_active_external_task_context(user_id, task_type)
        except Exception:
            context = None
        if context:
            run = self.db.get_task_run(context.get("task_id"))
            if run:
                return run

        runs = self.db.find_active_task_runs(user_id, task_type)
        if not runs:
            raise ExternalBehaviorError(
                "ACTIVE_TASK_NOT_FOUND",
                "no active subtask matches PlayerID and task_type",
            )
        if len(runs) > 1:
            raise ExternalBehaviorError(
                "ACTIVE_TASK_AMBIGUOUS",
                "multiple active subtasks match PlayerID and task_type",
            )
        return runs[0]

    def write(self, message: Dict[str, Any]) -> Dict[str, Any]:
        received_at_ms = int(time.time() * 1000)
        normalized = _validate_message(message)
        raw_payload_json = json.dumps(
            message,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        existing = self.db.get_external_behavior_record(normalized["client_event_id"])
        if existing is not None:
            if existing["raw_payload_json"] != raw_payload_json:
                raise ExternalBehaviorError(
                    "CLIENT_EVENT_ID_CONFLICT",
                    "client_event_id was already used by a different behavior payload",
                )
            run = self.db.get_task_run(existing["task_id"]) or {
                "task_id": existing["task_id"],
                "group_id": None,
            }
            existing["duplicate"] = True
            return self._success_reply(normalized, run, existing)

        run = self._resolve_task(normalized)
        stored = self.db.insert_external_behavior_record(
            client_event_id=normalized["client_event_id"],
            task_id=int(run["task_id"]),
            user_id=normalized["user_id"],
            task_type=normalized["task_type"],
            button=normalized["button"],
            behavior_type=normalized["behavior_type"],
            owner=normalized["owner"],
            is_active=normalized["is_active"],
            source_timestamp_ms=normalized["source_timestamp_ms"],
            received_at_ms=received_at_ms,
            pose_data_json=json.dumps(
                normalized["pose_data"],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            schema_version=normalized["schema_version"],
            raw_payload_json=raw_payload_json,
        )
        if stored["duplicate"] and stored["raw_payload_json"] != raw_payload_json:
            raise ExternalBehaviorError(
                "CLIENT_EVENT_ID_CONFLICT",
                "client_event_id was already used by a different behavior payload",
            )
        self.logger.info(
            "external behavior stored id=%s task_id=%s task_group_id=%s "
            "user_id=%s task_type=%s behavior_type=%s owner=%s duplicate=%s",
            stored["id"],
            run["task_id"],
            run.get("group_id"),
            normalized["user_id"],
            normalized["task_type"],
            normalized["behavior_type"],
            normalized["owner"],
            stored["duplicate"],
        )
        return self._success_reply(normalized, run, stored)

    @staticmethod
    def _success_reply(
        normalized: Dict[str, Any],
        run: Dict[str, Any],
        stored: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "type": "external_behavior_record_result",
            "ok": True,
            "client_event_id": normalized["client_event_id"],
            "behavior_record_id": int(stored["id"]),
            "resolved_task_id": int(run["task_id"]),
            "task_id": int(run["task_id"]),
            "task_group_id": run.get("group_id"),
            "task_type": normalized["task_type"],
            "behavior_type": normalized["behavior_type"],
            "pose_record_count": len(normalized["pose_data"]),
            "duplicate": bool(stored["duplicate"]),
            "server_time_us": int(time.time() * 1_000_000),
        }


_store = ExternalBehaviorStore()


def handle_external_behavior_record(message: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return _store.write(message)
    except ExternalBehaviorError as exc:
        return {
            "type": "external_behavior_record_result",
            "ok": False,
            "client_event_id": str(message.get("client_event_id") or ""),
            "error": {"code": exc.code, "message": str(exc)},
            "server_time_us": int(time.time() * 1_000_000),
        }
    except Exception as exc:
        get_logger("external_behavior").error(
            "external behavior write failed: %s",
            exc,
            exc_info=True,
        )
        return {
            "type": "external_behavior_record_result",
            "ok": False,
            "client_event_id": str(message.get("client_event_id") or ""),
            "error": {"code": "INTERNAL_ERROR", "message": str(exc)},
            "server_time_us": int(time.time() * 1_000_000),
        }
