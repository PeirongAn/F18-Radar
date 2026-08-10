from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .storage import ExternalCollectorDatabase
from runtime_paths import DATA_DIR, RUNTIME_HOME

JsonDict = Dict[str, Any]
SERVER_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = DATA_DIR / "external_collectors" / "collector_records.sqlite3"


def _env_enabled(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def _env_list(name: str, default: str = "") -> List[str]:
    raw = os.environ.get(name, default)
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


class WecareCollectorAdapter:
    def __init__(
        self,
        name: str = "wecare",
        base_url: str = "http://127.0.0.1:8787",
        provider: str = "wecare",
        marker_type: Optional[int] = None,
        timeout: float = 1.5,
        transport: Optional[Callable[[str, str, Optional[JsonDict], float], JsonDict]] = None,
        logger: Any = None,
        db: Optional[ExternalCollectorDatabase] = None,
    ):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.provider = provider.strip("/") or "wecare"
        self.marker_type = marker_type
        self.timeout = max(0.1, float(timeout))
        self.transport = transport or self._request_json
        self.logger = logger
        self.db = db
        self.active_task_id: Optional[str] = None
        self.active_subject_id: Optional[str] = None
        self.last_error: Optional[str] = None
        self.last_status: Optional[JsonDict] = None
        self.last_event_at_ms: Optional[int] = None

    def start(self) -> None:
        self.last_error = None

    def stop(self) -> None:
        self.active_task_id = None
        self.active_subject_id = None

    def clear_subject(self) -> None:
        self.active_subject_id = None

    def status_payload(self) -> JsonDict:
        try:
            response = self._send("GET", f"{self.base_url}/api/v1/status", None)
            self.last_status = response
            self.last_error = None
            provider_status = ((response or {}).get("providers") or {}).get(self.provider) or {}
            return {
                "ok": bool((response or {}).get("ok", True)),
                "name": self.name,
                "provider": self.provider,
                "base_url": self.base_url,
                "connected": bool(provider_status.get("connected") or provider_status.get("mqtt_connected")),
                "state": provider_status.get("state"),
                "active_task_id": provider_status.get("active_task_id") or self.active_task_id,
                "row_count": provider_status.get("row_count"),
                "data_types": provider_status.get("data_types") or [],
                "warnings": provider_status.get("warnings") or [],
                "last_error": provider_status.get("last_error") or self.last_error,
                "raw": provider_status,
            }
        except Exception as exc:
            self.last_error = str(exc)
            return self._error_status(str(exc))

    def start_task(
        self,
        task_name: str,
        subject_id: str,
        task_id: str,
        metadata: Optional[JsonDict] = None,
    ) -> JsonDict:
        task_id = str(task_id).strip()
        if not task_id:
            raise ValueError("external collector task_id is required")
        body = {
            "subject_id": str(subject_id or ""),
            "scenario": str(task_name or ""),
            "metadata": metadata or {},
        }
        path = f"{self.base_url}/api/v1/providers/{self.provider}/tasks/{_quote_path(task_id)}/start"
        response = self._send("POST", path, body)
        if response.get("ok") is False:
            if self.db is not None:
                self.db.record_event(
                    self.provider,
                    self.name,
                    task_id,
                    str(subject_id or ""),
                    "start_task",
                    body,
                    response=response,
                    ok=False,
                    error=str(response.get("error") or response),
                )
            raise RuntimeError(str(response.get("error") or response))
        self.active_task_id = task_id
        self.active_subject_id = str(subject_id or "")
        self.last_error = None
        self.last_event_at_ms = int(time.time() * 1000)
        if self.db is not None:
            self.db.upsert_task_start(
                self.provider,
                self.name,
                task_id,
                self.active_subject_id,
                str(task_name or ""),
                metadata or {},
                response=response,
            )
            self.db.record_event(
                self.provider,
                self.name,
                task_id,
                self.active_subject_id,
                "start_task",
                body,
                response=response,
            )
        return response

    def marker(self, name: str, payload: Optional[JsonDict] = None) -> JsonDict:
        if not self.active_task_id:
            return {"ok": False, "skipped": True, "reason": "no_active_task"}
        body = {"name": str(name), "payload": payload or {}}
        if self.marker_type is not None:
            body["type"] = self.marker_type
        path = (
            f"{self.base_url}/api/v1/providers/{self.provider}/tasks/"
            f"{_quote_path(self.active_task_id)}/markers"
        )
        response = self._send("POST", path, body)
        if response.get("ok") is False:
            if self.db is not None:
                self.db.record_event(
                    self.provider,
                    self.name,
                    self.active_task_id,
                    self.active_subject_id,
                    str(name),
                    payload or {},
                    response=response,
                    ok=False,
                    error=str(response.get("error") or response),
                )
            raise RuntimeError(str(response.get("error") or response))
        self.last_error = None
        self.last_event_at_ms = int(time.time() * 1000)
        if self.db is not None:
            self.db.record_event(
                self.provider,
                self.name,
                self.active_task_id,
                self.active_subject_id,
                str(name),
                payload or {},
                response=response,
            )
        return response

    def stop_task(self, task_id: Optional[str] = None) -> JsonDict:
        resolved = str(task_id or self.active_task_id or "").strip()
        if not resolved:
            return {"ok": False, "skipped": True, "reason": "no_active_task"}
        path = f"{self.base_url}/api/v1/providers/{self.provider}/tasks/{_quote_path(resolved)}/stop"
        response = self._send("POST", path, None)
        if response.get("ok") is False:
            if self.db is not None:
                self.db.record_event(
                    self.provider,
                    self.name,
                    resolved,
                    self.active_subject_id,
                    "stop_task",
                    {},
                    response=response,
                    ok=False,
                    error=str(response.get("error") or response),
                )
                self.db.finish_task(
                    self.provider,
                    resolved,
                    "stop_failed",
                    response=response,
                    error=str(response.get("error") or response),
                )
            raise RuntimeError(str(response.get("error") or response))
        if self.db is not None:
            self.db.record_event(
                self.provider,
                self.name,
                resolved,
                self.active_subject_id,
                "stop_task",
                {},
                response=response,
            )
            self.db.finish_task(self.provider, resolved, "completed", response=response)
            try:
                self.refresh_task_files(resolved)
            except Exception as exc:
                self.db.record_event(
                    self.provider,
                    self.name,
                    resolved,
                    self.active_subject_id,
                    "refresh_task_files",
                    {},
                    ok=False,
                    error=str(exc),
                )
                if self.logger is not None:
                    self.logger.warning(
                        "external collector file refresh failed name=%s provider=%s task_id=%s error=%s",
                        self.name,
                        self.provider,
                        resolved,
                        exc,
                        exc_info=True,
                    )
        if self.active_task_id == resolved:
            self.active_task_id = None
        self.last_error = None
        self.last_event_at_ms = int(time.time() * 1000)
        return response

    def refresh_task_files(self, task_id: str) -> JsonDict:
        task_id = str(task_id).strip()
        if not task_id:
            return {"ok": False, "files": [], "error": "invalid_task_id"}
        path = f"{self.base_url}/api/v1/providers/{self.provider}/tasks/{_quote_path(task_id)}/files"
        response = self._send("GET", path, None)
        files = [str(item) for item in response.get("files") or []]
        if self.db is not None:
            self.db.update_task_status(self.provider, task_id, {"files_response": response})
            self.db.upsert_files(
                self.provider,
                self.name,
                task_id,
                files,
                f"{self.base_url}/api/v1/providers/{self.provider}/tasks/{_quote_path(task_id)}/files",
                response=response,
            )
        return response

    def _error_status(self, message: str) -> JsonDict:
        return {
            "ok": False,
            "name": self.name,
            "provider": self.provider,
            "base_url": self.base_url,
            "connected": False,
            "state": "unavailable",
            "active_task_id": self.active_task_id,
            "row_count": None,
            "data_types": [],
            "warnings": [message],
            "last_error": message,
            "raw": {},
        }

    def _send(self, method: str, url: str, body: Optional[JsonDict]) -> JsonDict:
        if self.logger is not None:
            self.logger.info(
                "external collector request name=%s provider=%s method=%s url=%s body=%s",
                self.name,
                self.provider,
                method,
                url,
                _summarize_body(body),
            )
        try:
            response = self.transport(method, url, body, self.timeout)
        except Exception as exc:
            if self.logger is not None:
                self.logger.warning(
                    "external collector request failed name=%s provider=%s method=%s url=%s error=%s",
                    self.name,
                    self.provider,
                    method,
                    url,
                    exc,
                    exc_info=True,
                )
            raise
        if self.logger is not None:
            self.logger.info(
                "external collector response name=%s provider=%s method=%s url=%s ok=%s status=%s error=%s",
                self.name,
                self.provider,
                method,
                url,
                response.get("ok"),
                response.get("status"),
                response.get("error") or response.get("last_error"),
            )
        return response

    @staticmethod
    def _request_json(method: str, url: str, body: Optional[JsonDict], timeout: float) -> JsonDict:
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                payload = {"error": raw or str(exc)}
            payload.setdefault("ok", False)
            payload.setdefault("status", exc.code)
            return payload
        return json.loads(raw) if raw else {}


class ExternalCollectorManager:
    def __init__(
        self,
        adapters: Optional[List[WecareCollectorAdapter]] = None,
        logger: Any = None,
        db: Optional[ExternalCollectorDatabase] = None,
    ):
        self.adapters = adapters or []
        self.logger = logger
        self.db = db
        self.enabled = bool(self.adapters)

    def start(self) -> None:
        for adapter in self.adapters:
            self._call(adapter, "start")

    def stop(self) -> None:
        for adapter in self.adapters:
            self._call(adapter, "stop")
        if self.db is not None:
            self.db.close()

    def clear_subject(self) -> None:
        for adapter in self.adapters:
            self._call(adapter, "clear_subject")

    def start_task(
        self,
        task_name: str,
        subject_id: str,
        task_id: str,
        metadata: Optional[JsonDict] = None,
    ) -> None:
        for adapter in self.adapters:
            self._call(adapter, "start_task", task_name, subject_id, task_id, metadata or {})

    def marker(self, name: str, payload: Optional[JsonDict] = None) -> None:
        for adapter in self.adapters:
            self._call(adapter, "marker", name, payload or {})

    def stop_task(self, task_id: Optional[str] = None) -> None:
        for adapter in self.adapters:
            self._call(adapter, "stop_task", task_id)

    def status_payload(self) -> JsonDict:
        providers = {}
        for adapter in self.adapters:
            providers[adapter.name] = adapter.status_payload()
        return {
            "ok": all(status.get("ok", False) for status in providers.values()) if providers else True,
            "enabled": self.enabled,
            "db_path": self.db.path if self.db is not None else None,
            "providers": providers,
        }

    def task_files(self, provider: Optional[str] = None, task_id: Optional[str] = None) -> List[JsonDict]:
        if self.db is None:
            return []
        return self.db.task_files(provider=provider, task_id=task_id)

    def _call(self, adapter: WecareCollectorAdapter, method_name: str, *args) -> Optional[Any]:
        try:
            method = getattr(adapter, method_name)
            return method(*args)
        except Exception as exc:
            adapter.last_error = str(exc)
            if self.logger is not None:
                self.logger.warning(
                    "external collector %s.%s failed: %s",
                    adapter.name,
                    method_name,
                    exc,
                    exc_info=True,
                )
            return None


def create_external_collector_manager_from_env(logger: Any = None) -> Optional[ExternalCollectorManager]:
    if not _env_enabled("EXTERNAL_COLLECTORS_ENABLED", default=False):
        return None

    names = _env_list("EXTERNAL_COLLECTORS", "wecare,prime")
    db = ExternalCollectorDatabase(_resolve_db_path(os.environ.get("EXTERNAL_COLLECTORS_DB_PATH")))
    adapters: List[WecareCollectorAdapter] = []
    for name in names:
        prefix = f"{name.upper()}_COLLECTOR"
        if not _env_enabled(f"{prefix}_ENABLED", default=True):
            continue
        if name == "wecare":
            adapters.append(
                WecareCollectorAdapter(
                    name=name,
                    base_url=os.environ.get(f"{prefix}_BASE_URL", "http://127.0.0.1:8787"),
                    provider=os.environ.get(f"{prefix}_PROVIDER", "wecare"),
                    timeout=float(os.environ.get(f"{prefix}_TIMEOUT_SEC", "1.5")),
                    logger=logger,
                    db=db,
                )
            )
        elif name == "prime":
            adapters.append(
                WecareCollectorAdapter(
                    name=name,
                    base_url=os.environ.get(f"{prefix}_BASE_URL", "http://127.0.0.1:8789"),
                    provider=os.environ.get(f"{prefix}_PROVIDER", "prime"),
                    marker_type=int(os.environ.get(f"{prefix}_MARKER_TYPE", "1")),
                    timeout=float(os.environ.get(f"{prefix}_TIMEOUT_SEC", "1.5")),
                    logger=logger,
                    db=db,
                )
            )
        elif logger is not None:
            logger.warning("unknown external collector configured: %s", name)

    if not adapters:
        db.close()
        return None
    return ExternalCollectorManager(adapters, logger=logger, db=db)


def _quote_path(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def _resolve_db_path(raw_path: Optional[str]) -> str:
    if not raw_path or not str(raw_path).strip():
        return str(DEFAULT_DB_PATH)
    path = Path(str(raw_path).strip())
    if path.is_absolute():
        return str(path)
    parts = path.parts
    if parts and parts[0].lower() == "server":
        return str(RUNTIME_HOME / path)
    return str(SERVER_DIR / path)


def _summarize_body(body: Optional[JsonDict]) -> JsonDict:
    if not body:
        return {}
    summary: JsonDict = {}
    for key in ("subject_id", "scenario", "name", "type"):
        if key in body:
            summary[key] = body.get(key)
    payload = body.get("payload")
    if isinstance(payload, dict):
        summary["payload_keys"] = sorted(str(key) for key in payload.keys())
        for key in ("source", "f18_task_id", "task_id", "task_type", "event_type", "user_id"):
            if key in payload:
                summary[f"payload.{key}"] = payload.get(key)
    metadata = body.get("metadata")
    if isinstance(metadata, dict):
        summary["metadata_keys"] = sorted(str(key) for key in metadata.keys())
        for key in ("source", "f18_task_id", "task_type", "user_id", "event_owner"):
            if key in metadata:
                summary[f"metadata.{key}"] = metadata.get(key)
    return summary
