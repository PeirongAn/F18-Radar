from __future__ import annotations

import csv
import json
import os
import sqlite3
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from glob import glob
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional


SERVER_DIR = Path(__file__).resolve().parents[1]
DEFAULT_VENDOR_ROOT = r"D:\hengzhi\data"
DEFAULT_DB_PATH = SERVER_DIR / "data" / "physio" / "experiment_data.sqlite3"
DEFAULT_EXPORT_DIR = SERVER_DIR / "data" / "physio" / "exports"
DEFAULT_RAW_DIR = SERVER_DIR / "data" / "physio" / "raw"
DEFAULT_STREAMS = ["ppg", "eda", "acc", "gyro", "hr", "skt", "env", "o2"]
SAMPLE_HEADER = [
    "stream",
    "service_time_ns",
    "device_time_ms",
    "subject_id",
    "run_id",
    "trial_id",
    "values_json",
    "source_session_path",
]


def now_ns() -> int:
    return time.time_ns()


def iso_now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def latest_vendor_session(root: str) -> Optional[str]:
    sessions = [
        path
        for path in glob(os.path.join(root, "**", "_DYN*"), recursive=True)
        if os.path.isdir(path)
    ]
    if not sessions:
        return None
    return max(sessions, key=os.path.getmtime)


def read_header(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        return [item.strip() or f"col_{idx}" for idx, item in enumerate(next(reader))]


def parse_csv_line(line: str) -> Optional[List[str]]:
    if not line.strip():
        return None
    try:
        row = next(csv.reader([line]))
    except csv.Error:
        return None
    return row or None


@dataclass
class TailState:
    stream: str
    path: str
    labels: List[str]
    position: int


class Database:
    def __init__(self, path: str | os.PathLike[str]):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init_schema()

    def init_schema(self) -> None:
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS subjects (
                    subject_id TEXT PRIMARY KEY,
                    metadata_json TEXT NOT NULL,
                    created_at_ns INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_runs (
                    run_id TEXT PRIMARY KEY,
                    subject_id TEXT NOT NULL,
                    task_name TEXT NOT NULL,
                    started_at_ns INTEGER NOT NULL,
                    ended_at_ns INTEGER,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trials (
                    trial_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    trial_name TEXT NOT NULL,
                    started_at_ns INTEGER NOT NULL,
                    ended_at_ns INTEGER,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS markers (
                    marker_id TEXT PRIMARY KEY,
                    subject_id TEXT,
                    run_id TEXT,
                    trial_id TEXT,
                    name TEXT NOT NULL,
                    service_time_ns INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS samples (
                    sample_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stream TEXT NOT NULL,
                    service_time_ns INTEGER NOT NULL,
                    device_time_ms REAL,
                    subject_id TEXT NOT NULL,
                    run_id TEXT,
                    trial_id TEXT,
                    values_json TEXT NOT NULL,
                    source_session_path TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS source_sessions (
                    source_session_path TEXT PRIMARY KEY,
                    discovered_at_ns INTEGER NOT NULL,
                    last_seen_at_ns INTEGER NOT NULL,
                    active INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sample_files (
                    run_id TEXT PRIMARY KEY,
                    subject_id TEXT NOT NULL,
                    trial_id TEXT,
                    file_path TEXT NOT NULL,
                    row_count INTEGER NOT NULL DEFAULT 0,
                    started_at_ns INTEGER NOT NULL,
                    ended_at_ns INTEGER,
                    first_sample_ns INTEGER,
                    last_sample_ns INTEGER,
                    streams_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_samples_context
                    ON samples(subject_id, run_id, trial_id, service_time_ns);
                CREATE INDEX IF NOT EXISTS idx_markers_context
                    ON markers(subject_id, run_id, trial_id, service_time_ns);
                CREATE INDEX IF NOT EXISTS idx_sample_files_context
                    ON sample_files(subject_id, run_id, trial_id);
                """
            )
            self.conn.commit()

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    def upsert_subject(self, subject_id: str, metadata: Dict[str, Any]) -> None:
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO subjects(subject_id, metadata_json, created_at_ns)
                VALUES (?, ?, ?)
                ON CONFLICT(subject_id) DO UPDATE SET metadata_json=excluded.metadata_json
                """,
                (subject_id, json_dumps(metadata), now_ns()),
            )
            self.conn.commit()

    def create_task(self, subject_id: str, task_name: str, metadata: Dict[str, Any]) -> str:
        run_id = uuid.uuid4().hex
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO task_runs(run_id, subject_id, task_name, started_at_ns, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, subject_id, task_name, now_ns(), json_dumps(metadata)),
            )
            self.conn.commit()
        return run_id

    def end_task(self, run_id: str) -> None:
        with self.lock:
            self.conn.execute(
                "UPDATE task_runs SET ended_at_ns=? WHERE run_id=? AND ended_at_ns IS NULL",
                (now_ns(), run_id),
            )
            self.conn.commit()

    def create_trial(self, run_id: str, trial_name: str, metadata: Dict[str, Any]) -> str:
        trial_id = uuid.uuid4().hex
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO trials(trial_id, run_id, trial_name, started_at_ns, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (trial_id, run_id, trial_name, now_ns(), json_dumps(metadata)),
            )
            self.conn.commit()
        return trial_id

    def end_trial(self, trial_id: str) -> None:
        with self.lock:
            self.conn.execute(
                "UPDATE trials SET ended_at_ns=? WHERE trial_id=? AND ended_at_ns IS NULL",
                (now_ns(), trial_id),
            )
            self.conn.commit()

    def insert_marker(
        self,
        subject_id: Optional[str],
        run_id: Optional[str],
        trial_id: Optional[str],
        name: str,
        payload: Dict[str, Any],
    ) -> str:
        marker_id = uuid.uuid4().hex
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO markers(marker_id, subject_id, run_id, trial_id, name, service_time_ns, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (marker_id, subject_id, run_id, trial_id, name, now_ns(), json_dumps(payload)),
            )
            self.conn.commit()
        return marker_id

    def insert_samples(self, rows: List[tuple]) -> None:
        if not rows:
            return
        with self.lock:
            self.conn.executemany(
                """
                INSERT INTO samples(stream, service_time_ns, device_time_ms, subject_id, run_id, trial_id, values_json, source_session_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            self.conn.commit()

    def mark_source_session(self, path: str, active: bool) -> None:
        ts = now_ns()
        with self.lock:
            if active:
                self.conn.execute("UPDATE source_sessions SET active=0")
            self.conn.execute(
                """
                INSERT INTO source_sessions(source_session_path, discovered_at_ns, last_seen_at_ns, active)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source_session_path) DO UPDATE SET last_seen_at_ns=excluded.last_seen_at_ns, active=excluded.active
                """,
                (path, ts, ts, 1 if active else 0),
            )
            self.conn.commit()

    def upsert_sample_file(
        self,
        run_id: str,
        subject_id: str,
        trial_id: Optional[str],
        file_path: str,
        started_at_ns: int,
        streams: List[str],
    ) -> None:
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO sample_files(run_id, subject_id, trial_id, file_path, row_count, started_at_ns, streams_json)
                VALUES (?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    subject_id=excluded.subject_id,
                    trial_id=excluded.trial_id,
                    file_path=excluded.file_path,
                    started_at_ns=excluded.started_at_ns,
                    streams_json=excluded.streams_json
                """,
                (run_id, subject_id, trial_id, file_path, started_at_ns, json_dumps(streams)),
            )
            self.conn.commit()

    def update_sample_file_progress(
        self,
        run_id: str,
        row_count: int,
        first_sample_ns: Optional[int],
        last_sample_ns: Optional[int],
        streams: List[str],
        ended_at_ns: Optional[int] = None,
    ) -> None:
        with self.lock:
            self.conn.execute(
                """
                UPDATE sample_files
                SET row_count=?,
                    first_sample_ns=?,
                    last_sample_ns=?,
                    streams_json=?,
                    ended_at_ns=COALESCE(?, ended_at_ns)
                WHERE run_id=?
                """,
                (row_count, first_sample_ns, last_sample_ns, json_dumps(streams), ended_at_ns, run_id),
            )
            self.conn.commit()

    def get_sample_files(
        self,
        subject_id: Optional[str] = None,
        run_id: Optional[str] = None,
        trial_id: Optional[str] = None,
    ) -> List[sqlite3.Row]:
        query = "SELECT * FROM sample_files WHERE 1=1"
        args: List[Any] = []
        if subject_id:
            query += " AND subject_id=?"
            args.append(subject_id)
        if run_id:
            query += " AND run_id=?"
            args.append(run_id)
        if trial_id:
            query += " AND trial_id=?"
            args.append(trial_id)
        query += " ORDER BY started_at_ns, run_id"
        with self.lock:
            return self.conn.execute(query, args).fetchall()

    def count_file_samples(
        self,
        subject_id: Optional[str] = None,
        run_id: Optional[str] = None,
        trial_id: Optional[str] = None,
    ) -> int:
        query = "SELECT COALESCE(SUM(row_count), 0) FROM sample_files WHERE 1=1"
        args: List[Any] = []
        if subject_id:
            query += " AND subject_id=?"
            args.append(subject_id)
        if run_id:
            query += " AND run_id=?"
            args.append(run_id)
        if trial_id:
            query += " AND trial_id=?"
            args.append(trial_id)
        with self.lock:
            return int(self.conn.execute(query, args).fetchone()[0] or 0)

    def count_samples(
        self,
        subject_id: Optional[str] = None,
        run_id: Optional[str] = None,
        trial_id: Optional[str] = None,
    ) -> int:
        query = "SELECT COUNT(*) FROM samples WHERE 1=1"
        args: List[Any] = []
        if subject_id:
            query += " AND subject_id=?"
            args.append(subject_id)
        if run_id:
            query += " AND run_id=?"
            args.append(run_id)
        if trial_id:
            query += " AND trial_id=?"
            args.append(trial_id)
        with self.lock:
            return int(self.conn.execute(query, args).fetchone()[0])

    def export_data(
        self,
        export_dir: str | os.PathLike[str],
        subject_id: Optional[str] = None,
        run_id: Optional[str] = None,
        trial_id: Optional[str] = None,
        sample_storage: str = "file",
    ) -> Dict[str, str]:
        export_dir = str(export_dir)
        os.makedirs(export_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        prefix = f"export_{stamp}_{uuid.uuid4().hex[:8]}"
        sample_path = os.path.abspath(os.path.join(export_dir, f"{prefix}_samples.csv"))
        marker_path = os.path.abspath(os.path.join(export_dir, f"{prefix}_markers.csv"))
        meta_path = os.path.abspath(os.path.join(export_dir, f"{prefix}_metadata.json"))

        where = ["1=1"]
        args: List[Any] = []
        if subject_id:
            where.append("subject_id=?")
            args.append(subject_id)
        if run_id:
            where.append("run_id=?")
            args.append(run_id)
        if trial_id:
            where.append("trial_id=?")
            args.append(trial_id)
        clause = " AND ".join(where)

        with self.lock:
            samples = []
            sample_files = self.get_sample_files(subject_id=subject_id, run_id=run_id, trial_id=trial_id)
            if sample_storage == "sqlite":
                samples = self.conn.execute(
                    f"""
                    SELECT stream, service_time_ns, device_time_ms, subject_id, run_id, trial_id, values_json, source_session_path
                    FROM samples WHERE {clause} ORDER BY service_time_ns
                    """,
                    args,
                ).fetchall()
            markers = self.conn.execute(
                f"""
                SELECT marker_id, subject_id, run_id, trial_id, name, service_time_ns, payload_json
                FROM markers WHERE {clause} ORDER BY service_time_ns
                """,
                args,
            ).fetchall()

        with open(sample_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(SAMPLE_HEADER)
            if sample_storage == "sqlite":
                for row in samples:
                    writer.writerow([row[key] for key in row.keys()])
            else:
                for sample_file in sample_files:
                    file_path = sample_file["file_path"]
                    if not os.path.exists(file_path):
                        continue
                    with open(file_path, "r", encoding="utf-8", newline="") as source:
                        reader = csv.reader(source)
                        next(reader, None)
                        for row in reader:
                            writer.writerow(row)

        with open(marker_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["marker_id", "subject_id", "run_id", "trial_id", "name", "service_time_ns", "payload_json"])
            for row in markers:
                writer.writerow([row[key] for key in row.keys()])

        metadata = {
            "created_at": iso_now(),
            "filters": {"subject_id": subject_id, "run_id": run_id, "trial_id": trial_id},
            "sample_storage": sample_storage,
            "sample_count": len(samples) if sample_storage == "sqlite" else sum(int(row["row_count"]) for row in sample_files),
            "sample_files": [dict(row) for row in sample_files],
            "marker_count": len(markers),
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        return {"samples_csv": sample_path, "markers_csv": marker_path, "metadata_json": meta_path}


def _safe_path_part(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in str(value))
    return safe.strip("._") or "unknown"


class SampleFileStore:
    def __init__(self, root_dir: str | os.PathLike[str], db: Database):
        self.root_dir = Path(root_dir)
        self.db = db
        self.lock = threading.RLock()
        self.file = None
        self.writer: Optional[csv.writer] = None
        self.active_run_id: Optional[str] = None
        self.active_subject_id: Optional[str] = None
        self.active_trial_id: Optional[str] = None
        self.active_path: Optional[str] = None
        self.row_count = 0
        self.first_sample_ns: Optional[int] = None
        self.last_sample_ns: Optional[int] = None
        self.streams: set[str] = set()

    def start_task(self, subject_id: str, run_id: str, trial_id: Optional[str] = None) -> str:
        with self.lock:
            self.close_active()
            task_dir = self.root_dir / _safe_path_part(subject_id) / _safe_path_part(run_id)
            task_dir.mkdir(parents=True, exist_ok=True)
            path = task_dir / "samples.csv"
            self.file = open(path, "w", newline="", encoding="utf-8")
            self.writer = csv.writer(self.file)
            self.writer.writerow(SAMPLE_HEADER)
            self.file.flush()
            self.active_run_id = run_id
            self.active_subject_id = subject_id
            self.active_trial_id = trial_id
            self.active_path = str(path.resolve())
            self.row_count = 0
            self.first_sample_ns = None
            self.last_sample_ns = None
            self.streams = set()
            self.db.upsert_sample_file(
                run_id=run_id,
                subject_id=subject_id,
                trial_id=trial_id,
                file_path=self.active_path,
                started_at_ns=now_ns(),
                streams=[],
            )
            return self.active_path

    def write_samples(self, rows: List[tuple]) -> None:
        if not rows:
            return
        with self.lock:
            if not self.writer or not self.active_run_id:
                return
            self.writer.writerows(rows)
            if self.file:
                self.file.flush()
            for row in rows:
                self.streams.add(str(row[0]))
                service_time_ns = int(row[1])
                if self.first_sample_ns is None or service_time_ns < self.first_sample_ns:
                    self.first_sample_ns = service_time_ns
                if self.last_sample_ns is None or service_time_ns > self.last_sample_ns:
                    self.last_sample_ns = service_time_ns
            self.row_count += len(rows)
            self.db.update_sample_file_progress(
                run_id=self.active_run_id,
                row_count=self.row_count,
                first_sample_ns=self.first_sample_ns,
                last_sample_ns=self.last_sample_ns,
                streams=sorted(self.streams),
            )

    def close_active(self) -> None:
        with self.lock:
            if self.active_run_id:
                self.db.update_sample_file_progress(
                    run_id=self.active_run_id,
                    row_count=self.row_count,
                    first_sample_ns=self.first_sample_ns,
                    last_sample_ns=self.last_sample_ns,
                    streams=sorted(self.streams),
                    ended_at_ns=now_ns(),
                )
            if self.file:
                try:
                    self.file.flush()
                    self.file.close()
                finally:
                    self.file = None
            self.writer = None
            self.active_run_id = None
            self.active_subject_id = None
            self.active_trial_id = None
            self.active_path = None
            self.row_count = 0
            self.first_sample_ns = None
            self.last_sample_ns = None
            self.streams = set()

    def snapshot(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "active_run_id": self.active_run_id,
                "active_subject_id": self.active_subject_id,
                "active_trial_id": self.active_trial_id,
                "active_file_path": self.active_path,
                "active_row_count": self.row_count,
                "first_sample_ns": self.first_sample_ns,
                "last_sample_ns": self.last_sample_ns,
                "streams": sorted(self.streams),
            }


class ExperimentState:
    def __init__(self, db: Database):
        self.db = db
        self.lock = threading.RLock()
        self.subject_id: Optional[str] = None
        self.subject_metadata: Dict[str, Any] = {}
        self.run_id: Optional[str] = None
        self.task_name: Optional[str] = None
        self.trial_id: Optional[str] = None
        self.trial_name: Optional[str] = None
        self.recent_markers: Deque[Dict[str, Any]] = deque(maxlen=100)

    def snapshot(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "mode": "experiment" if self.subject_id else "service_check",
                "subject_id": self.subject_id,
                "run_id": self.run_id,
                "task_name": self.task_name,
                "trial_id": self.trial_id,
                "trial_name": self.trial_name,
                "recent_markers": list(self.recent_markers),
            }

    def set_subject(self, subject_id: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        metadata = metadata or {}
        self.db.upsert_subject(subject_id, metadata)
        with self.lock:
            self.subject_id = subject_id
            self.subject_metadata = metadata
            self.run_id = None
            self.task_name = None
            self.trial_id = None
            self.trial_name = None
        return self.snapshot()

    def clear_subject(self) -> Dict[str, Any]:
        with self.lock:
            old_run_id = self.run_id
            old_trial_id = self.trial_id
            self.subject_id = None
            self.subject_metadata = {}
            self.run_id = None
            self.task_name = None
            self.trial_id = None
            self.trial_name = None
        if old_trial_id:
            self.db.end_trial(old_trial_id)
        if old_run_id:
            self.db.end_task(old_run_id)
        return self.snapshot()

    def start_task(self, task_name: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        metadata = metadata or {}
        with self.lock:
            if not self.subject_id:
                raise RuntimeError("Set subject before starting a physio task")
            old_run_id = self.run_id
            old_trial_id = self.trial_id
            subject_id = self.subject_id
        if old_trial_id:
            self.db.end_trial(old_trial_id)
        if old_run_id:
            self.db.end_task(old_run_id)
        run_id = self.db.create_task(subject_id, task_name, metadata)
        with self.lock:
            self.run_id = run_id
            self.task_name = task_name
            self.trial_id = None
            self.trial_name = None
        return self.snapshot()

    def stop_task(self) -> Dict[str, Any]:
        with self.lock:
            old_run_id = self.run_id
            old_trial_id = self.trial_id
            self.run_id = None
            self.task_name = None
            self.trial_id = None
            self.trial_name = None
        if old_trial_id:
            self.db.end_trial(old_trial_id)
        if old_run_id:
            self.db.end_task(old_run_id)
        return self.snapshot()

    def marker(self, name: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = payload or {}
        with self.lock:
            subject_id = self.subject_id
            run_id = self.run_id
            trial_id = self.trial_id
        marker_id = self.db.insert_marker(subject_id, run_id, trial_id, name, payload)
        marker = {
            "marker_id": marker_id,
            "name": name,
            "payload": payload,
            "service_time_ns": now_ns(),
            "subject_id": subject_id,
            "run_id": run_id,
            "trial_id": trial_id,
        }
        with self.lock:
            self.recent_markers.append(marker)
        return marker

    def context_for_sample(self) -> Dict[str, Optional[str]]:
        with self.lock:
            return {
                "subject_id": self.subject_id,
                "run_id": self.run_id,
                "trial_id": self.trial_id,
            }


class Collector:
    def __init__(
        self,
        root: str,
        streams: List[str],
        db: Database,
        state: ExperimentState,
        poll: float = 0.05,
        sample_storage: str = "file",
        sample_file_store: Optional[SampleFileStore] = None,
    ):
        self.root = root
        self.streams = streams
        self.db = db
        self.state = state
        self.poll = poll
        self.sample_storage = sample_storage
        self.sample_file_store = sample_file_store
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.current_session: Optional[str] = None
        self.project: Optional[str] = None
        self.tails: Dict[str, TailState] = {}
        self.latest: Dict[str, Dict[str, Any]] = {}
        self.recent_points: Dict[str, Deque[Dict[str, Any]]] = {stream: deque(maxlen=500) for stream in streams}
        self.seen_times: Dict[str, Deque[int]] = {stream: deque(maxlen=2000) for stream in streams}
        self.warnings: List[str] = []

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.run, daemon=True, name="physio-vendor-csv-collector")
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)

    def snapshot(self) -> Dict[str, Any]:
        cutoff = now_ns() - 1_000_000_000
        with self.lock:
            stream_status = {}
            live_count = 0
            for stream in self.streams:
                times = self.seen_times.get(stream, deque())
                hz = sum(1 for item in times if item >= cutoff)
                live_count += hz
                last = self.latest.get(stream)
                stream_status[stream] = {
                    "hz": hz,
                    "last_seen_ns": last.get("service_time_ns") if last else None,
                    "last_value": last.get("values") if last else None,
                    "points": list(self.recent_points.get(stream, deque())),
                }
            warnings = list(self.warnings)
            if self.current_session and live_count == 0:
                warnings.append(
                    "No live samples in the current vendor CSV session. Check that vendor acquisition is started, not just connected."
                )
            return {
                "vendor_root": self.root,
                "project": self.project,
                "available_projects": self.available_projects(),
                "source_session_path": self.current_session,
                "streams": stream_status,
                "warnings": warnings,
            }

    def available_projects(self) -> List[str]:
        try:
            return sorted(name for name in os.listdir(self.root) if os.path.isdir(os.path.join(self.root, name)))
        except OSError:
            return []

    def set_project(self, project: Optional[str]) -> None:
        if project:
            project_path = os.path.join(self.root, project)
            if not os.path.isdir(project_path):
                raise RuntimeError(f"Unknown project: {project}")
        with self.lock:
            self.project = project
            self.current_session = None
            self.tails = {}
            self.latest = {}
            self.recent_points = {stream: deque(maxlen=500) for stream in self.streams}
            self.seen_times = {stream: deque(maxlen=2000) for stream in self.streams}

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.ensure_session()
                self.poll_once()
            except Exception as exc:
                with self.lock:
                    self.warnings = [f"collector error: {exc}"]
            time.sleep(self.poll)

    def ensure_session(self) -> None:
        search_root = os.path.join(self.root, self.project) if self.project else self.root
        session = latest_vendor_session(search_root)
        if not session:
            with self.lock:
                self.warnings = [f"No vendor session under {search_root}"]
            return
        if session == self.current_session:
            self.db.mark_source_session(session, active=True)
            return

        tails: Dict[str, TailState] = {}
        for stream in self.streams:
            path = os.path.join(session, f"{stream}.csv")
            if not os.path.exists(path):
                continue
            labels = read_header(path)
            tails[stream] = TailState(stream=stream, path=path, labels=labels, position=os.path.getsize(path))

        with self.lock:
            self.current_session = session
            self.tails = tails
            self.latest = {}
            self.recent_points = {stream: deque(maxlen=500) for stream in self.streams}
            self.seen_times = {stream: deque(maxlen=2000) for stream in self.streams}
            self.warnings = [] if tails else [f"No known CSV files in {session}"]
            for tail in tails.values():
                for event in self.load_recent_points(tail, limit=300):
                    self.latest[tail.stream] = event
                    self.recent_points[tail.stream].append(event)
        self.db.mark_source_session(session, active=True)

    def load_recent_points(self, tail: TailState, limit: int) -> List[Dict[str, Any]]:
        try:
            with open(tail.path, "r", encoding="utf-8-sig", newline="") as f:
                lines = f.readlines()
        except OSError:
            return []
        rows = [parse_csv_line(line) for line in lines[1:]]
        valid_rows = [row for row in rows if row and row != tail.labels]
        return [event for row in valid_rows[-limit:] if (event := self.row_to_event(tail, row))]

    def poll_once(self) -> None:
        with self.lock:
            tails = list(self.tails.values())
            session = self.current_session
        if not session:
            return

        db_rows: List[tuple] = []
        for tail in tails:
            events = self.read_tail(tail)
            for event in events:
                service_time_ns = event["service_time_ns"]
                with self.lock:
                    self.latest[tail.stream] = event
                    self.recent_points[tail.stream].append(event)
                    self.seen_times[tail.stream].append(service_time_ns)

                ctx = self.state.context_for_sample()
                if ctx["subject_id"]:
                    db_rows.append(
                        (
                            tail.stream,
                            service_time_ns,
                            event.get("device_time_ms"),
                            ctx["subject_id"],
                            ctx["run_id"],
                            ctx["trial_id"],
                            json_dumps(event["values"]),
                            session,
                        )
                    )
        if self.sample_storage == "sqlite":
            self.db.insert_samples(db_rows)
        elif self.sample_file_store:
            self.sample_file_store.write_samples(db_rows)

    def read_tail(self, tail: TailState) -> List[Dict[str, Any]]:
        if not os.path.exists(tail.path):
            return []
        size = os.path.getsize(tail.path)
        if size < tail.position:
            tail.position = 0

        events: List[Dict[str, Any]] = []
        with open(tail.path, "r", encoding="utf-8-sig", newline="") as f:
            f.seek(tail.position)
            if tail.position == 0:
                f.readline()
            while True:
                line = f.readline()
                if not line:
                    break
                row = parse_csv_line(line)
                if not row or row == tail.labels:
                    continue
                event = self.row_to_event(tail, row)
                if event:
                    events.append(event)
            tail.position = f.tell()
        return events

    def row_to_event(self, tail: TailState, row: List[str]) -> Optional[Dict[str, Any]]:
        if not row:
            return None
        values: Dict[str, Any] = {}
        for label, raw in zip(tail.labels[1:], row[1:]):
            try:
                values[label] = float(raw)
            except ValueError:
                values[label] = raw
        try:
            device_time_ms: Optional[float] = float(row[0])
        except ValueError:
            device_time_ms = None
        return {
            "stream": tail.stream,
            "service_time_ns": now_ns(),
            "device_time_ms": device_time_ms,
            "values": values,
        }


class PhysioService:
    def __init__(
        self,
        vendor_root: str = DEFAULT_VENDOR_ROOT,
        db_path: str | os.PathLike[str] = DEFAULT_DB_PATH,
        export_dir: str | os.PathLike[str] = DEFAULT_EXPORT_DIR,
        raw_dir: str | os.PathLike[str] = DEFAULT_RAW_DIR,
        streams: Optional[List[str]] = None,
        sample_storage: str = "file",
    ):
        self.vendor_root = vendor_root
        self.db_path = str(db_path)
        self.export_dir = str(export_dir)
        self.raw_dir = str(raw_dir)
        self.sample_storage = sample_storage if sample_storage in {"file", "sqlite"} else "file"
        self.streams = streams or list(DEFAULT_STREAMS)
        self.enabled = True
        self.running = False
        self.error: Optional[str] = None
        self.db = Database(self.db_path)
        self.state = ExperimentState(self.db)
        self.sample_file_store = SampleFileStore(self.raw_dir, self.db)
        self.collector = Collector(
            vendor_root,
            self.streams,
            self.db,
            self.state,
            sample_storage=self.sample_storage,
            sample_file_store=self.sample_file_store,
        )

    def start(self) -> None:
        self.collector.start()
        self.running = True
        self.error = None

    def stop(self) -> None:
        try:
            self.sample_file_store.close_active()
            self.state.clear_subject()
        except Exception:
            pass
        self.collector.stop()
        self.db.close()
        self.running = False

    def set_subject(self, subject_id: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.state.set_subject(subject_id, metadata)

    def clear_subject(self) -> Dict[str, Any]:
        self.sample_file_store.close_active()
        return self.state.clear_subject()

    def start_task(self, task_name: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        snapshot = self.state.start_task(task_name, metadata)
        if self.sample_storage == "file" and snapshot.get("subject_id") and snapshot.get("run_id"):
            self.sample_file_store.start_task(
                subject_id=str(snapshot["subject_id"]),
                run_id=str(snapshot["run_id"]),
                trial_id=snapshot.get("trial_id"),
            )
        return snapshot

    def stop_task(self) -> Dict[str, Any]:
        self.sample_file_store.close_active()
        return self.state.stop_task()

    def marker(self, name: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.state.marker(name, payload)

    def export_data(
        self,
        subject_id: Optional[str] = None,
        run_id: Optional[str] = None,
        trial_id: Optional[str] = None,
    ) -> Dict[str, str]:
        return self.db.export_data(
            self.export_dir,
            subject_id=subject_id,
            run_id=run_id,
            trial_id=trial_id,
            sample_storage=self.sample_storage,
        )

    def status_payload(self) -> Dict[str, Any]:
        state_snapshot = self.state.snapshot()
        collector_snapshot = self.collector.snapshot()
        return {
            "ok": True,
            "enabled": self.enabled,
            "running": self.running,
            "error": self.error,
            "time_ns": now_ns(),
            "state": state_snapshot,
            "collector": collector_snapshot,
            "db_path": self.db_path,
            "export_dir": self.export_dir,
            "raw_dir": self.raw_dir,
            "sample_storage": self.sample_storage,
            "sample_file": self.sample_file_store.snapshot(),
            "formal_sample_count": (
                self.db.count_samples(subject_id=state_snapshot.get("subject_id"))
                if self.sample_storage == "sqlite" and state_snapshot.get("subject_id")
                else self.db.count_file_samples(subject_id=state_snapshot.get("subject_id"))
                if state_snapshot.get("subject_id")
                else 0
            ),
        }


def _env_enabled(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _env_streams() -> List[str]:
    raw = os.environ.get("PHYSIO_STREAMS")
    if not raw:
        return list(DEFAULT_STREAMS)
    streams = [part.strip() for part in raw.split(",") if part.strip()]
    return streams or list(DEFAULT_STREAMS)


def create_physio_service_from_env() -> Optional[PhysioService]:
    if not _env_enabled("PHYSIO_RING_ENABLED", default=True):
        return None
    vendor_root = os.environ.get("PHYSIO_VENDOR_ROOT", DEFAULT_VENDOR_ROOT)
    db_path = os.environ.get("PHYSIO_DB_PATH", str(DEFAULT_DB_PATH))
    export_dir = os.environ.get("PHYSIO_EXPORT_DIR", str(DEFAULT_EXPORT_DIR))
    raw_dir = os.environ.get("PHYSIO_RAW_DIR", str(DEFAULT_RAW_DIR))
    sample_storage = os.environ.get("PHYSIO_SAMPLE_STORAGE", "file").strip().lower()
    return PhysioService(
        vendor_root=vendor_root,
        db_path=db_path,
        export_dir=export_dir,
        raw_dir=raw_dir,
        streams=_env_streams(),
        sample_storage=sample_storage,
    )
