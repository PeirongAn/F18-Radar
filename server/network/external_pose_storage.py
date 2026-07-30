from __future__ import annotations

import atexit
import json
import math
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from managers import db_manager, get_logger


SERVER_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = SERVER_DIR / "data" / "external_pose" / "raw"
SUPPORTED_TASK_TYPES = {"PLATFORM_CONTROL", "WEAPON_FIRING"}
SUPPORTED_SIDES = {"Our", "Enemy"}
MAX_RECENT_SNAPSHOT_IDS = 100_000


class ExternalPoseError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class PoseFileState:
    task_id: int
    task_group_id: Optional[int]
    user_id: str
    task_type: str
    path: Path
    file: Any
    row_count: int
    entity_record_count: int
    first_pose_time_ms: Optional[int]
    last_pose_time_ms: Optional[int]
    last_synced_row_count: int
    last_synced_at: float


def _safe_path_part(value: Any) -> str:
    safe = "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "_"
        for character in str(value)
    )
    return safe.strip("._") or "unknown"


def _storage_root(raw_path: Optional[str] = None) -> Path:
    raw = raw_path if raw_path is not None else os.environ.get("EXTERNAL_POSE_STORAGE_ROOT")
    if not raw or not str(raw).strip():
        return DEFAULT_ROOT
    path = Path(str(raw).strip())
    if path.is_absolute():
        return path
    parts = path.parts
    if parts and parts[0].lower() == "server":
        return SERVER_DIR.parent / path
    return SERVER_DIR / path


def _integer_timestamp(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ExternalPoseError("INVALID_TIMESTAMP", f"{field_name} must be a Unix millisecond integer")
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        raise ExternalPoseError("INVALID_TIMESTAMP", f"{field_name} must be a Unix millisecond integer")
    if timestamp <= 0:
        raise ExternalPoseError("INVALID_TIMESTAMP", f"{field_name} must be greater than zero")
    return timestamp


def _number(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ExternalPoseError("INVALID_POSE_DATA", f"{field_name} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ExternalPoseError("INVALID_POSE_DATA", f"{field_name} must be numeric")
    if not math.isfinite(number):
        raise ExternalPoseError("INVALID_POSE_DATA", f"{field_name} must be finite")
    return number


def _normalize_task_type(value: Any) -> str:
    task_type = str(value or "").strip().upper()
    if task_type == "WEAPON_LAUNCH":
        task_type = "WEAPON_FIRING"
    if task_type not in SUPPORTED_TASK_TYPES:
        raise ExternalPoseError(
            "UNSUPPORTED_TASK_TYPE",
            "task_type must be PLATFORM_CONTROL or WEAPON_FIRING",
        )
    return task_type


def _validate_message(message: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(message, dict):
        raise ExternalPoseError("INVALID_PAYLOAD", "message must be a JSON object")
    if message.get("type") not in {"external_pose_record", "external_pose_data"}:
        raise ExternalPoseError("INVALID_PAYLOAD", "unsupported external pose message type")

    schema_version = str(message.get("schema_version") or "").strip()
    snapshot_id = str(message.get("client_snapshot_id") or "").strip()
    data = message.get("data")
    if not schema_version:
        raise ExternalPoseError("INVALID_PAYLOAD", "schema_version is required")
    if not snapshot_id:
        raise ExternalPoseError("INVALID_PAYLOAD", "client_snapshot_id is required")
    if not isinstance(data, dict):
        raise ExternalPoseError("INVALID_PAYLOAD", "data must be a JSON object")

    user_id = str(data.get("PlayerID") or "").strip()
    if not user_id:
        raise ExternalPoseError("INVALID_PAYLOAD", "data.PlayerID is required")
    task_type = _normalize_task_type(data.get("task_type"))
    captured_at = _integer_timestamp(data.get("captured_at"), "data.captured_at")
    pose_data = data.get("pose_data")
    if not isinstance(pose_data, list) or not pose_data:
        raise ExternalPoseError("INVALID_POSE_DATA", "data.pose_data must be a non-empty array")

    normalized_poses = []
    for index, pose in enumerate(pose_data):
        if not isinstance(pose, dict):
            raise ExternalPoseError("INVALID_POSE_DATA", f"pose_data[{index}] must be an object")
        side = str(pose.get("Side") or "").strip()
        entity_id = str(pose.get("ID") or "").strip()
        if side not in SUPPORTED_SIDES:
            raise ExternalPoseError(
                "INVALID_POSE_DATA",
                f"pose_data[{index}].Side must be Our or Enemy",
            )
        if not entity_id:
            raise ExternalPoseError("INVALID_POSE_DATA", f"pose_data[{index}].ID is required")
        pose_time_ms = _integer_timestamp(
            pose.get("timestamp", captured_at),
            f"pose_data[{index}].timestamp",
        )
        posture = pose.get("posture")
        if not isinstance(posture, dict) or not posture:
            raise ExternalPoseError(
                "INVALID_POSE_DATA",
                f"pose_data[{index}].posture must be a non-empty object",
            )
        normalized_posture = {
            str(name): _number(value, f"pose_data[{index}].posture.{name}")
            for name, value in posture.items()
        }
        normalized_poses.append(
            {
                "Side": side,
                "ID": entity_id,
                "timestamp": pose_time_ms,
                "posture": normalized_posture,
            }
        )

    requested_task_id = data.get("task_id")
    if requested_task_id in ("", None):
        requested_task_id = None
    else:
        try:
            requested_task_id = int(requested_task_id)
        except (TypeError, ValueError):
            raise ExternalPoseError("INVALID_PAYLOAD", "data.task_id must be an integer or null")

    return {
        "schema_version": schema_version,
        "client_snapshot_id": snapshot_id,
        "user_id": user_id,
        "task_type": task_type,
        "requested_task_id": requested_task_id,
        "captured_at": captured_at,
        "pose_data": normalized_poses,
    }


class ExternalPoseFileStore:
    def __init__(
        self,
        database_manager=None,
        root_dir: Optional[str | os.PathLike[str]] = None,
        sync_every: int = 100,
        sync_interval_seconds: float = 1.0,
    ):
        self.db = database_manager or db_manager
        self.root_dir = _storage_root(str(root_dir) if root_dir is not None else None)
        self.sync_every = max(1, int(sync_every))
        self.sync_interval_seconds = max(0.0, float(sync_interval_seconds))
        self.logger = get_logger("external_pose")
        self.lock = threading.RLock()
        self.states: Dict[int, PoseFileState] = {}
        self.recent_snapshot_ids: OrderedDict[str, int] = OrderedDict()
        self.closed = False

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
                raise ExternalPoseError(
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
            raise ExternalPoseError(
                "ACTIVE_TASK_NOT_FOUND",
                "no active subtask matches PlayerID and task_type",
            )
        if len(runs) > 1:
            raise ExternalPoseError(
                "ACTIVE_TASK_AMBIGUOUS",
                "multiple active subtasks match PlayerID and task_type",
            )
        return runs[0]

    def _path_for(self, user_id: str, task_id: int) -> Path:
        return (
            self.root_dir
            / _safe_path_part(user_id)
            / _safe_path_part(task_id)
            / "pose_samples.jsonl"
        )

    def _remember_snapshot(self, snapshot_id: str, task_id: int) -> None:
        self.recent_snapshot_ids[snapshot_id] = task_id
        self.recent_snapshot_ids.move_to_end(snapshot_id)
        while len(self.recent_snapshot_ids) > MAX_RECENT_SNAPSHOT_IDS:
            self.recent_snapshot_ids.popitem(last=False)

    def _scan_existing_file(self, path: Path) -> Dict[str, Any]:
        result = {
            "row_count": 0,
            "entity_record_count": 0,
            "first_pose_time_ms": None,
            "last_pose_time_ms": None,
        }
        if not path.exists():
            return result
        with path.open("r", encoding="utf-8") as existing:
            for line in existing:
                try:
                    payload = json.loads(line)
                except (TypeError, ValueError):
                    continue
                result["row_count"] += 1
                poses = payload.get("pose_data")
                if isinstance(poses, list):
                    result["entity_record_count"] += len(poses)
                captured_at = payload.get("captured_at")
                if isinstance(captured_at, int):
                    first = result["first_pose_time_ms"]
                    last = result["last_pose_time_ms"]
                    result["first_pose_time_ms"] = captured_at if first is None else min(first, captured_at)
                    result["last_pose_time_ms"] = captured_at if last is None else max(last, captured_at)
                snapshot_id = str(payload.get("client_snapshot_id") or "").strip()
                task_id = payload.get("resolved_task_id")
                if snapshot_id and task_id is not None:
                    self._remember_snapshot(snapshot_id, int(task_id))
        return result

    def _open_state(
        self,
        run: Dict[str, Any],
        normalized: Dict[str, Any],
        received_at_ms: int,
    ) -> PoseFileState:
        task_id = int(run["task_id"])
        existing_state = self.states.get(task_id)
        if existing_state:
            return existing_state

        for other_task_id, other_state in list(self.states.items()):
            if (
                other_state.user_id == normalized["user_id"]
                and other_state.task_type == normalized["task_type"]
                and other_task_id != task_id
            ):
                self._close_state(other_state)
                self.states.pop(other_task_id, None)

        path = self._path_for(normalized["user_id"], task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        scanned = self._scan_existing_file(path)
        indexed = self.db.upsert_external_pose_file(
            task_id=task_id,
            task_group_id=run.get("group_id"),
            user_id=normalized["user_id"],
            task_type=normalized["task_type"],
            file_path=str(path.resolve()),
            schema_version=normalized["schema_version"],
            now_ms=received_at_ms,
        )
        row_count = max(scanned["row_count"], indexed["row_count"])
        entity_count = max(
            scanned["entity_record_count"],
            indexed["entity_record_count"],
        )
        first_pose_time_ms = scanned["first_pose_time_ms"] or indexed["first_pose_time_ms"]
        last_pose_time_ms = scanned["last_pose_time_ms"] or indexed["last_pose_time_ms"]
        state = PoseFileState(
            task_id=task_id,
            task_group_id=run.get("group_id"),
            user_id=normalized["user_id"],
            task_type=normalized["task_type"],
            path=path.resolve(),
            file=path.open("a", encoding="utf-8", newline="\n"),
            row_count=row_count,
            entity_record_count=entity_count,
            first_pose_time_ms=first_pose_time_ms,
            last_pose_time_ms=last_pose_time_ms,
            last_synced_row_count=int(indexed["row_count"]),
            last_synced_at=time.monotonic(),
        )
        self.states[task_id] = state
        self.logger.info(
            "external pose file ready task_id=%s task_group_id=%s user_id=%s task_type=%s path=%s",
            task_id,
            run.get("group_id"),
            normalized["user_id"],
            normalized["task_type"],
            state.path,
        )
        return state

    def _sync_state(self, state: PoseFileState, now_ms: int, status: str = "active") -> None:
        self.db.update_external_pose_file_progress(
            file_path=str(state.path),
            row_count=state.row_count,
            entity_record_count=state.entity_record_count,
            first_pose_time_ms=state.first_pose_time_ms,
            last_pose_time_ms=state.last_pose_time_ms,
            now_ms=now_ms,
            status=status,
        )
        state.last_synced_row_count = state.row_count
        state.last_synced_at = time.monotonic()

    def _close_state(self, state: PoseFileState) -> None:
        try:
            state.file.flush()
            self._sync_state(state, int(time.time() * 1000), status="closed")
        finally:
            state.file.close()

    def write(self, message: Dict[str, Any]) -> Dict[str, Any]:
        normalized = _validate_message(message)
        received_at_ms = int(time.time() * 1000)
        with self.lock:
            if self.closed:
                raise RuntimeError("external pose store is closed")
            run = self._resolve_task(normalized)
            task_id = int(run["task_id"])
            snapshot_id = normalized["client_snapshot_id"]
            state = self._open_state(run, normalized, received_at_ms)
            duplicate_task_id = self.recent_snapshot_ids.get(snapshot_id)
            if duplicate_task_id is not None:
                if duplicate_task_id != task_id:
                    raise ExternalPoseError(
                        "TASK_ID_MISMATCH",
                        "client_snapshot_id was already used for another task",
                )
                return self._success_reply(normalized, run, duplicate=True)

            record = {
                "schema_version": normalized["schema_version"],
                "client_snapshot_id": snapshot_id,
                "received_at_ms": received_at_ms,
                "resolved_task_id": task_id,
                "task_group_id": run.get("group_id"),
                "user_id": normalized["user_id"],
                "task_type": normalized["task_type"],
                "captured_at": normalized["captured_at"],
                "pose_data": normalized["pose_data"],
            }
            state.file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            state.file.flush()
            state.row_count += 1
            state.entity_record_count += len(normalized["pose_data"])
            state.first_pose_time_ms = (
                normalized["captured_at"]
                if state.first_pose_time_ms is None
                else min(state.first_pose_time_ms, normalized["captured_at"])
            )
            state.last_pose_time_ms = (
                normalized["captured_at"]
                if state.last_pose_time_ms is None
                else max(state.last_pose_time_ms, normalized["captured_at"])
            )
            self._remember_snapshot(snapshot_id, task_id)

            needs_sync = (
                state.row_count == 1
                or state.row_count - state.last_synced_row_count >= self.sync_every
                or time.monotonic() - state.last_synced_at >= self.sync_interval_seconds
            )
            if needs_sync:
                self._sync_state(state, received_at_ms)
            return self._success_reply(normalized, run, duplicate=False)

    @staticmethod
    def _success_reply(
        normalized: Dict[str, Any],
        run: Dict[str, Any],
        *,
        duplicate: bool,
    ) -> Dict[str, Any]:
        return {
            "type": "external_pose_record_result",
            "ok": True,
            "client_snapshot_id": normalized["client_snapshot_id"],
            "pose_snapshot_id": normalized["client_snapshot_id"],
            "resolved_task_id": int(run["task_id"]),
            "task_id": int(run["task_id"]),
            "task_group_id": run.get("group_id"),
            "task_type": normalized["task_type"],
            "pose_record_count": len(normalized["pose_data"]),
            "duplicate": duplicate,
            "server_time_us": int(time.time() * 1_000_000),
        }

    def close(self) -> None:
        with self.lock:
            if self.closed:
                return
            self.closed = True
            for state in list(self.states.values()):
                self._close_state(state)
            self.states.clear()


_store_lock = threading.Lock()
_store: Optional[ExternalPoseFileStore] = None


def get_external_pose_store() -> ExternalPoseFileStore:
    global _store
    with _store_lock:
        if _store is None or _store.closed:
            _store = ExternalPoseFileStore()
        return _store


def handle_external_pose_record(message: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return get_external_pose_store().write(message)
    except ExternalPoseError as exc:
        return {
            "type": "external_pose_record_result",
            "ok": False,
            "client_snapshot_id": str(message.get("client_snapshot_id") or ""),
            "error": {"code": exc.code, "message": str(exc)},
            "server_time_us": int(time.time() * 1_000_000),
        }
    except Exception as exc:
        get_logger("external_pose").error(
            "external pose write failed: %s",
            exc,
            exc_info=True,
        )
        return {
            "type": "external_pose_record_result",
            "ok": False,
            "client_snapshot_id": str(message.get("client_snapshot_id") or ""),
            "error": {"code": "INTERNAL_ERROR", "message": str(exc)},
            "server_time_us": int(time.time() * 1_000_000),
        }


def _close_global_store() -> None:
    if _store is not None:
        _store.close()


atexit.register(_close_global_store)
