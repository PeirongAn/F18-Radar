import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from collectors.external import (
    ExternalCollectorManager,
    WecareCollectorAdapter,
    create_external_collector_manager_from_env,
    _resolve_db_path,
)
from collectors.storage import ExternalCollectorDatabase


def test_wecare_adapter_start_marker_stop_requests():
    calls = []

    def transport(method, url, body, timeout):
        calls.append((method, url, body, timeout))
        if method == "GET":
            return {
                "ok": True,
                "providers": {
                    "wecare": {
                        "state": "ready",
                        "connected": True,
                        "active_task_id": None,
                        "row_count": 12,
                        "data_types": ["imu"],
                        "warnings": [],
                    }
                },
            }
        return {"ok": True}

    adapter = WecareCollectorAdapter(base_url="http://collector.test", transport=transport)

    status = adapter.status_payload()
    adapter.start_task("RADAR_TARGETING", "S001", "42", {"source": "F18-Radar"})
    adapter.marker("task_start", {"f18_task_id": 42})
    adapter.stop_task()

    assert status["connected"] is True
    assert calls[1][0] == "POST"
    assert calls[1][1] == "http://collector.test/api/v1/providers/wecare/tasks/42/start"
    assert calls[1][2]["subject_id"] == "S001"
    assert calls[1][2]["scenario"] == "RADAR_TARGETING"
    assert calls[1][2]["metadata"]["source"] == "F18-Radar"
    assert calls[2][1] == "http://collector.test/api/v1/providers/wecare/tasks/42/markers"
    assert calls[2][2]["name"] == "task_start"
    assert calls[3][1] == "http://collector.test/api/v1/providers/wecare/tasks/42/stop"


def test_wecare_adapter_status_reports_unreachable_service():
    def transport(method, url, body, timeout):
        raise OSError("collector down")

    adapter = WecareCollectorAdapter(base_url="http://collector.test", transport=transport)

    status = adapter.status_payload()

    assert status["ok"] is False
    assert status["state"] == "unavailable"
    assert status["last_error"] == "collector down"


def test_wecare_adapter_records_task_and_files_in_local_db(tmp_path):
    db = ExternalCollectorDatabase(tmp_path / "collector_records.sqlite3")

    def transport(method, url, body, timeout):
        if url.endswith("/files"):
            return {"ok": True, "files": ["meta.json", "events.jsonl", "all_data.csv"]}
        return {"ok": True}

    adapter = WecareCollectorAdapter(base_url="http://collector.test", transport=transport, db=db)

    adapter.start_task("RADAR_TARGETING", "S001", "42", {"source": "F18-Radar"})
    adapter.marker("task_start", {"f18_task_id": 42})
    adapter.stop_task()

    files = db.task_files(provider="wecare", task_id="42")
    db.close()

    by_name = {item["filename"]: item for item in files}
    assert sorted(by_name) == ["all_data.csv", "events.jsonl", "meta.json"]
    assert by_name["all_data.csv"]["file_url"] == (
        "http://collector.test/api/v1/providers/wecare/tasks/42/files/all_data.csv"
    )


def test_prime_adapter_uses_prime_provider_marker_type_and_mqtt_status():
    calls = []

    def transport(method, url, body, timeout):
        calls.append((method, url, body, timeout))
        if method == "GET" and url.endswith("/api/v1/status"):
            return {
                "ok": True,
                "providers": {
                    "prime": {
                        "state": "ready",
                        "device_id": "4049972242",
                        "mqtt_connected": True,
                        "active_task_id": None,
                        "row_count": 0,
                        "data_types": [],
                    }
                },
            }
        if method == "GET" and url.endswith("/files"):
            return {"ok": True, "files": ["events.jsonl", "meta.json"]}
        return {"ok": True}

    adapter = WecareCollectorAdapter(
        name="prime",
        base_url="http://prime.test",
        provider="prime",
        marker_type=1,
        transport=transport,
    )

    status = adapter.status_payload()
    adapter.start_task("RADAR_TARGETING", "S001", "42", {})
    adapter.marker("task_start", {"f18_task_id": 42})

    assert status["connected"] is True
    assert calls[1][1] == "http://prime.test/api/v1/providers/prime/tasks/42/start"
    assert calls[2][1] == "http://prime.test/api/v1/providers/prime/tasks/42/markers"
    assert calls[2][2]["name"] == "task_start"
    assert calls[2][2]["type"] == 1


def test_external_collector_manager_keeps_going_after_adapter_failure():
    class FakeAdapter:
        def __init__(self, name, fail=False):
            self.name = name
            self.fail = fail
            self.calls = []
            self.last_error = None

        def start_task(self, *args):
            self.calls.append(args)
            if self.fail:
                raise RuntimeError("boom")

        def status_payload(self):
            return {"ok": self.last_error is None, "last_error": self.last_error}

    bad = FakeAdapter("bad", fail=True)
    good = FakeAdapter("good")
    manager = ExternalCollectorManager([bad, good])

    manager.start_task("RADAR_TARGETING", "S001", "42", {})

    assert bad.last_error == "boom"
    assert good.calls == [("RADAR_TARGETING", "S001", "42", {})]


def test_create_external_collector_manager_from_env(monkeypatch):
    monkeypatch.setenv("EXTERNAL_COLLECTORS_ENABLED", "true")
    monkeypatch.setenv("EXTERNAL_COLLECTORS", "wecare")
    monkeypatch.setenv("WECARE_COLLECTOR_ENABLED", "true")
    monkeypatch.setenv("WECARE_COLLECTOR_BASE_URL", "http://127.0.0.1:8787")
    monkeypatch.setenv("WECARE_COLLECTOR_PROVIDER", "wecare")

    manager = create_external_collector_manager_from_env()

    assert manager is not None
    assert [adapter.name for adapter in manager.adapters] == ["wecare"]
    assert manager.adapters[0].base_url == "http://127.0.0.1:8787"


def test_wecare_collector_enabled_false_skips_wecare(monkeypatch):
    monkeypatch.setenv("EXTERNAL_COLLECTORS_ENABLED", "true")
    monkeypatch.setenv("EXTERNAL_COLLECTORS", "wecare")
    monkeypatch.setenv("WECARE_COLLECTOR_ENABLED", "false")

    manager = create_external_collector_manager_from_env()

    assert manager is None


def test_prime_collector_can_be_registered_from_env(monkeypatch):
    monkeypatch.setenv("EXTERNAL_COLLECTORS_ENABLED", "true")
    monkeypatch.setenv("EXTERNAL_COLLECTORS", "prime")
    monkeypatch.setenv("PRIME_COLLECTOR_ENABLED", "true")
    monkeypatch.setenv("PRIME_COLLECTOR_BASE_URL", "http://127.0.0.1:8789")
    monkeypatch.setenv("PRIME_COLLECTOR_PROVIDER", "prime")
    monkeypatch.setenv("PRIME_COLLECTOR_MARKER_TYPE", "1")

    manager = create_external_collector_manager_from_env()

    assert manager is not None
    assert [adapter.name for adapter in manager.adapters] == ["prime"]
    assert manager.adapters[0].base_url == "http://127.0.0.1:8789"
    assert manager.adapters[0].provider == "prime"
    assert manager.adapters[0].marker_type == 1


def test_external_collectors_db_path_resolves_server_prefix_to_repo_root():
    resolved = _resolve_db_path("server/data/external_collectors/collector_records.sqlite3")

    assert resolved.endswith(r"F18-Radar\server\data\external_collectors\collector_records.sqlite3")
    assert r"\server\server\data\\" not in resolved
