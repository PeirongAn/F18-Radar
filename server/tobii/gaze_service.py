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
    {data_dir}/{task_id}/
        raw_gaze.jsonl      # 每帧一行：{"ts_us":…,"gaze":[x,y],"in_box":true|false|null}
        fixation.jsonl      # 注视事件：{"ts_us":…,"event":"fixation_start|fixation_end"}
        summary.json        # 任务结束时写入：元数据 + 统计信息
"""

import math
import time
import uuid
import json
import sqlite3
import queue
import asyncio
import os
import threading
from collections import deque


# 连续未注视帧数阈值，超过后推送注意力反馈
OUT_OF_BOX_FALSE_THRESHOLD = 2000

# 写入队列中的事件类型标识
_EVT_GAZE_FRAME = "gaze_frame"
_EVT_FIXATION = "fixation"
_EVT_TASK_SUMMARY = "task_summary"
_EVT_STOP_WRITER = "stop_writer"
_EVT_DB_EXEC = "db_exec"


class GazeService:
    """眼动追踪服务，封装 Tobii 设备与所有业务逻辑。"""

    def __init__(self, data_dir: str = None, gaze_window_size: int = 600):
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
        self._flag: bool = False          # 当前是否处于 fixation 中
        self._task_active: bool = False
        self._current_task: dict | None = None
        self._state_lock = threading.Lock()

        # ── 最新注视点（可视化 / 轮询用）──────
        self._latest_gaze_point: list | None = None
        self._latest_gaze_time: float | None = None
        self._gaze_point_lock = threading.Lock()

        # ── 注意力反馈状态 ────────────────────
        self._consecutive_out_of_box_false: int = 0
        self._out_of_box_feedback_sent: bool = False

        # ── WebSocket 广播 ────────────────────
        self._connected_clients: set = set()
        self._clients_lock = threading.Lock()
        self._ws_event_loop: asyncio.AbstractEventLoop | None = None

        # ── 后台文件写入队列 ──────────────────
        self._writer_queue: queue.Queue = queue.Queue()
        self._writer_thread = threading.Thread(
            target=self._run_writer, daemon=True, name="GazeFileWriter"
        )
        self._writer_thread.start()

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
        screen_size: tuple,
        task_id: str | int | None = None,
        user_id: str = "",
        task_source: str = "",
        task_name: str = "",
        system_time: int | None = None,
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

        screen_w, screen_h = screen_size or (1, 1)
        normalized_bbox = _normalize_bboxes(bbox, screen_w or 1, screen_h or 1)

        # 优先使用外部传入的 task_id，回退到生成 UUID
        resolved_task_id = str(task_id) if task_id is not None else str(uuid.uuid4())

        # 创建任务目录
        task_dir = os.path.join(self._data_dir, resolved_task_id)
        os.makedirs(task_dir, exist_ok=True)

        with self._state_lock:
            self._current_task = {
                "task_id": resolved_task_id,
                "task_dir": task_dir,
                "bbox": normalized_bbox,
                "start_system_time": system_time,
                "user_id": user_id or "",
                "task_source": task_source or "",
                "task_name": task_name or "",
                "frame_count": 0,
                "fixation_count": 0,
            }
            self._task_active = True
            self._flag = False
            self._reset_out_of_box_state()

        # 记录任务开始到 gaze_records.db
        self._enqueue_db(
            "INSERT OR REPLACE INTO gaze_tasks "
            "(task_id, user_id, task_name, data_dir, start_time_us, status) "
            "VALUES (?, ?, ?, ?, ?, 'active')",
            (resolved_task_id, user_id or "", task_name or "", task_dir, system_time),
        )
        if normalized_bbox:
            self._enqueue_db(
                "INSERT INTO gaze_targets "
                "(task_id, bbox_json, normalized_bbox_json, screen_width, screen_height, appear_time_us) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (resolved_task_id, json.dumps(bbox), json.dumps(normalized_bbox),
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
    ) -> dict:
        """
        记录目标窗口消失、结束当前任务并写入 summary.json。

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

        resolved_task_id = task_id or self._get_active_task_id()
        if not resolved_task_id:
            raise ValueError("窗口消失时必须提供 task_id 或存在活动任务")

        with self._state_lock:
            if self._task_active and self._flag is True:
                self._enqueue_fixation_event(resolved_task_id, "fixation_end", system_time)

            self._flag = False
            self._task_active = False
            self._reset_out_of_box_state()

            task_info = self._current_task
            begin_time = (
                self._current_task["start_system_time"]
                if self._current_task
                else system_time
            )
            effective_user_id = user_id or (
                self._current_task.get("user_id") if self._current_task else ""
            )
            effective_task_source = task_source or (
                self._current_task.get("task_source") if self._current_task else ""
            )
            effective_task_name = task_name or (
                self._current_task.get("task_name") if self._current_task else ""
            )
            task_dir = self._current_task.get("task_dir") if self._current_task else None
            frame_count = self._current_task.get("frame_count", 0) if self._current_task else 0
            fixation_count = self._current_task.get("fixation_count", 0) if self._current_task else 0
            self._current_task = None

        # 自动关闭该任务下所有未关闭的目标事件
        self._enqueue_db(
            "UPDATE gaze_targets SET disappear_time_us = ?, auto_closed = 1 "
            "WHERE task_id = ? AND disappear_time_us IS NULL",
            (system_time, resolved_task_id),
        )
        # 更新任务记录为已完成
        self._enqueue_db(
            "UPDATE gaze_tasks SET end_time_us = ?, duration_ms = ?, "
            "total_frames = ?, fixation_count = ?, status = 'completed' "
            "WHERE task_id = ?",
            (system_time, (system_time - begin_time) / 1000,
             frame_count, fixation_count, resolved_task_id),
        )

        # 向写入队列发送 summary sentinel
        if task_dir:
            summary = {
                "task_id": resolved_task_id,
                "user_id": effective_user_id,
                "task_source": effective_task_source,
                "task_name": effective_task_name,
                "start_us": begin_time,
                "end_us": system_time,
                "duration_ms": (system_time - begin_time) / 1000,
                "total_frames": frame_count,
                "fixation_count": fixation_count,
            }
            self._writer_queue.put({
                "evt": _EVT_TASK_SUMMARY,
                "task_dir": task_dir,
                "data": summary,
            })

        print(f"[GazeService] 任务结束: task_id={resolved_task_id}")
        return {
            "task_id": resolved_task_id,
            "task_info": task_info,
        }

    def get_active_task_id(self) -> str | None:
        """公开接口：获取当前活动任务 ID。"""
        return self._get_active_task_id()

    def set_task_bbox(
        self,
        bbox: list,
        screen_size: tuple,
        task_id: str | None = None,
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
        screen_w, screen_h = screen_size or (1, 1)
        normalized_bbox = _normalize_bboxes(bbox, screen_w or 1, screen_h or 1)

        with self._state_lock:
            if not self._task_active or self._current_task is None:
                return False
            if task_id is not None and self._current_task.get("task_id") != str(task_id):
                return False
            active_task_id = self._current_task["task_id"]
            self._current_task["bbox"] = normalized_bbox
            self._reset_out_of_box_state()

        now_us = int(time.time() * 1_000_000)

        # 先关闭该任务下所有未关闭的目标（disappear_time_us IS NULL）
        self._enqueue_db(
            "UPDATE gaze_targets SET disappear_time_us = ? "
            "WHERE task_id = ? AND disappear_time_us IS NULL",
            (now_us, active_task_id),
        )
        # 若新 bbox 非空，记录目标出现
        if bbox:
            self._enqueue_db(
                "INSERT INTO gaze_targets "
                "(task_id, bbox_json, normalized_bbox_json, "
                "screen_width, screen_height, appear_time_us) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (active_task_id, json.dumps(bbox), json.dumps(normalized_bbox),
                 int(screen_w), int(screen_h), now_us),
            )

        print(f"[GazeService] bbox 已更新: {normalized_bbox}")
        return True

    # ═══════════════════════════════════════════
    # 眼动数据库辅助方法
    # ═══════════════════════════════════════════

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
                task_name   TEXT    DEFAULT '',
                data_dir    TEXT,
                start_time_us INTEGER NOT NULL,
                end_time_us   INTEGER,
                duration_ms   REAL,
                total_frames    INTEGER DEFAULT 0,
                fixation_count  INTEGER DEFAULT 0,
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
        """)

    # ═══════════════════════════════════════════
    # WebSocket 客户端管理
    # ═══════════════════════════════════════════

    def set_ws_event_loop(self, loop: asyncio.AbstractEventLoop):
        """设置 asyncio 事件循环，用于从 gaze 回调线程触发广播。"""
        self._ws_event_loop = loop

    def register_ws_client(self, websocket):
        """注册一个新的 WebSocket 连接。"""
        with self._clients_lock:
            self._connected_clients.add(websocket)

    def unregister_ws_client(self, websocket):
        """注销一个 WebSocket 连接。"""
        with self._clients_lock:
            self._connected_clients.discard(websocket)

    async def broadcast(self, message_obj: dict):
        """向所有已注册客户端广播 JSON 消息（异步）。"""
        message = json.dumps(message_obj, ensure_ascii=False)
        with self._clients_lock:
            clients = list(self._connected_clients)

        stale = []
        for client in clients:
            try:
                await client.send(message)
            except Exception:
                stale.append(client)

        if stale:
            with self._clients_lock:
                for c in stale:
                    self._connected_clients.discard(c)

    # ═══════════════════════════════════════════
    # 内部实现
    # ═══════════════════════════════════════════

    def _reset_out_of_box_state(self):
        self._consecutive_out_of_box_false = 0
        self._out_of_box_feedback_sent = False

    def _get_active_task_id(self) -> str | None:
        if self._current_task and isinstance(self._current_task, dict):
            return self._current_task.get("task_id")
        return None

    def _gaze_data_callback(self, gaze_data: dict):
        """Tobii 实时数据回调——每帧调用一次。"""
        system_time_stamp = int(time.time() * 1_000_000)
        gaze_point = _get_valid_gaze_point(gaze_data)

        frame_record = {
            "system_time_stamp": system_time_stamp,
            "gaze_point": gaze_point,
        }

        with self._window_lock:
            self._gaze_window.append(frame_record)

        with self._gaze_point_lock:
            self._latest_gaze_point = list(gaze_point)
            self._latest_gaze_time = time.time() * 1000

        with self._state_lock:
            if not self._task_active or self._current_task is None:
                return
            task = self._current_task
            task["frame_count"] = task.get("frame_count", 0) + 1

        current_in_box = _point_in_bboxes(gaze_point, task["bbox"])
        should_push_feedback = False
        feedback_task_id = None

        # 向文件写入队列发送帧数据
        self._writer_queue.put({
            "evt": _EVT_GAZE_FRAME,
            "task_dir": task["task_dir"],
            "data": {
                "ts_us": system_time_stamp,
                "gaze": list(gaze_point),
                "in_box": current_in_box,
            },
        })

        with self._state_lock:
            if not self._task_active or self._current_task is None:
                return

            if current_in_box is False:
                self._consecutive_out_of_box_false += 1
                if self._consecutive_out_of_box_false >= OUT_OF_BOX_FALSE_THRESHOLD:
                    should_push_feedback = True
                    feedback_task_id = self._current_task.get("task_id")
                    self._consecutive_out_of_box_false = 0
            else:
                self._consecutive_out_of_box_false = 0

            if self._flag is False and current_in_box is True:
                self._flag = True
                self._current_task["fixation_count"] = self._current_task.get("fixation_count", 0) + 1
                self._enqueue_fixation_event(task["task_id"], "fixation_start", system_time_stamp)
            elif self._flag is True and current_in_box is False:
                self._flag = False
                self._enqueue_fixation_event(task["task_id"], "fixation_end", system_time_stamp)

        if should_push_feedback:
            self._push_attention_feedback(feedback_task_id, self._consecutive_out_of_box_false)

    def _enqueue_fixation_event(self, task_id: str, event_type: str, ts_us: int):
        """将注视事件放入写入队列。
        
        此方法在已持有 _state_lock 的代码路径中调用，Queue 操作本身是线程安全的，
        无需再次加锁。task_dir 由 task_id 和 data_dir 确定性计算得到。
        """
        task_dir = os.path.join(self._data_dir, task_id)
        self._writer_queue.put({
            "evt": _EVT_FIXATION,
            "task_dir": task_dir,
            "data": {
                "ts_us": ts_us,
                "event": event_type,
            },
        })
        print(f"[GazeService] fixation 事件: task_id={task_id}, type={event_type}")

    def _push_attention_feedback(self, task_id: str, consecutive_count: int):
        """从 gaze 回调线程安全地触发前端注意力反馈广播。"""
        if self._ws_event_loop is None:
            return
        payload = {
            "ok": True,
            "type": "attention_feedback",
            "action": "flash_mode",
            "should_flash": True,
            "duration_ms": 3000,
            "reason": "consecutive_out_of_box_false",
            "consecutive_false_count": consecutive_count,
            "task_id": task_id,
            "server_time_ms": int(time.time() * 1000),
        }
        print(f"[GazeService] 发送注意力反馈: {payload}")
        asyncio.run_coroutine_threadsafe(self.broadcast(payload), self._ws_event_loop)

    # ═══════════════════════════════════════════
    # 后台文件写入线程
    # ═══════════════════════════════════════════

    def _run_writer(self):
        """
        后台 daemon 线程：持续消费写入队列，将数据路由到对应文件和数据库。

        每个 task_dir 保持一对打开的文件句柄（raw_gaze + fixation），
        收到 task_summary 事件时写 summary.json 并关闭对应句柄。
        收到 db_exec 事件时执行 SQL 写入 gaze_records.db。
        收到 stop_writer sentinel 时退出。
        """
        # 初始化眼动记录数据库
        os.makedirs(self._data_dir, exist_ok=True)
        db_conn = sqlite3.connect(self._db_path)
        db_conn.execute("PRAGMA journal_mode=WAL")
        self._init_gaze_db(db_conn)

        # 已打开的文件句柄：{task_dir: {"gaze": file, "fixation": file}}
        open_handles: dict[str, dict] = {}

        def _get_handles(task_dir: str) -> dict:
            if task_dir not in open_handles:
                os.makedirs(task_dir, exist_ok=True)
                open_handles[task_dir] = {
                    "gaze": open(
                        os.path.join(task_dir, "raw_gaze.jsonl"), "a", encoding="utf-8"
                    ),
                    "fixation": open(
                        os.path.join(task_dir, "fixation.jsonl"), "a", encoding="utf-8"
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

                elif evt == _EVT_FIXATION:
                    handles = _get_handles(task_dir)
                    handles["fixation"].write(json.dumps(data, ensure_ascii=False) + "\n")
                    handles["fixation"].flush()

                elif evt == _EVT_TASK_SUMMARY:
                    # flush & close 之前打开的帧文件句柄，再写 summary
                    _close_handles(task_dir)
                    summary_path = os.path.join(task_dir, "summary.json")
                    with open(summary_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    print(f"[GazeService] summary 已写入: {summary_path}")

            except Exception as e:
                print(f"[GazeService] 文件写入出错 ({evt}): {e}")

        # 退出前关闭所有文件句柄和数据库连接
        for task_dir in list(open_handles.keys()):
            _close_handles(task_dir)
        try:
            db_conn.close()
        except Exception:
            pass

    def shutdown(self):
        """关闭后台写入线程（进程退出前调用）。"""
        self._writer_queue.put({"evt": _EVT_STOP_WRITER})
        self._writer_thread.join(timeout=5)


# ═══════════════════════════════════════════════
# 纯函数工具（无状态，也可被外部直接导入）
# ═══════════════════════════════════════════════

def _get_valid_gaze_point(gaze_data: dict) -> tuple:
    """从 Tobii 帧数据提取有效注视点（优先双眼均值，回退单眼）。"""
    left_valid = gaze_data.get("left_gaze_point_validity") == 1
    right_valid = gaze_data.get("right_gaze_point_validity") == 1
    left_pt = gaze_data.get("left_gaze_point_on_display_area")
    right_pt = gaze_data.get("right_gaze_point_on_display_area")

    if left_valid and right_valid:
        lx, ly = left_pt
        rx, ry = right_pt
        if not any(math.isnan(v) for v in (lx, ly, rx, ry)):
            return ((lx + rx) / 2, (ly + ry) / 2)

    if left_valid:
        lx, ly = left_pt
        if not (math.isnan(lx) or math.isnan(ly)):
            return (lx, ly)

    if right_valid:
        rx, ry = right_pt
        if not (math.isnan(rx) or math.isnan(ry)):
            return (rx, ry)

    return (0.0, 0.0)


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


def _point_in_bboxes(point: tuple, bboxes: list) -> bool:
    """判断归一化注视点是否落在任意一个 bbox 内。"""
    if point is None or not bboxes:
        return False
    x, y = point
    for x1, y1, x2, y2 in bboxes:
        if x1 <= x <= x2 and y1 <= y <= y2:
            return True
    return False
