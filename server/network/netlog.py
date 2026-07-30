import json
import time
import uuid
from typing import Any, Dict, Optional


SUMMARY_KEYS = (
    "type",
    "TaskName",
    "task_id",
    "task_group_id",
    "overall_task_id",
    "ID",
    "user_id",
    "userId",
    "taskType",
    "task_type",
    "task_category",
    "category",
    "status",
    "event_type",
    "sub_task_seq",
    "expected_subtasks",
    "completed_subtasks",
    "task_status",
    "next_subtask_task_id",
    "ok",
    "client_event_id",
    "behavior_record_id",
    "behavior_type",
    "client_snapshot_id",
    "pose_snapshot_id",
    "resolved_task_id",
    "pose_record_count",
    "duplicate",
    "box_visible",
    "name",
    "run_id",
    "trial_id",
)

INTERFACE_PREFIXES = ("/api/", "/tobii/", "/physio/")
NOISY_GET_PATHS = {"/tobii/gaze_point", "/tobii/gaze_data"}
NOISY_WS_TYPES = {"ue_ping"}


def request_id() -> str:
    return uuid.uuid4().hex[:8]


def now_ms() -> float:
    return time.perf_counter() * 1000.0


def duration_ms(start_ms: float) -> int:
    return max(0, int(now_ms() - start_ms))


def remote_from_request(request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.remote or "-"


def remote_from_websocket(websocket) -> str:
    remote = getattr(websocket, "remote_address", None)
    if isinstance(remote, tuple):
        return ":".join(str(part) for part in remote if part is not None)
    if remote:
        return str(remote)
    return "-"


def should_log_http(path: str, method: str) -> bool:
    if method.upper() == "GET" and path in NOISY_GET_PATHS:
        return False
    return path.startswith(INTERFACE_PREFIXES)


def should_log_ws_message(message_data: Any) -> bool:
    if not isinstance(message_data, dict):
        return True
    return message_data.get("type") not in NOISY_WS_TYPES


def payload_summary(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    summary: Dict[str, Any] = {}
    for key in SUMMARY_KEYS:
        if key in payload and payload[key] not in (None, ""):
            summary[key] = payload[key]

    answers = payload.get("answers")
    if isinstance(answers, dict):
        summary["answers"] = len(answers)
    elif isinstance(answers, list):
        summary["answers"] = len(answers)

    return summary


def format_fields(fields: Dict[str, Any]) -> str:
    parts = []
    for key, value in fields.items():
        if isinstance(value, bool):
            value = str(value).lower()
        elif isinstance(value, (dict, list, tuple)):
            value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        parts.append(f"{key}={value}")
    return " ".join(parts)


async def http_request_summary(request) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    body_bytes = 0

    content_length = request.headers.get("Content-Length")
    if content_length:
        try:
            body_bytes = int(content_length)
        except ValueError:
            body_bytes = 0

    if request.can_read_body:
        content_type = request.headers.get("Content-Type", "")
        if "json" in content_type.lower():
            try:
                raw = await request.text()
                body_bytes = len(raw.encode("utf-8"))
                if raw:
                    summary.update(payload_summary(json.loads(raw)))
            except Exception:
                summary["body"] = "invalid_json"

    for key in ("user_id", "userId", "task_id", "taskType", "run_id", "trial_id"):
        value = request.query.get(key)
        if value and key not in summary:
            summary[key] = value

    if body_bytes:
        summary["bytes"] = body_bytes
    return summary


def log_http(logger, request_id_: str, request, status: int, elapsed_ms: int, summary: Dict[str, Any]) -> None:
    fields = {
        "id": request_id_,
        "method": request.method,
        "path": request.path,
        "status": status,
        "duration_ms": elapsed_ms,
        "remote": remote_from_request(request),
        **summary,
    }
    logger.info("NET HTTP %s", format_fields(fields))


def log_ws_connect(
    logger,
    client_id: str,
    endpoint: str,
    remote: str,
    clients: Optional[int] = None,
) -> None:
    fields = {
        "event": "connect",
        "id": client_id,
        "endpoint": endpoint,
        "remote": remote,
    }
    if clients is not None:
        fields["clients"] = clients
    logger.info("NET WS %s", format_fields(fields))


def log_ws_disconnect(
    logger,
    client_id: str,
    endpoint: str,
    remote: str,
    elapsed_ms: Optional[int] = None,
    clients: Optional[int] = None,
    reason: Optional[str] = None,
) -> None:
    fields = {
        "event": "disconnect",
        "id": client_id,
        "endpoint": endpoint,
        "remote": remote,
    }
    if elapsed_ms is not None:
        fields["duration_ms"] = elapsed_ms
    if clients is not None:
        fields["clients"] = clients
    if reason:
        fields["reason"] = reason
    logger.info("NET WS %s", format_fields(fields))


def log_ws_message(
    logger,
    client_id: str,
    endpoint: str,
    message: Any,
    message_data: Any = None,
) -> None:
    if not should_log_ws_message(message_data):
        return

    if isinstance(message, str):
        message_bytes = len(message.encode("utf-8"))
    elif isinstance(message, bytes):
        message_bytes = len(message)
    else:
        message_bytes = 0

    fields = {
        "event": "recv",
        "id": client_id,
        "endpoint": endpoint,
        "bytes": message_bytes,
    }
    if isinstance(message_data, dict):
        summary = payload_summary(message_data)
        fields["type"] = summary.pop("type", summary.pop("TaskName", "unknown"))
        fields.update(summary)
    else:
        fields["type"] = "invalid_json"

    logger.info("NET WS %s", format_fields(fields))


def log_ws_send(
    logger,
    client_id: str,
    endpoint: str,
    message_data: Any,
    *,
    success: bool,
    error: Optional[str] = None,
) -> None:
    fields = {
        "event": "send" if success else "send_failed",
        "id": client_id,
        "endpoint": endpoint,
    }
    if isinstance(message_data, dict):
        summary = payload_summary(message_data)
        fields["type"] = summary.pop("type", "unknown")
        fields.update(summary)
    else:
        fields["type"] = "unknown"
    if error:
        fields["reason"] = error

    if success:
        logger.info("NET WS %s", format_fields(fields))
    else:
        logger.error("NET WS %s", format_fields(fields))
