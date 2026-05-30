import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.message_handler import MessageHandler
from main import _physio_has_required_start_data, _physio_start_warnings, _physio_total_live_hz
from physio.service import LslCollector, PhysioService, json_dumps, now_ns


class FakePhysioService:
    def __init__(self):
        self.calls = []

    def set_subject(self, subject_id, metadata=None):
        self.calls.append(("set_subject", subject_id, metadata or {}))

    def start_task(self, task_name, metadata=None, run_id=None):
        self.calls.append(("start_task", task_name, metadata or {}, run_id))

    def marker(self, name, payload=None):
        self.calls.append(("marker", name, payload or {}))

    def stop_task(self):
        self.calls.append(("stop_task",))

    def clear_subject(self):
        self.calls.append(("clear_subject",))


class FakeLslInfo:
    def __init__(self, name, stream_type, channel_count=1, nominal_srate=1.0):
        self._name = name
        self._type = stream_type
        self._channel_count = channel_count
        self._nominal_srate = nominal_srate

    def name(self):
        return self._name

    def type(self):
        return self._type

    def source_id(self):
        return self._name

    def channel_count(self):
        return self._channel_count

    def nominal_srate(self):
        return self._nominal_srate


class FakeLslInlet:
    def __init__(self, info, samples_by_name):
        self.info = info
        self.samples_by_name = samples_by_name
        self.closed = False

    def open_stream(self, timeout=0.0):
        return None

    def close_stream(self):
        self.closed = True

    def pull_chunk(self, timeout=0.0, max_samples=256):
        rows = self.samples_by_name.get(self.info.name(), [])
        if not rows:
            return [], []
        self.samples_by_name[self.info.name()] = []
        samples = [row[0] for row in rows[:max_samples]]
        timestamps = [row[1] for row in rows[:max_samples]]
        return samples, timestamps


class FakeLslModule:
    def __init__(self, infos, samples_by_name):
        self.infos = infos
        self.samples_by_name = samples_by_name

    def resolve_streams(self, wait_time=0.0):
        return self.infos

    def StreamInlet(self, info, max_buflen=360, recover=True):
        return FakeLslInlet(info, self.samples_by_name)


def test_physio_start_task_records_formal_task():
    handler = MessageHandler()
    physio = FakePhysioService()
    handler.set_physio_service(physio)

    handler._physio_start_task(
        "RADAR_TARGETING",
        "S001",
        42,
        "manual",
        {
            "is_ai_active": False,
            "difficulty_config": {"level": "low"},
            "audio_enabled": True,
            "repetition_info": {"current": 1, "total": 3},
        },
        {"is_practice": False},
    )

    assert physio.calls[0][0] == "set_subject"
    assert physio.calls[1][0] == "start_task"
    assert physio.calls[1][1] == "RADAR_TARGETING"
    assert physio.calls[1][2]["f18_task_id"] == 42
    assert physio.calls[1][3] == "42"
    assert physio.calls[2][0] == "marker"
    assert physio.calls[2][1] == "task_start"


def test_physio_skips_practice_task():
    handler = MessageHandler()
    physio = FakePhysioService()
    handler.set_physio_service(physio)

    handler._physio_start_task(
        "SA_THREAT_RESPONSE",
        "S001",
        43,
        "AI",
        {"is_ai_active": True},
        {"is_practice": True},
    )

    assert physio.calls == []


def test_physio_stop_task_writes_marker_then_clears_context():
    handler = MessageHandler()
    physio = FakePhysioService()
    handler.set_physio_service(physio)

    handler._physio_stop_task(
        "SA_THREAT_RESPONSE",
        "S001",
        99,
        "manual",
        {"current": 2, "total": 5},
        {"type": "task_result_confirmed", "timestamp": 123},
        {"is_practice": False},
    )

    assert [call[0] for call in physio.calls] == ["marker", "stop_task", "clear_subject"]
    assert physio.calls[0][1] == "task_result_confirmed"
    assert physio.calls[0][2]["f18_task_id"] == 99


def _sample_row(subject_id, run_id, trial_id=None, stream="ppg", value=1.25):
    return (
        stream,
        now_ns(),
        123.0,
        subject_id,
        run_id,
        trial_id,
        json_dumps({"value": value}),
        r"D:\hengzhi\data\project\_DYN_TEST",
    )


def _make_service(tmp, sample_storage="file"):
    base = Path(tmp)
    return PhysioService(
        vendor_root=str(base / "vendor"),
        db_path=base / "experiment_data.sqlite3",
        export_dir=base / "exports",
        raw_dir=base / "raw",
        streams=["ppg"],
        sample_storage=sample_storage,
    )


def test_physio_file_storage_writes_raw_csv_not_samples_table():
    with tempfile.TemporaryDirectory() as tmp:
        service = _make_service(tmp, sample_storage="file")
        try:
            service.set_subject("S001", {"group": "formal"})
            task = service.start_task("RADAR_TARGETING", {"f18_task_id": 42}, run_id="42")
            run_id = task["run_id"]

            service.sample_file_store.write_samples([_sample_row("S001", run_id)])
            sample_file = service.sample_file_store.snapshot()["active_file_path"]

            assert run_id == "42"
            assert sample_file
            assert Path(sample_file).exists()
            assert Path(sample_file).parts[-2:] == ("42", "samples.csv")
            rows = service.db.conn.execute("SELECT run_id FROM task_runs").fetchall()
            assert [row["run_id"] for row in rows] == ["42"]
            assert service.db.count_samples(subject_id="S001") == 0
            assert service.db.count_file_samples(subject_id="S001") == 1

            lines = Path(sample_file).read_text(encoding="utf-8").splitlines()
            assert lines[0].startswith("stream,service_time_ns,device_time_ms")
            assert len(lines) == 2
        finally:
            service.stop()


def test_physio_start_task_without_run_id_keeps_uuid_fallback():
    with tempfile.TemporaryDirectory() as tmp:
        service = _make_service(tmp, sample_storage="file")
        try:
            service.set_subject("S001", {"group": "formal"})
            task = service.start_task("RADAR_TARGETING", {"source": "standalone"})

            assert len(task["run_id"]) == 32
            assert task["run_id"] != "42"
        finally:
            service.stop()


def test_physio_explicit_active_run_id_is_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        service = _make_service(tmp, sample_storage="file")
        try:
            service.set_subject("S001", {"group": "formal"})
            first = service.start_task("RADAR_TARGETING", {"f18_task_id": 42}, run_id="42")
            second = service.start_task("RADAR_TARGETING", {"f18_task_id": 42}, run_id="42")

            rows = service.db.conn.execute("SELECT run_id, ended_at_ns FROM task_runs").fetchall()
            assert first["run_id"] == second["run_id"] == "42"
            assert len(rows) == 1
            assert rows[0]["ended_at_ns"] is None
        finally:
            service.stop()


def test_physio_rejects_completed_explicit_run_id_reuse():
    with tempfile.TemporaryDirectory() as tmp:
        service = _make_service(tmp, sample_storage="file")
        try:
            service.set_subject("S001", {"group": "formal"})
            service.start_task("RADAR_TARGETING", {"f18_task_id": 42}, run_id="42")
            service.stop_task()

            try:
                service.start_task("RADAR_TARGETING", {"f18_task_id": 42}, run_id="42")
            except RuntimeError as exc:
                assert "run_id already exists" in str(exc)
            else:
                raise AssertionError("Expected duplicate explicit run_id to be rejected")
        finally:
            service.stop()


def test_physio_file_storage_does_not_create_empty_raw_csv_without_samples():
    with tempfile.TemporaryDirectory() as tmp:
        service = _make_service(tmp, sample_storage="file")
        try:
            service.set_subject("S001", {"group": "formal"})
            service.start_task("RADAR_TARGETING", {"f18_task_id": 42})

            assert service.sample_file_store.snapshot()["active_file_path"] is None
            assert list((Path(tmp) / "raw").glob("**/samples.csv")) == []
            assert service.db.count_file_samples(subject_id="S001") == 0

            service.stop_task()
            assert list((Path(tmp) / "raw").glob("**/samples.csv")) == []
            assert service.db.count_file_samples(subject_id="S001") == 0
        finally:
            service.stop()


def test_physio_set_subject_same_subject_preserves_active_run_until_next_task():
    with tempfile.TemporaryDirectory() as tmp:
        service = _make_service(tmp, sample_storage="file")
        try:
            service.set_subject("S001", {"group": "formal"})
            first = service.start_task("PLATFORM_CONTROL", {"f18_task_id": 42})
            first_run_id = first["run_id"]

            service.set_subject("S001", {"group": "formal", "updated": True})
            assert service.status_payload()["state"]["run_id"] == first_run_id

            second = service.start_task("WEAPON_LAUNCH", {"f18_task_id": 43})
            rows = service.db.conn.execute(
                "SELECT run_id, ended_at_ns FROM task_runs ORDER BY started_at_ns"
            ).fetchall()

            assert rows[0]["run_id"] == first_run_id
            assert rows[0]["ended_at_ns"] is not None
            assert rows[1]["run_id"] == second["run_id"]
            assert rows[1]["ended_at_ns"] is None
        finally:
            service.stop()


def test_physio_new_database_exposes_only_task_runs_and_markers_tables():
    with tempfile.TemporaryDirectory() as tmp:
        service = _make_service(tmp, sample_storage="sqlite")
        try:
            service.set_subject("S001")
            task = service.start_task("RADAR_TARGETING", {"f18_task_id": 42}, run_id="42")
            service.sample_file_store.write_samples([_sample_row("S001", task["run_id"])])
            service.marker("task_start", {"f18_task_id": 42})

            tables = {
                row[0]
                for row in service.db.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert {"task_runs", "markers"}.issubset(tables)
            assert "subjects" not in tables
            assert "trials" not in tables
            assert "samples" not in tables
            assert "source_sessions" not in tables
            assert "sample_files" not in tables
            assert service.sample_storage == "file"
            assert service.db.count_samples(subject_id="S001") == 0
            assert service.db.count_file_samples(subject_id="S001") == 1
        finally:
            service.stop()


def test_physio_file_export_merges_raw_samples_and_markers():
    with tempfile.TemporaryDirectory() as tmp:
        service = _make_service(tmp, sample_storage="file")
        try:
            service.set_subject("S001")
            task = service.start_task("SA_THREAT_RESPONSE", {"f18_task_id": 77})
            run_id = task["run_id"]
            service.sample_file_store.write_samples(
                [
                    _sample_row("S001", run_id, stream="ppg", value=1.0),
                    _sample_row("S001", run_id, stream="ppg", value=2.0),
                ]
            )
            service.marker("task_result_confirmed", {"f18_task_id": 77})
            service.stop_task()

            exported = service.export_data(subject_id="S001")
            sample_lines = Path(exported["samples_csv"]).read_text(encoding="utf-8").splitlines()
            marker_text = Path(exported["markers_csv"]).read_text(encoding="utf-8")

            assert len(sample_lines) == 3
            assert "task_result_confirmed" in marker_text
            assert service.sample_file_store.snapshot()["active_file_path"] is None
            raw_files = service.db.get_raw_files(subject_id="S001")
            assert len(raw_files) == 1
            assert raw_files[0]["row_count"] == 2
            assert raw_files[0]["ended_at_ns"] is not None
        finally:
            service.stop()


def test_lsl_collector_reports_live_streams_from_samples_only():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        db = PhysioService(
            db_path=base / "experiment_data.sqlite3",
            export_dir=base / "exports",
            raw_dir=base / "raw",
            source_kind="lsl",
            pylsl_module=FakeLslModule(
                [
                    FakeLslInfo("DYN000150_HR", "HR", nominal_srate=1.0),
                    FakeLslInfo("DYN000150_PPG_ori", "PPG_ori", nominal_srate=100.0),
                ],
                {"DYN000150_HR": [([89.0], 123.456)]},
            ),
        )
        try:
            collector = db.collector
            assert isinstance(collector, LslCollector)
            collector.scan_once()
            collector.poll_once()
            status = collector.snapshot()

            assert status["source_kind"] == "lsl"
            assert len(status["discovered_streams"]) == 2
            assert status["live_streams"] == ["hr"]
            assert status["unavailable_streams"] == ["ppg_ori"]
            assert status["streams"]["hr"]["hz"] == 1
            assert status["streams"]["ppg_ori"]["hz"] == 0
        finally:
            db.stop()


def test_lsl_collector_warns_when_outlets_have_no_samples():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        service = PhysioService(
            db_path=base / "experiment_data.sqlite3",
            export_dir=base / "exports",
            raw_dir=base / "raw",
            source_kind="lsl",
            pylsl_module=FakeLslModule([FakeLslInfo("DYN000150_PPG_ori", "PPG_ori", nominal_srate=100.0)], {}),
        )
        try:
            service.collector.scan_once()
            service.collector.poll_once()
            status = service.status_payload()

            assert _physio_total_live_hz(status) == 0
            assert status["collector"]["discovered_streams"][0]["stream"] == "ppg_ori"
            assert status["collector"]["live_streams"] == []
            assert "LSL stream visible but no live samples" in _physio_start_warnings(status)
            assert "缺少实时数据流: acc, eda, env, gyro, hr, o2, ppg_filter, ppg_ori, skt" in _physio_start_warnings(status)
        finally:
            service.stop()


def test_lsl_collector_warns_when_no_matching_outlets():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        service = PhysioService(
            db_path=base / "experiment_data.sqlite3",
            export_dir=base / "exports",
            raw_dir=base / "raw",
            source_kind="lsl",
            pylsl_module=FakeLslModule([], {}),
        )
        try:
            service.collector.scan_once()
            status = service.status_payload()

            assert status["collector"]["discovered_streams"] == []
            assert _physio_start_warnings(status) == [
                "No LSL streams matching prefix DYN",
                "缺少实时数据流: acc, eda, env, gyro, hr, o2, ppg_filter, ppg_ori, skt",
            ]
        finally:
            service.stop()


def test_lsl_start_warnings_report_partially_missing_live_streams():
    status = {
        "collector": {
            "source_kind": "lsl",
            "streams": {
                "ppg_ori": {"hz": 64},
                "ppg_filter": {"hz": 64},
                "hr": {"hz": 1},
                "acc": {"hz": 0},
                "mark": {"hz": 0},
            },
            "live_streams": ["hr", "ppg_filter", "ppg_ori"],
            "warnings": [],
        }
    }

    assert _physio_total_live_hz(status) == 129
    assert not _physio_has_required_start_data(status)
    assert _physio_start_warnings(status) == ["缺少实时数据流: acc"]


def test_lsl_start_data_allows_missing_marker_stream():
    status = {
        "collector": {
            "source_kind": "lsl",
            "streams": {
                "ppg_ori": {"hz": 64},
                "hr": {"hz": 1},
                "mark": {"hz": 0},
            },
            "live_streams": ["hr", "ppg_ori"],
            "warnings": [],
        }
    }

    assert _physio_has_required_start_data(status)
    assert _physio_start_warnings(status) == []


def test_lsl_samples_write_existing_raw_csv_format():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        service = PhysioService(
            db_path=base / "experiment_data.sqlite3",
            export_dir=base / "exports",
            raw_dir=base / "raw",
            source_kind="lsl",
            pylsl_module=FakeLslModule([FakeLslInfo("DYN000150_HR", "HR")], {"DYN000150_HR": [([88.0], 555.25)]}),
        )
        try:
            service.set_subject("S001")
            task = service.start_task("RADAR_TARGETING", {"f18_task_id": 42})
            service.collector.scan_once()
            service.collector.poll_once()

            sample_file = service.sample_file_store.snapshot()["active_file_path"]
            assert sample_file
            rows = Path(sample_file).read_text(encoding="utf-8").splitlines()
            assert len(rows) == 2
            assert rows[0].startswith("stream,service_time_ns,device_time_ms")
            assert rows[1].startswith("hr,")
            assert ",S001," in rows[1]
            assert task["run_id"] in rows[1]
            assert "lsl_timestamp" in rows[1]
            assert "DYN000150_HR" in rows[1]
            assert ",lsl://DYN000150_HR" in rows[1]
        finally:
            service.stop()


def test_physio_start_warnings_report_missing_vendor_session():
    status = {
        "collector": {
            "vendor_root": r"D:\hengzhi\data\project",
            "source_session_path": None,
            "streams": {},
            "warnings": [r"No vendor session under D:\hengzhi\data\project"],
        }
    }

    assert _physio_total_live_hz(status) == 0
    assert _physio_start_warnings(status) == [r"No vendor session under D:\hengzhi\data\project"]


def test_physio_start_warnings_report_session_without_live_samples():
    status = {
        "collector": {
            "source_session_path": r"D:\hengzhi\data\project\_DYN_TEST",
            "streams": {"ppg": {"hz": 0}, "hr": {"hz": 0}},
            "warnings": [],
        }
    }

    warnings = _physio_start_warnings(status)

    assert _physio_total_live_hz(status) == 0
    assert warnings == ["当前手环/指环数据会话没有实时样本，请确认厂商采集软件已连接设备并开始采集"]


def test_physio_start_warnings_empty_when_live_samples_exist():
    status = {
        "collector": {
            "source_session_path": r"D:\hengzhi\data\project\_DYN_TEST",
            "streams": {"ppg": {"hz": 12}, "hr": {"hz": 1}},
            "warnings": [],
        }
    }

    assert _physio_total_live_hz(status) == 13
    assert _physio_start_warnings(status) == []


def test_physio_start_warnings_empty_when_any_single_stream_is_live():
    status = {
        "collector": {
            "source_session_path": r"D:\hengzhi\data\project\_DYN_TEST",
            "streams": {"ppg": {"hz": 0}, "eda": {"hz": 0}, "hr": {"hz": 1}},
            "warnings": ["No live samples in the current vendor CSV session. Check that vendor acquisition is started, not just connected."],
        }
    }

    assert _physio_total_live_hz(status) == 1
    assert _physio_start_warnings(status) == []
