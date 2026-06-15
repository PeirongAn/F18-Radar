from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


def now_ns() -> int:
    return time.time_ns()


def json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


class ExternalCollectorDatabase:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.closed = False
        self.init_schema()

    def init_schema(self) -> None:
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS collector_task_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    collector_name TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    subject_id TEXT,
                    task_name TEXT,
                    started_at_ns INTEGER NOT NULL,
                    ended_at_ns INTEGER,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    start_response_json TEXT,
                    stop_response_json TEXT,
                    last_status_json TEXT,
                    last_error TEXT,
                    UNIQUE(provider, task_id)
                );
                CREATE TABLE IF NOT EXISTS collector_events (
                    event_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    collector_name TEXT NOT NULL,
                    task_id TEXT,
                    subject_id TEXT,
                    name TEXT NOT NULL,
                    service_time_ns INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    response_json TEXT,
                    ok INTEGER NOT NULL DEFAULT 1,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS collector_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    collector_name TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    file_url TEXT NOT NULL,
                    discovered_at_ns INTEGER NOT NULL,
                    response_json TEXT,
                    UNIQUE(provider, task_id, filename)
                );
                CREATE INDEX IF NOT EXISTS idx_collector_task_runs_task
                    ON collector_task_runs(task_id, provider);
                CREATE INDEX IF NOT EXISTS idx_collector_events_task
                    ON collector_events(task_id, provider, service_time_ns);
                CREATE INDEX IF NOT EXISTS idx_collector_files_task
                    ON collector_files(task_id, provider);
                """
            )
            self.conn.commit()

    def close(self) -> None:
        with self.lock:
            if self.closed:
                return
            try:
                self.conn.commit()
            except sqlite3.Error:
                pass
            for sql in ("PRAGMA wal_checkpoint(TRUNCATE)", "PRAGMA journal_mode=DELETE"):
                try:
                    self.conn.execute(sql).fetchall()
                except sqlite3.Error:
                    pass
            self.conn.close()
            self.closed = True

    def upsert_task_start(
        self,
        provider: str,
        collector_name: str,
        task_id: str,
        subject_id: str,
        task_name: str,
        metadata: Dict[str, Any],
        response: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO collector_task_runs (
                    provider, collector_name, task_id, subject_id, task_name,
                    started_at_ns, status, metadata_json, start_response_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, task_id) DO UPDATE SET
                    collector_name=excluded.collector_name,
                    subject_id=excluded.subject_id,
                    task_name=excluded.task_name,
                    status='active',
                    metadata_json=excluded.metadata_json,
                    start_response_json=excluded.start_response_json,
                    last_error=NULL
                """,
                (
                    provider,
                    collector_name,
                    str(task_id),
                    subject_id,
                    task_name,
                    now_ns(),
                    "active",
                    json_dumps(metadata),
                    json_dumps(response),
                ),
            )
            self.conn.commit()

    def record_event(
        self,
        provider: str,
        collector_name: str,
        task_id: Optional[str],
        subject_id: Optional[str],
        name: str,
        payload: Optional[Dict[str, Any]] = None,
        response: Optional[Dict[str, Any]] = None,
        ok: bool = True,
        error: Optional[str] = None,
    ) -> str:
        event_id = uuid.uuid4().hex
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO collector_events (
                    event_id, provider, collector_name, task_id, subject_id, name,
                    service_time_ns, payload_json, response_json, ok, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    provider,
                    collector_name,
                    str(task_id) if task_id is not None else None,
                    subject_id,
                    name,
                    now_ns(),
                    json_dumps(payload),
                    json_dumps(response),
                    1 if ok else 0,
                    error,
                ),
            )
            self.conn.commit()
        return event_id

    def finish_task(
        self,
        provider: str,
        task_id: str,
        status: str,
        response: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        with self.lock:
            self.conn.execute(
                """
                UPDATE collector_task_runs
                SET ended_at_ns=?,
                    status=?,
                    stop_response_json=?,
                    last_error=?
                WHERE provider=? AND task_id=?
                """,
                (now_ns(), status, json_dumps(response), error, provider, str(task_id)),
            )
            self.conn.commit()

    def update_task_status(
        self,
        provider: str,
        task_id: str,
        status: Dict[str, Any],
        error: Optional[str] = None,
    ) -> None:
        with self.lock:
            self.conn.execute(
                """
                UPDATE collector_task_runs
                SET last_status_json=?,
                    last_error=?
                WHERE provider=? AND task_id=?
                """,
                (json_dumps(status), error, provider, str(task_id)),
            )
            self.conn.commit()

    def upsert_files(
        self,
        provider: str,
        collector_name: str,
        task_id: str,
        files: List[str],
        base_file_url: str,
        response: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self.lock:
            for filename in files:
                safe_name = str(filename)
                self.conn.execute(
                    """
                    INSERT INTO collector_files (
                        provider, collector_name, task_id, filename, file_url,
                        discovered_at_ns, response_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(provider, task_id, filename) DO UPDATE SET
                        file_url=excluded.file_url,
                        discovered_at_ns=excluded.discovered_at_ns,
                        response_json=excluded.response_json
                    """,
                    (
                        provider,
                        collector_name,
                        str(task_id),
                        safe_name,
                        f"{base_file_url.rstrip('/')}/{safe_name}",
                        now_ns(),
                        json_dumps(response),
                    ),
                )
            self.conn.commit()

    def task_files(self, provider: Optional[str] = None, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
        where = ["1=1"]
        args: List[Any] = []
        if provider:
            where.append("provider=?")
            args.append(provider)
        if task_id:
            where.append("task_id=?")
            args.append(str(task_id))
        with self.lock:
            rows = self.conn.execute(
                f"""
                SELECT provider, collector_name, task_id, filename, file_url, discovered_at_ns
                FROM collector_files
                WHERE {' AND '.join(where)}
                ORDER BY discovered_at_ns, filename
                """,
                args,
            ).fetchall()
        return [dict(row) for row in rows]
