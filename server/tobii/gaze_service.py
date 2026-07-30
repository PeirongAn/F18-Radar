"""
GazeService — 眼动追踪核心服务

封装 Tobii 眼动仪的设备管理、注视点采集、任务生命周期和文件写入，
供 HTTP、WebSocket 等上层服务统一调用。

典型用法:
    service = GazeService(data_dir="/path/to/gaze_data")
    service.connect()                 # 连接眼动仪

    # 在 WebSocket/HTTP 处理里调用
    task_id = service.start_task(bbox, screen_size, task_id="外部传入的ID", user_id=...)
    service.stop_task(task_id)

    # 给 WebSocket 广播注册事件循环和客户端
    service.set_ws_event_loop(loop)
    service.register_ws_client(ws)
    service.unregister_ws_client(ws)

    # 读取最新注视点（供 HTTP GET 或其他服务轮询）
    point, ts = service.get_latest_gaze_point()

文件存储结构（每个任务独立目录）:
    {data_dir}/raw/{user_id}/{task_id}/
        raw_gaze.jsonl      # 每帧一行：{"ts_us":…,"gaze":[x,y],"hit":false}

任务元数据、markers、targets、feedback 和统计统一写入 gaze_records.db。
"""

import math
import time
import uuid
import json
import hashlib
import sqlite3
import queue
import asyncio
import os
import threading
import logging
from collections import deque


# 连续未注视帧数阈值，超过后推送注意力反馈
def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


OUT_OF_BOX_FALSE_THRESHOLD = _env_int("GAZE_OUT_OF_BOX_FALSE_THRESHOLD", 200)
ATTENTION_FEEDBACK_COOLDOWN_MS = _env_int("GAZE_ATTENTION_FEEDBACK_COOLDOWN_MS", 3000)
GAZE_SCREEN_WIDTH = _env_int("GAZE_SCREEN_WIDTH", 0)
GAZE_SCREEN_HEIGHT = _env_int("GAZE_SCREEN_HEIGHT", 0)
GAZE_PROGRESS_LOGS_ENABLED = os.environ.get("GAZE_PROGRESS_LOGS", "").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

ANALYSIS_AOI_IDS = {
    "left_ai_target",
    "left_candidate_list",
    "right_ai_history_accuracy",
    "right_recommendation",
    "right_candidate_list",
    "right_detail",
    "right_comparison",
    "TrustHistory",
    "TrustStatePanel",
    "SHOOT",
    "Title",
    "AIConfidence",
    "HistoricalResultRecord",
    "AIFlightTrajectory",
}

# 写入队列中的事件类型标识
_EVT_GAZE_FRAME = "gaze_frame"
_EVT_CLOSE_TASK = "close_task"
_EVT_STOP_WRITER = "stop_writer"
_EVT_DB_EXEC = "db_exec"


class GazeService:
    """眼动追踪服务，封装 Tobii 设备与所有业务逻辑。"""

    def __init__(self, data_dir: str = None, gaze_window_size: int = 600):
        self._logger = logging.getLogger("radar_system.gaze_service")
        self._progress_logs_enabled = GAZE_PROGRESS_LOGS_ENABLED

        # 文件存储根目录，默认放在本文件旁边的 ../../data/gaze
        if data_dir is None:
            _here = os.path.dirname(os.path.abspath(__file__))
            data_dir = os.path.join(_here, "..", "..", "server", "data", "gaze")
        self._data_dir = os.path.abspath(data_dir)
        self._db_path = os.path.join(self._data_dir, "gaze_records.db")

        # ── 设备 ──────────────────────────────
        self._eyetracker = None

        # ── 注视点滑动窗口 ────────────────────
        self._gaze_window: deque = deque(maxlen=gaze_window_size)
        self._window_lock = threading.Lock()

        # ── 任务状态 ──────────────────────────
        self._task_active: bool = False
        self._current_task: dict | None = None
        self._state_lock = threading.Lock()

        # ── 最新注视点（可视化 / 轮询用）──────
        self._latest_gaze_point: list | None = None
        self._latest_gaze_time: float | None = None
        self._gaze_point_lock = threading.Lock()

        # ── 注意力反馈状态 ────────────────────
        self._consecutive_out_of_box_false: int = 0
        self._last_attention_feedback_time_ms: int = 0
        self._last_out_of_box_log_count: int = 0

        # ── WebSocket 广播 ────────────────────
        self._connected_clients: set = set()
        self._clients_lock = threading.Lock()
        self._ws_event_loop: asyncio.AbstractEventLoop | None = None

        # ── 后台文件写入队列 ──────────────────
        self._writer_queue: queue.Queue = queue.Queue()
        self._shutdown_lock = threading.Lock()
        self._shutdown_requested = False
        self._writer_thread = threading.Thread(
            target=self._run_writer, daemon=True, name="GazeFileWriter"
        )
        self._writer_thread.start()
        configured_screen = (
            (GAZE_SCREEN_WIDTH, GAZE_SCREEN_HEIGHT)
            if GAZE_SCREEN_WIDTH > 0 and GAZE_SCREEN_HEIGHT > 0
            else "client_fallback"
        )
        self._log_info(
            "配置已加载: "
            f"out_of_box_threshold={OUT_OF_BOX_FALSE_THRESHOLD}, "
            f"progress_logs={self._progress_logs_enabled}, "
            f"screen_size={configured_screen}"
        )

    def _log_info(self, message: str):
        formatted = f"[GazeService] {message}"
        if self._logger.hasHandlers():
            self._logger.info(message)
        else:
            print(formatted)

    # ═══════════════════════════════════════════
    # 设备管理
    # ═══════════════════════════════════════════

    def connect(self) -> str:
        """
        连接第一个可用的 Tobii 眼动仪并开始订阅注视数据。

        Returns:
            连接设备的名称字符串。

        Raises:
            RuntimeError: 找不到眼动仪。
            ImportError:  未安装 tobii_research。
        """
        try:
            import tobii_research as tr
        except ImportError as exc:
            raise ImportError(
                "请先安装 tobii_research: pip install tobii_research"
            ) from exc

        trackers = tr.find_all_eyetrackers()
        if not trackers:
            raise RuntimeError("未找到 Tobii 眼动仪，请检查设备连接")

        self._eyetracker = trackers[0]
        self._eyetracker.subscribe_to(
            tr.EYETRACKER_GAZE_DATA,
            self._gaze_data_callback,
            as_dictionary=True,
        )
        print(f"[GazeService] 已连接: {self._eyetracker.device_name}")
        return self._eyetracker.device_name

    def disconnect(self):
        """取消订阅并断开设备。"""
        if self._eyetracker is None:
            return
        try:
            import tobii_research as tr
            self._eyetracker.unsubscribe_from(
                tr.EYETRACKER_GAZE_DATA, self._gaze_data_callback
            )
        except Exception as e:
            print(f"[GazeService] 断开时出错: {e}")
        finally:
            self._eyetracker = None

    # ═══════════════════════════════════════════
    # 注视点查询（供外部服务调用）
    # ═══════════════════════════════════════════

    def get_latest_gaze_point(
        self, max_age_ms: float = 1000
    ) -> tuple[list | None, float | None]:
        """
        返回最新注视点坐标和时间戳。

        Args:
            max_age_ms: 数据有效期（毫秒），超过则视为过期。

        Returns:
            (gaze_point, timestamp_ms)，数据不存在或过期时均返回 (None, None)。
        """
        with self._gaze_point_lock:
            if self._latest_gaze_point is None or self._latest_gaze_time is None:
                return None, None
            age = time.time() * 1000 - self._latest_gaze_time
            if age > max_age_ms:
                return None, None
            return list(self._latest_gaze_point), self._latest_gaze_time

    def get_gaze_window_snapshot(self) -> list:
        """返回当前注视窗口的快照列表（副本）。"""
        with self._window_lock:
            return list(self._gaze_window)

    # ═══════════════════════════════════════════
    # 任务管理（供 HTTP / WebSocket 处理层调用）
    # ═══════════════════════════════════════════

    def start_task(
        self,
        bbox: list,
        screen_size: tuple | list | None,
        task_id: str | int | None = None,
        user_id: str = "",
        task_source: str = "",
        task_name: str = "",
        system_time: int | None = None,
        regions: list | None = None,
        coordinate_space: str | None = None,
        start_trigger: str = "task_start",
    ) -> str:
        """
        记录目标窗口出现、开始新任务，并创建对应的文件存储目录。

        Args:
            bbox:        原始像素坐标列表 [[x1,y1,x2,y2], ...]。
            screen_size: (width, height) 屏幕分辨率，用于归一化。
            task_id:     外部传入的任务 ID（主服务器 task_id）；为 None 时自动生成 UUID。
            user_id:     操作员 ID。
            task_source: 任务来源标识。
            task_name:   任务名称。
            system_time: 微秒级系统时间戳，默认使用当前时间。

        Returns:
            实际使用的 task_id 字符串。
        """
        if system_time is None:
            system_time = int(time.time() * 1_000_000)

        screen_w, screen_h = self._resolve_screen_size(screen_size)
        normalized_regions = _normalize_regions(
            regions=regions,
            bbox=bbox,
            coordinate_space=coordinate_space,
            screen_width=screen_w or 1,
            screen_height=screen_h or 1,
        )

        # 优先使用外部传入的 task_id，回退到生成 UUID
        resolved_task_id = str(task_id) if task_id is not None else str(uuid.uuid4())

        active_task_id = None
        with self._state_lock:
            if self._task_active and self._current_task:
                active_task_id = str(self._current_task.get("task_id"))
        if active_task_id == resolved_task_id:
            # Reconnects and duplicate task-start messages belong to the same
            # concrete trial.  Preserve AOI revision/state instead of resetting
            # the active gaze task and reusing revision 1.
            with self._state_lock:
                if self._current_task and normalized_regions:
                    self._current_task["bbox"] = normalized_regions
                    self._current_task["regions"] = normalized_regions
                if self._current_task:
                    self._current_task["user_id"] = user_id or self._current_task.get("user_id", "")
                    self._current_task["task_source"] = task_source or self._current_task.get("task_source", "")
                    self._current_task["task_name"] = task_name or self._current_task.get("task_name", "")
            self._log_info(
                f"duplicate gaze task start ignored; task_id={resolved_task_id}"
            )
            return resolved_task_id

        if active_task_id and active_task_id != resolved_task_id:
            self._log_info(
                "starting a new gaze task while another task is active; "
                f"auto-closing active={active_task_id}, new={resolved_task_id}"
            )
            self.stop_task(
                task_id=active_task_id,
                system_time=system_time,
                end_trigger="auto_closed_by_new_task",
            )

        # 创建任务目录
        task_dir = self._build_task_dir(user_id=user_id, task_id=resolved_task_id, system_time=system_time)
        os.makedirs(task_dir, exist_ok=True)

        with self._state_lock:
            self._current_task = {
                "task_id": resolved_task_id,
                "task_dir": task_dir,
                "bbox": normalized_regions,
                "regions": normalized_regions,
                "analysis_aoi_regions": [],
                "analysis_aoi_revision": None,
                "analysis_aoi_snapshot_id": None,
                "analysis_aoi_layout_signature": None,
                "analysis_aoi_alignment_valid": False,
                "start_system_time": system_time,
                "user_id": user_id or "",
                "task_source": task_source or "",
                "task_name": task_name or "",
                "start_trigger": start_trigger or "task_start",
                "frame_count": 0,
                "valid_frames": 0,
                "in_region_frames": 0,
                "feedback_count": 0,
            }
            self._task_active = True
            self._reset_out_of_box_state()

        # 记录任务开始到 gaze_records.db
        self._enqueue_db(
            "INSERT OR REPLACE INTO gaze_tasks "
            "(task_id, user_id, task_source, task_name, data_dir, start_time_us, start_trigger, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'active')",
            (
                resolved_task_id,
                user_id or "",
                task_source or "",
                task_name or "",
                task_dir,
                system_time,
                start_trigger or "task_start",
            ),
        )
        if normalized_regions:
            self._enqueue_db(
                "INSERT INTO gaze_targets "
                "(task_id, bbox_json, normalized_bbox_json, screen_width, screen_height, appear_time_us) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (resolved_task_id, None, json.dumps(normalized_regions, ensure_ascii=False),
                 int(screen_w), int(screen_h), system_time),
            )

        print(f"[GazeService] 任务开始: task_id={resolved_task_id}, dir={task_dir}")
        return resolved_task_id

    def stop_task(
        self,
        task_id: str | None = None,
        user_id: str = "",
        task_source: str = "",
        task_name: str = "",
        system_time: int | None = None,
        end_trigger: str = "task_end",
    ) -> dict:
        """
        记录目标窗口消失、结束当前任务，并把生命周期和统计写入 SQLite。

        Args:
            task_id:     要结束的任务 ID，为 None 时自动取当前活动任务。
            user_id, task_source, task_name: 可覆盖任务创建时的值。
            system_time: 微秒级系统时间戳，默认使用当前时间。

        Returns:
            包含 task_id、task_info 等字段的 dict。

        Raises:
            ValueError: 无法确定 task_id。
        """
        if system_time is None:
            system_time = int(time.time() * 1_000_000)

        requested_task_id = str(task_id) if task_id is not None else None
        resolved_task_id = requested_task_id or self._get_active_task_id()
        if not resolved_task_id:
            raise ValueError("窗口消失时必须提供 task_id 或存在活动任务")

        with self._state_lock:
            if not self._task_active or self._current_task is None:
                raise ValueError(f"no active gaze task to stop: task_id={resolved_task_id}")
            active_task_id = str(self._current_task.get("task_id"))
            if requested_task_id is not None and requested_task_id != active_task_id:
                raise ValueError(
                    f"stop task_id mismatch: request={requested_task_id}, active={active_task_id}"
                )
            resolved_task_id = active_task_id
            self._task_active = False
            self._reset_out_of_box_state()

            task_info = self._current_task
            begin_time = (
                self._current_task["start_system_time"]
                if self._current_task
                else system_time
            )
            task_dir = self._current_task.get("task_dir") if self._current_task else None
            frame_count = self._current_task.get("frame_count", 0) if self._current_task else 0
            valid_frames = self._current_task.get("valid_frames", 0) if self._current_task else 0
            in_region_frames = self._current_task.get("in_region_frames", 0) if self._current_task else 0
            self._current_task = None

        # 自动关闭该任务下所有未关闭的目标事件
        self._enqueue_db(
            "UPDATE gaze_targets SET disappear_time_us = ?, auto_closed = 1 "
            "WHERE task_id = ? AND disappear_time_us IS NULL",
            (system_time, resolved_task_id),
        )
        self._enqueue_db(
            "UPDATE gaze_aoi_snapshots SET valid_to_us = ? "
            "WHERE task_id = ? AND valid_to_us IS NULL",
            (system_time, resolved_task_id),
        )
        # 更新任务记录为已完成
        self._enqueue_db(
            "UPDATE gaze_tasks SET end_time_us = ?, duration_ms = ?, "
            "total_frames = ?, valid_frames = ?, in_region_frames = ?, end_trigger = ?, status = 'completed' "
            "WHERE task_id = ?",
            (system_time, (system_time - begin_time) / 1000,
             frame_count, valid_frames, in_region_frames, end_trigger or "task_end", resolved_task_id),
        )

        # 任务结束后只关闭 raw_gaze 句柄；任务摘要由 gaze_tasks 查询还原。
        if task_dir:
            self._writer_queue.put({
                "evt": _EVT_CLOSE_TASK,
                "task_dir": task_dir,
            })

        print(f"[GazeService] 任务结束: task_id={resolved_task_id}")
        return {
            "task_id": resolved_task_id,
            "task_info": task_info,
        }

    def get_active_task_id(self) -> str | None:
        """公开接口：获取当前活动任务 ID。"""
        return self._get_active_task_id()

    def get_screen_size(self) -> tuple[int, int] | None:
        """返回 server 端配置的 gaze 屏幕尺寸；未配置时返回 None。"""
        if GAZE_SCREEN_WIDTH > 0 and GAZE_SCREEN_HEIGHT > 0:
            return (GAZE_SCREEN_WIDTH, GAZE_SCREEN_HEIGHT)
        return None

    def set_task_bbox(
        self,
        bbox: list,
        screen_size: tuple | list | None,
        task_id: str | None = None,
        regions: list | None = None,
        coordinate_space: str | None = None,
    ) -> bool:
        """
        更新当前活动任务的注意力区域（bbox）。

        通常由前端在目标窗口出现时调用（`/tobii/hand` box_visible=True），
        此时 task_id 已由主服务器在 task_start 时确定，无需重新创建任务。

        Args:
            bbox:        原始像素坐标列表 [[x1,y1,x2,y2], ...]。
            screen_size: (width, height) 屏幕分辨率，用于归一化。
            task_id:     要更新的任务 ID；为 None 时更新当前活动任务。

        Returns:
            True 表示更新成功，False 表示没有匹配的活动任务。
        """
        screen_w, screen_h = self._resolve_screen_size(screen_size)
        normalized_regions = _normalize_regions(
            regions=regions,
            bbox=bbox,
            coordinate_space=coordinate_space,
            screen_width=screen_w or 1,
            screen_height=screen_h or 1,
        )
        bbox_count = len(bbox) if isinstance(bbox, list) else 0
        region_count = len(regions) if isinstance(regions, list) else 0
        self._log_info(
            "收到bbox更新请求: "
            f"task_id={task_id}, bbox_count={bbox_count}, region_count={region_count}, "
            f"coordinate_space={coordinate_space or 'auto'}, screen_size=({screen_w}, {screen_h})"
        )

        with self._state_lock:
            if not self._task_active or self._current_task is None:
                self._log_info("bbox更新被忽略: 当前没有活动眼动任务")
                return False
            if task_id is not None and self._current_task.get("task_id") != str(task_id):
                self._log_info(
                    "bbox更新被忽略: task_id不匹配, "
                    f"request={task_id}, active={self._current_task.get('task_id')}"
                )
                return False
            active_task_id = self._current_task["task_id"]
            self._current_task["bbox"] = normalized_regions
            self._current_task["regions"] = normalized_regions
            self._reset_out_of_box_state()
            self._log_info(
                "bbox已写入活动任务: "
                f"task_id={active_task_id}, normalized_regions={normalized_regions}"
            )

        now_us = int(time.time() * 1_000_000)

        # 先关闭该任务下所有未关闭的目标（disappear_time_us IS NULL）
        self._enqueue_db(
            "UPDATE gaze_targets SET disappear_time_us = ? "
            "WHERE task_id = ? AND disappear_time_us IS NULL",
            (now_us, active_task_id),
        )
        # 若新 bbox 非空，记录归一化目标出现；原始 bbox 不再作为分析主数据保存。
        if normalized_regions:
            self._enqueue_db(
                "INSERT INTO gaze_targets "
                "(task_id, bbox_json, normalized_bbox_json, "
                "screen_width, screen_height, appear_time_us) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (active_task_id, None, json.dumps(normalized_regions, ensure_ascii=False),
                 int(screen_w), int(screen_h), now_us),
            )

        self._log_info(f"bbox数据库记录已更新: task_id={active_task_id}")
        return True

    # ═══════════════════════════════════════════
    # 眼动数据库辅助方法
    # ═══════════════════════════════════════════

    def set_analysis_aoi_snapshot(
        self,
        *,
        task_id: str | None,
        trial_id: str | None,
        task_group_id: str | None,
        task_type: str,
        client_snapshot_id: str | None,
        client_captured_at_ms: int | None,
        change_reasons: list | None,
        coordinate_space: str | None,
        display: dict | None,
        regions: list | None,
    ) -> dict:
        """Install versioned analysis AOIs without changing attention feedback."""
        display_data = display if isinstance(display, dict) else {}
        normalized_regions = _normalize_analysis_aoi_regions(
            regions=regions,
            coordinate_space=coordinate_space,
            screen_width=_as_float(display_data.get("screen_width_physical_px"))
            or _as_float(display_data.get("screen_width_css_px"))
            or 1,
            screen_height=_as_float(display_data.get("screen_height_physical_px"))
            or _as_float(display_data.get("screen_height_css_px"))
            or 1,
        )
        alignment_valid = bool(display_data.get("alignment_valid"))
        canonical_payload = {
            "coordinate_space": "display_area_normalized",
            "display": display_data,
            "regions": normalized_regions,
        }
        layout_signature = hashlib.sha256(
            json.dumps(
                canonical_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        now_us = int(time.time() * 1_000_000)

        with self._state_lock:
            if not self._task_active or self._current_task is None:
                return {"ok": False, "msg": "no active gaze task"}
            active_task_id = str(self._current_task.get("task_id"))
            if task_id is not None and str(task_id) != active_task_id:
                return {
                    "ok": False,
                    "msg": "task_id mismatch",
                    "task_id": active_task_id,
                }
            if self._current_task.get("analysis_aoi_layout_signature") == layout_signature:
                return {
                    "ok": True,
                    "changed": False,
                    "task_id": active_task_id,
                    "snapshot_id": self._current_task.get("analysis_aoi_snapshot_id"),
                    "revision": self._current_task.get("analysis_aoi_revision"),
                    "layout_signature": layout_signature,
                }

            revision = int(self._current_task.get("analysis_aoi_revision") or 0) + 1
            snapshot_id = str(uuid.uuid4())
            self._current_task["analysis_aoi_regions"] = [
                region for region in normalized_regions if region.get("visible") is True
            ]
            self._current_task["analysis_aoi_revision"] = revision
            self._current_task["analysis_aoi_snapshot_id"] = snapshot_id
            self._current_task["analysis_aoi_layout_signature"] = layout_signature
            self._current_task["analysis_aoi_alignment_valid"] = alignment_valid

        self._enqueue_db(
            "UPDATE gaze_aoi_snapshots SET valid_to_us = ? "
            "WHERE task_id = ? AND valid_to_us IS NULL",
            (now_us, active_task_id),
        )
        self._enqueue_db(
            "INSERT INTO gaze_aoi_snapshots "
            "(snapshot_id, task_id, trial_id, task_group_id, task_type, revision, "
            "valid_from_us, change_reasons_json, layout_signature, coordinate_space, "
            "display_json, regions_json, alignment_valid, client_captured_at_ms, client_snapshot_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot_id,
                active_task_id,
                str(trial_id) if trial_id is not None else active_task_id,
                str(task_group_id) if task_group_id is not None else None,
                str(task_type or ""),
                revision,
                now_us,
                json.dumps(change_reasons or [], ensure_ascii=False),
                layout_signature,
                "display_area_normalized",
                json.dumps(display_data, ensure_ascii=False, sort_keys=True),
                json.dumps(normalized_regions, ensure_ascii=False, sort_keys=True),
                1 if alignment_valid else 0,
                int(client_captured_at_ms) if client_captured_at_ms is not None else None,
                str(client_snapshot_id) if client_snapshot_id else None,
            ),
        )
        return {
            "ok": True,
            "changed": True,
            "task_id": active_task_id,
            "snapshot_id": snapshot_id,
            "revision": revision,
            "layout_signature": layout_signature,
        }

    def record_marker(
        self,
        name: str,
        payload: dict | None = None,
        task_id: str | int | None = None,
        user_id: str = "",
        system_time: int | None = None,
    ) -> dict:
        """Record a manual gaze marker in SQLite."""
        marker_name = str(name or "").strip()
        if not marker_name:
            raise ValueError("marker name is required")
        if system_time is None:
            system_time = int(time.time() * 1_000_000)

        requested_task_id = str(task_id) if task_id is not None else None
        marker_id = uuid.uuid4().hex
        payload_obj = _sanitize_marker_payload(payload if isinstance(payload, dict) else {})
        resolved_task_id = requested_task_id
        resolved_user_id = user_id or ""

        with self._state_lock:
            active_task = self._current_task if self._task_active else None
            if active_task:
                active_task_id = str(active_task.get("task_id"))
                if requested_task_id is not None and requested_task_id != active_task_id:
                    raise ValueError(
                        f"marker task_id mismatch: request={requested_task_id}, active={active_task_id}"
                    )
                resolved_task_id = active_task_id
                resolved_user_id = resolved_user_id or active_task.get("user_id", "")

        record = {
            "marker_id": marker_id,
            "task_id": resolved_task_id,
            "user_id": resolved_user_id,
            "name": marker_name,
            "event_time_us": int(system_time),
            "payload": payload_obj,
        }
        self._enqueue_db(
            "INSERT INTO gaze_markers "
            "(marker_id, task_id, user_id, name, event_time_us, payload_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                marker_id,
                resolved_task_id or "",
                resolved_user_id or "",
                marker_name,
                int(system_time),
                json.dumps(payload_obj, ensure_ascii=False),
            ),
        )
        self._log_info(
            f"marker recorded: marker_id={marker_id}, task_id={resolved_task_id or ''}, name={marker_name}"
        )
        return record

    def _enqueue_db(self, sql: str, params: tuple = ()):
        """向后台写入线程发送 DB 写操作（线程安全）。"""
        self._writer_queue.put({"evt": _EVT_DB_EXEC, "sql": sql, "params": params})

    @staticmethod
    def _init_gaze_db(conn: sqlite3.Connection):
        """在 gaze_records.db 上创建所需表（幂等）。"""
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS gaze_tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id     TEXT    NOT NULL UNIQUE,
                user_id     TEXT    DEFAULT '',
                task_source TEXT    DEFAULT '',
                task_name   TEXT    DEFAULT '',
                data_dir    TEXT,
                start_time_us INTEGER NOT NULL,
                end_time_us   INTEGER,
                start_trigger TEXT DEFAULT '',
                end_trigger TEXT DEFAULT '',
                duration_ms   REAL,
                total_frames    INTEGER DEFAULT 0,
                valid_frames    INTEGER DEFAULT 0,
                in_region_frames INTEGER DEFAULT 0,
                status      TEXT    DEFAULT 'active',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS gaze_targets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id     TEXT    NOT NULL,
                bbox_json   TEXT,
                normalized_bbox_json TEXT,
                screen_width  INTEGER,
                screen_height INTEGER,
                appear_time_us    INTEGER NOT NULL,
                disappear_time_us INTEGER,
                auto_closed INTEGER DEFAULT 0,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES gaze_tasks(task_id)
            );

            CREATE TABLE IF NOT EXISTS gaze_aoi_snapshots (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT    NOT NULL UNIQUE,
                task_id     TEXT    NOT NULL,
                trial_id    TEXT,
                task_group_id TEXT,
                task_type   TEXT    DEFAULT '',
                revision    INTEGER NOT NULL,
                valid_from_us INTEGER NOT NULL,
                valid_to_us INTEGER,
                change_reasons_json TEXT,
                layout_signature TEXT NOT NULL,
                coordinate_space TEXT DEFAULT 'display_area_normalized',
                display_json TEXT,
                regions_json TEXT,
                alignment_valid INTEGER DEFAULT 0,
                client_captured_at_ms INTEGER,
                client_snapshot_id TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(task_id, revision),
                FOREIGN KEY (task_id) REFERENCES gaze_tasks(task_id)
            );

            CREATE INDEX IF NOT EXISTS idx_gaze_aoi_snapshots_task_time
            ON gaze_aoi_snapshots(task_id, valid_from_us);

            CREATE TABLE IF NOT EXISTS gaze_feedback_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id     TEXT    NOT NULL,
                event_time_ms INTEGER NOT NULL,
                reason      TEXT    DEFAULT '',
                consecutive_false_count INTEGER DEFAULT 0,
                threshold   INTEGER DEFAULT 0,
                payload_json TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES gaze_tasks(task_id)
            );

            CREATE TABLE IF NOT EXISTS gaze_markers (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                marker_id   TEXT    NOT NULL UNIQUE,
                task_id     TEXT    DEFAULT '',
                user_id     TEXT    DEFAULT '',
                name        TEXT    NOT NULL,
                event_time_us INTEGER NOT NULL,
                payload_json TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        _ensure_column(conn, "gaze_tasks", "task_source", "TEXT DEFAULT ''")
        _ensure_column(conn, "gaze_tasks", "start_trigger", "TEXT DEFAULT ''")
        _ensure_column(conn, "gaze_tasks", "end_trigger", "TEXT DEFAULT ''")
        _ensure_column(conn, "gaze_tasks", "valid_frames", "INTEGER DEFAULT 0")
        _ensure_column(conn, "gaze_tasks", "in_region_frames", "INTEGER DEFAULT 0")

    # ═══════════════════════════════════════════
    # WebSocket 客户端管理
    # ═══════════════════════════════════════════

    def set_ws_event_loop(self, loop: asyncio.AbstractEventLoop):
        """设置 asyncio 事件循环，用于从 gaze 回调线程触发广播。"""
        self._ws_event_loop = loop
        self._log_info("WS事件循环已设置，注意力反馈可异步广播")

    def register_ws_client(self, websocket):
        """注册一个新的 WebSocket 连接。"""
        with self._clients_lock:
            self._connected_clients.add(websocket)
            client_count = len(self._connected_clients)
        self._log_info(f"WS客户端已注册，当前客户端数={client_count}")

    def unregister_ws_client(self, websocket):
        """注销一个 WebSocket 连接。"""
        with self._clients_lock:
            self._connected_clients.discard(websocket)
            client_count = len(self._connected_clients)
        self._log_info(f"WS客户端已注销，当前客户端数={client_count}")

    async def broadcast(self, message_obj: dict):
        """向所有已注册客户端广播 JSON 消息（异步）。"""
        message = json.dumps(message_obj, ensure_ascii=False)
        with self._clients_lock:
            clients = list(self._connected_clients)

        stale = []
        for client in clients:
            try:
                if hasattr(client, "send_str"):
                    await client.send_str(message)
                else:
                    await client.send(message)
            except Exception:
                stale.append(client)

        if stale:
            with self._clients_lock:
                for c in stale:
                    self._connected_clients.discard(c)
            self._log_info(f"广播时移除了失效WS客户端: stale_count={len(stale)}")

    # ═══════════════════════════════════════════
    # 内部实现
    # ═══════════════════════════════════════════

    def _reset_out_of_box_state(self):
        self._consecutive_out_of_box_false = 0
        self._last_attention_feedback_time_ms = 0
        self._last_out_of_box_log_count = 0

    def _resolve_screen_size(self, screen_size: tuple | list | None) -> tuple:
        if GAZE_SCREEN_WIDTH > 0 and GAZE_SCREEN_HEIGHT > 0:
            return (GAZE_SCREEN_WIDTH, GAZE_SCREEN_HEIGHT)

        if isinstance(screen_size, (list, tuple)) and len(screen_size) >= 2:
            return (screen_size[0] or 1, screen_size[1] or 1)
        return (1, 1)

    def _build_task_dir(self, user_id: str, task_id: str, system_time: int) -> str:
        safe_user_id = _safe_path_segment(user_id, default="unknown_user")
        safe_task_id = _safe_path_segment(task_id, default=str(uuid.uuid4()))
        task_dir = os.path.abspath(
            os.path.join(self._data_dir, "raw", safe_user_id, safe_task_id)
        )
        data_root = os.path.abspath(self._data_dir)
        if os.path.commonpath([data_root, task_dir]) != data_root:
            raise ValueError(f"invalid gaze task data path: {task_dir}")
        return task_dir

    def _get_active_task_id(self) -> str | None:
        if self._current_task and isinstance(self._current_task, dict):
            return self._current_task.get("task_id")
        return None

    def _gaze_data_callback(self, gaze_data: dict):
        """Tobii 实时数据回调——每帧调用一次。"""
        system_time_stamp = int(time.time() * 1_000_000)
        gaze_point, gaze_valid = _get_gaze_point(gaze_data)

        frame_record = {
            "system_time_stamp": system_time_stamp,
            "gaze_point": gaze_point,
            "valid": gaze_valid,
        }

        with self._window_lock:
            self._gaze_window.append(frame_record)

        with self._gaze_point_lock:
            self._latest_gaze_point = list(gaze_point) if gaze_valid else None
            self._latest_gaze_time = time.time() * 1000 if gaze_valid else None

        with self._state_lock:
            if not self._task_active or self._current_task is None:
                return
            task = dict(self._current_task)
            task["frame_count"] = task.get("frame_count", 0) + 1
            self._current_task["frame_count"] = task["frame_count"]
            if gaze_valid:
                self._current_task["valid_frames"] = self._current_task.get("valid_frames", 0) + 1

        regions = task.get("regions") or task.get("bbox") or []
        has_attention_region = bool(regions)
        region_hits = _region_hits(gaze_point, regions) if gaze_valid else []
        current_in_region = bool(region_hits)
        should_push_feedback = False
        feedback_task_id = None
        feedback_count = 0

        if current_in_region:
            with self._state_lock:
                if self._task_active and self._current_task is not None:
                    self._current_task["in_region_frames"] = self._current_task.get("in_region_frames", 0) + 1

        frame_data = {
            "ts_us": system_time_stamp,
            "gaze": list(gaze_point) if gaze_valid else None,
            "hit": current_in_region,
        }
        frame_data.update(_extract_tobii_raw_fields(gaze_data))
        if current_in_region:
            frame_data["hits"] = region_hits

        aoi_revision = task.get("analysis_aoi_revision")
        if aoi_revision is not None:
            frame_data["aoi_revision"] = int(aoi_revision)
            if task.get("analysis_aoi_alignment_valid"):
                analysis_regions = task.get("analysis_aoi_regions") or []
                frame_data["aoi_hits"] = (
                    _region_hits(gaze_point, analysis_regions) if gaze_valid else []
                )

        # 向文件写入队列发送瘦身后的逐帧数据
        self._writer_queue.put({
            "evt": _EVT_GAZE_FRAME,
            "task_dir": task["task_dir"],
            "data": frame_data,
        })

        with self._state_lock:
            if not self._task_active or self._current_task is None:
                return

            if not has_attention_region:
                self._reset_out_of_box_state()
                return

            if not gaze_valid or current_in_region is False:
                self._consecutive_out_of_box_false += 1
                current_count = self._consecutive_out_of_box_false
                log_step = max(1, OUT_OF_BOX_FALSE_THRESHOLD // 4)
                if (
                    self._progress_logs_enabled and
                    (current_count == 1 or current_count - self._last_out_of_box_log_count >= log_step)
                ):
                    self._last_out_of_box_log_count = current_count
                    miss_reason = "invalid_gaze" if not gaze_valid else "outside_target"
                    self._log_info(
                        "注视点未命中目标: "
                        f"task_id={self._current_task.get('task_id')}, "
                        f"count={current_count}/{OUT_OF_BOX_FALSE_THRESHOLD}, "
                        f"reason={miss_reason}, gaze={gaze_point}, bbox={task['bbox']}"
                    )
                now_ms = int(time.time() * 1000)
                cooldown_elapsed = (
                    self._last_attention_feedback_time_ms <= 0
                    or now_ms - self._last_attention_feedback_time_ms >= ATTENTION_FEEDBACK_COOLDOWN_MS
                )
                if self._consecutive_out_of_box_false >= OUT_OF_BOX_FALSE_THRESHOLD and cooldown_elapsed:
                    should_push_feedback = True
                    feedback_task_id = self._current_task.get("task_id")
                    feedback_count = self._consecutive_out_of_box_false
                    self._log_info(
                        "未命中目标超时，准备触发提醒: "
                        f"task_id={feedback_task_id}, count={feedback_count}, "
                        f"reason={'invalid_gaze' if not gaze_valid else 'outside_target'}, gaze={gaze_point}"
                    )
                    self._last_attention_feedback_time_ms = now_ms
            else:
                if self._progress_logs_enabled and self._consecutive_out_of_box_false > 0:
                    self._log_info(
                        "注视点回到目标框内: "
                        f"task_id={self._current_task.get('task_id')}, "
                        f"cleared_count={self._consecutive_out_of_box_false}, gaze={gaze_point}"
                    )
                self._reset_out_of_box_state()

        if should_push_feedback:
            self._push_attention_feedback(feedback_task_id, feedback_count)

    def _push_attention_feedback(self, task_id: str, consecutive_count: int):
        """从 gaze 回调线程安全地触发前端注意力反馈广播。"""
        payload = {
            "ok": True,
            "type": "attention_feedback",
            "action": "flash_mode",
            "should_flash": True,
            "duration_ms": 3000,
            "reason": "consecutive_not_in_target",
            "consecutive_false_count": consecutive_count,
            "task_id": task_id,
            "server_time_ms": int(time.time() * 1000),
        }

        with self._state_lock:
            if (
                self._current_task
                and isinstance(self._current_task, dict)
                and self._current_task.get("task_id") == str(task_id)
            ):
                self._current_task["feedback_count"] = (
                    self._current_task.get("feedback_count", 0) + 1
                )

        feedback_payload = _sanitize_feedback_payload(payload)
        self._enqueue_db(
            "INSERT INTO gaze_feedback_events "
            "(task_id, event_time_ms, reason, consecutive_false_count, threshold, payload_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(task_id),
                payload["server_time_ms"],
                payload["reason"],
                int(consecutive_count),
                int(OUT_OF_BOX_FALSE_THRESHOLD),
                json.dumps(feedback_payload, ensure_ascii=False),
            ),
        )

        if self._ws_event_loop is None:
            self._log_info(
                "注意力反馈未广播: WS事件循环未设置, "
                f"task_id={task_id}, consecutive_count={consecutive_count}"
            )
            return
        with self._clients_lock:
            client_count = len(self._connected_clients)
        self._log_info(f"发送注意力反馈: clients={client_count}, payload={payload}")
        asyncio.run_coroutine_threadsafe(self.broadcast(payload), self._ws_event_loop)

    # ═══════════════════════════════════════════
    # 后台文件写入线程
    # ═══════════════════════════════════════════

    def _run_writer(self):
        """
        后台 daemon 线程：持续消费写入队列，将 raw frame 写入任务文件，并执行 SQLite 写入。

        每个 task_dir 保持 raw_gaze 文件句柄。
        收到 close_task 事件时关闭对应句柄。
        收到 db_exec 事件时执行 SQL 写入 gaze_records.db。
        收到 stop_writer sentinel 时退出。
        """
        # 初始化眼动记录数据库
        os.makedirs(self._data_dir, exist_ok=True)
        db_conn = sqlite3.connect(self._db_path)
        db_conn.execute("PRAGMA journal_mode=WAL")
        self._init_gaze_db(db_conn)

        # 已打开的文件句柄：{task_dir: {"gaze": file}}
        open_handles: dict[str, dict] = {}

        def _get_handles(task_dir: str) -> dict:
            if task_dir not in open_handles:
                os.makedirs(task_dir, exist_ok=True)
                open_handles[task_dir] = {
                    "gaze": open(
                        os.path.join(task_dir, "raw_gaze.jsonl"), "a", encoding="utf-8"
                    ),
                }
            return open_handles[task_dir]

        def _close_handles(task_dir: str):
            if task_dir in open_handles:
                for fh in open_handles[task_dir].values():
                    try:
                        fh.flush()
                        fh.close()
                    except Exception:
                        pass
                del open_handles[task_dir]

        while True:
            try:
                item = self._writer_queue.get(timeout=1.0)
            except queue.Empty:
                # 定期 flush 所有打开的句柄
                for handles in open_handles.values():
                    for fh in handles.values():
                        try:
                            fh.flush()
                        except Exception:
                            pass
                continue

            evt = item.get("evt")

            if evt == _EVT_STOP_WRITER:
                break

            if evt == _EVT_DB_EXEC:
                try:
                    db_conn.execute(item["sql"], item.get("params", ()))
                    db_conn.commit()
                except Exception as e:
                    print(f"[GazeService] DB 写入出错: {e}")
                continue

            task_dir = item.get("task_dir")
            data = item.get("data", {})

            if not task_dir:
                continue

            try:
                if evt == _EVT_GAZE_FRAME:
                    handles = _get_handles(task_dir)
                    handles["gaze"].write(json.dumps(data, ensure_ascii=False) + "\n")

                elif evt == _EVT_CLOSE_TASK:
                    _close_handles(task_dir)

            except Exception as e:
                print(f"[GazeService] 文件写入出错 ({evt}): {e}")

        # 退出前关闭所有文件句柄和数据库连接
        for task_dir in list(open_handles.keys()):
            _close_handles(task_dir)
        _close_sqlite_wal_connection(db_conn)

    def shutdown(self, timeout: float | None = None):
        """关闭后台写入线程（进程退出前调用）。"""
        self.disconnect()
        with self._shutdown_lock:
            if not self._shutdown_requested:
                self._shutdown_requested = True
                self._writer_queue.put({"evt": _EVT_STOP_WRITER})
        self._writer_thread.join(timeout=timeout)
        if self._writer_thread.is_alive():
            print("[GazeService] writer shutdown timed out; WAL files may remain until process exit")


# ═══════════════════════════════════════════════
# 纯函数工具（无状态，也可被外部直接导入）
# ═══════════════════════════════════════════════

def _safe_path_segment(value, default: str = "unknown") -> str:
    text = str(value or "").strip()
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in text)
    cleaned = cleaned.strip(" .")
    return (cleaned or default)[:120]


def _close_sqlite_wal_connection(conn: sqlite3.Connection) -> None:
    try:
        conn.commit()
    except sqlite3.Error:
        pass
    for sql in ("PRAGMA wal_checkpoint(TRUNCATE)", "PRAGMA journal_mode=DELETE"):
        try:
            conn.execute(sql).fetchall()
        except sqlite3.Error:
            pass
    try:
        conn.close()
    except sqlite3.Error:
        pass


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str):
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _sanitize_marker_payload(payload: dict) -> dict:
    duplicated_fields = {
        "task_id",
        "user_id",
        "event_type",
        "gaze_task_id",
        "timestamp",
        "timestamp_ms",
        "timestamp_us",
    }
    return {
        key: value
        for key, value in payload.items()
        if key not in duplicated_fields
    }


def _sanitize_feedback_payload(payload: dict) -> dict:
    duplicated_fields = {
        "task_id",
        "user_id",
        "server_time_ms",
        "event_time_ms",
        "reason",
        "consecutive_false_count",
        "threshold",
    }
    return {
        key: value
        for key, value in payload.items()
        if key not in duplicated_fields
    }


def _json_safe_tobii_value(value):
    """Convert SDK tuples and non-finite sentinel values to strict JSON values."""
    if isinstance(value, (tuple, list)):
        return [_json_safe_tobii_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _extract_tobii_raw_fields(gaze_data: dict) -> dict:
    """Keep the per-eye measurements that arrive with Tobii gaze data."""
    raw = {}
    timestamp_fields = {
        "device_time_stamp": "device_ts_us",
        "system_time_stamp": "sdk_system_ts_us",
    }
    for sdk_key, raw_key in timestamp_fields.items():
        if sdk_key in gaze_data:
            raw[raw_key] = _json_safe_tobii_value(gaze_data[sdk_key])

    eye_fields = {
        "gaze_point_on_display_area": "gaze_display",
        "gaze_point_in_user_coordinate_system": "gaze_user_mm",
        "gaze_point_validity": "gaze_valid",
        "pupil_diameter": "pupil_diameter_mm",
        "pupil_validity": "pupil_valid",
        "gaze_origin_in_user_coordinate_system": "origin_user_mm",
        "gaze_origin_in_trackbox_coordinate_system": "origin_trackbox",
        "gaze_origin_validity": "origin_valid",
    }
    for side in ("left", "right"):
        eye = {}
        for sdk_suffix, raw_key in eye_fields.items():
            sdk_key = f"{side}_{sdk_suffix}"
            if sdk_key not in gaze_data:
                continue
            value = gaze_data[sdk_key]
            if sdk_suffix.endswith("validity"):
                value = bool(value)
            eye[raw_key] = _json_safe_tobii_value(value)
        if eye:
            raw[f"{side}_eye"] = eye
    return raw


def _get_gaze_point(gaze_data: dict) -> tuple[tuple | None, bool]:
    """从 Tobii 帧数据提取有效注视点（优先双眼均值，回退单眼）。"""
    left_valid = gaze_data.get("left_gaze_point_validity") == 1
    right_valid = gaze_data.get("right_gaze_point_validity") == 1
    left_pt = gaze_data.get("left_gaze_point_on_display_area")
    right_pt = gaze_data.get("right_gaze_point_on_display_area")

    if left_valid and right_valid and _is_point_pair(left_pt) and _is_point_pair(right_pt):
        lx, ly = _as_float(left_pt[0]), _as_float(left_pt[1])
        rx, ry = _as_float(right_pt[0]), _as_float(right_pt[1])
        if None not in (lx, ly, rx, ry):
            return ((lx + rx) / 2, (ly + ry) / 2), True

    if left_valid and _is_point_pair(left_pt):
        lx, ly = _as_float(left_pt[0]), _as_float(left_pt[1])
        if None not in (lx, ly):
            return (lx, ly), True

    if right_valid and _is_point_pair(right_pt):
        rx, ry = _as_float(right_pt[0]), _as_float(right_pt[1])
        if None not in (rx, ry):
            return (rx, ry), True

    return None, False


def _is_point_pair(value) -> bool:
    return isinstance(value, (list, tuple)) and len(value) >= 2


def _normalize_bboxes(
    bbox_list: list, screen_width: float, screen_height: float, clip: bool = True
) -> list:
    """将像素 bbox 列表归一化到 0-1 坐标系。"""
    result = []
    for x1, y1, x2, y2 in bbox_list:
        nx1 = x1 / screen_width
        ny1 = y1 / screen_height
        nx2 = x2 / screen_width
        ny2 = y2 / screen_height
        if clip:
            nx1, nx2 = max(0.0, min(1.0, nx1)), max(0.0, min(1.0, nx2))
            ny1, ny2 = max(0.0, min(1.0, ny1)), max(0.0, min(1.0, ny2))
        result.append([nx1, ny1, nx2, ny2])
    return result


def _normalize_regions(
    regions: list | None,
    bbox: list | None,
    coordinate_space: str | None,
    screen_width: float,
    screen_height: float,
    clip: bool = True,
) -> list:
    raw_regions = regions if isinstance(regions, list) else None
    if raw_regions is None:
        raw_regions = [
            {"shape": "rect", "left": x1, "top": y1, "right": x2, "bottom": y2}
            for x1, y1, x2, y2 in (bbox or [])
        ]

    space = _normalize_coordinate_space(coordinate_space) or _infer_coordinate_space(raw_regions)
    result = []
    for region in raw_regions:
        if not isinstance(region, dict):
            continue
        shape = str(region.get("shape") or "rect").lower()
        if shape == "ellipse":
            cx = _as_float(region.get("cx"))
            cy = _as_float(region.get("cy"))
            rx = _as_float(region.get("rx"))
            ry = _as_float(region.get("ry"))
            if cx is None or cy is None or rx is None or ry is None or rx <= 0 or ry <= 0:
                continue
            if space == "physical_pixel":
                cx, cy = cx / screen_width, cy / screen_height
                rx, ry = rx / screen_width, ry / screen_height
            normalized = {"shape": "ellipse", "cx": cx, "cy": cy, "rx": rx, "ry": ry}
        else:
            left = _as_float(region.get("left"))
            top = _as_float(region.get("top"))
            right = _as_float(region.get("right"))
            bottom = _as_float(region.get("bottom"))
            if left is None or top is None or right is None or bottom is None:
                continue
            if space == "physical_pixel":
                left, right = left / screen_width, right / screen_width
                top, bottom = top / screen_height, bottom / screen_height
            left, right = min(left, right), max(left, right)
            top, bottom = min(top, bottom), max(top, bottom)
            normalized = {"shape": "rect", "left": left, "top": top, "right": right, "bottom": bottom}
        if region.get("id") is not None:
            normalized["id"] = str(region.get("id"))
        if clip:
            normalized = _clip_region(normalized)
        result.append(normalized)
    return result


def _normalize_analysis_aoi_regions(
    regions: list | None,
    coordinate_space: str | None,
    screen_width: float,
    screen_height: float,
) -> list:
    """Normalize and retain metadata for the seven experiment-analysis AOIs."""
    if not isinstance(regions, list):
        raise ValueError("regions must be a list")
    seen_ids: set[str] = set()
    result = []
    for raw_region in regions:
        if not isinstance(raw_region, dict):
            continue
        region_id = str(raw_region.get("id") or "").strip()
        if region_id not in ANALYSIS_AOI_IDS:
            raise ValueError(f"unsupported analysis AOI id: {region_id or '<empty>'}")
        if region_id in seen_ids:
            raise ValueError(f"duplicate analysis AOI id: {region_id}")
        seen_ids.add(region_id)
        normalized_items = _normalize_regions(
            regions=[raw_region],
            bbox=None,
            coordinate_space=coordinate_space,
            screen_width=screen_width,
            screen_height=screen_height,
        )
        if not normalized_items:
            raise ValueError(f"invalid analysis AOI geometry: {region_id}")
        normalized = normalized_items[0]
        normalized["visible"] = bool(raw_region.get("visible"))
        binding = raw_region.get("binding")
        normalized["binding"] = binding if isinstance(binding, dict) else {}
        result.append(normalized)
    return sorted(result, key=lambda item: item["id"])


def _infer_coordinate_space(regions: list) -> str:
    for region in regions:
        if not isinstance(region, dict):
            continue
        for key in ("left", "top", "right", "bottom", "cx", "cy", "rx", "ry"):
            value = _as_float(region.get(key))
            if value is not None and abs(value) > 1:
                return "physical_pixel"
    return "display_area_normalized"


def _normalize_coordinate_space(coordinate_space: str | None) -> str | None:
    if not coordinate_space:
        return None
    value = str(coordinate_space).lower()
    if value in {"physical", "physical_pixel", "physical_pixels", "pixel", "pixels"}:
        return "physical_pixel"
    if value in {"display_area_normalized", "normalized", "normalised"}:
        return "display_area_normalized"
    return None


def _as_float(value) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _clip_region(region: dict) -> dict:
    if region.get("shape") == "ellipse":
        return {
            **region,
            "cx": _clip01(region["cx"]),
            "cy": _clip01(region["cy"]),
            "rx": max(0.0, min(1.0, region["rx"])),
            "ry": max(0.0, min(1.0, region["ry"])),
        }
    return {
        **region,
        "left": _clip01(region["left"]),
        "top": _clip01(region["top"]),
        "right": _clip01(region["right"]),
        "bottom": _clip01(region["bottom"]),
    }


def _point_in_regions(point: tuple, regions: list) -> bool:
    return bool(_region_hits(point, regions))


def _region_hits(point: tuple | None, regions: list) -> list:
    if point is None or not regions:
        return []
    x, y = point
    hits = []
    for index, region in enumerate(regions):
        hit = False
        if isinstance(region, dict):
            shape = str(region.get("shape") or "rect").lower()
            if shape == "ellipse":
                cx = region.get("cx")
                cy = region.get("cy")
                rx = region.get("rx")
                ry = region.get("ry")
                if cx is None or cy is None or not rx or not ry:
                    continue
                hit = bool(((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1)
            else:
                left = region.get("left")
                top = region.get("top")
                right = region.get("right")
                bottom = region.get("bottom")
                if None in (left, top, right, bottom):
                    continue
                hit = bool(
                    left <= x <= right
                    and top <= y <= bottom
                )
            if hit:
                hits.append(str(region.get("id") or f"region_{index + 1}"))
        else:
            x1, y1, x2, y2 = region
            if x1 <= x <= x2 and y1 <= y <= y2:
                hits.append(f"region_{index + 1}")
    return hits


def _point_in_bboxes(point: tuple, bboxes: list) -> bool:
    """判断归一化注视点是否落在任意一个 bbox 内。"""
    if point is None or not bboxes:
        return False
    x, y = point
    for x1, y1, x2, y2 in bboxes:
        if x1 <= x <= x2 and y1 <= y <= y2:
            return True
    return False
