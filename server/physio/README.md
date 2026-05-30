# Physio Ring Service

This module records wristband/ring physiological data from vendor CSV sessions.
It can run embedded in the F18 backend, or as a standalone check service.

## Start Modes

### Embedded in F18 backend

By default, the F18 backend starts this service during `server/main.py`
initialization.

```powershell
cd D:\codes\F18-Radar
server\.venv\Scripts\python.exe server\main.py
```

Open the pre-task check page:

```text
http://127.0.0.1:8080/physio/check
```

Disable embedded startup:

```powershell
$env:PHYSIO_RING_ENABLED="false"
server\.venv\Scripts\python.exe server\main.py
```

### Standalone physio service

Use this when you only want to test the wristband service before the task flow.

```powershell
cd D:\codes\F18-Radar
server\.venv\Scripts\python.exe server\physio\main.py
```

Default URL:

```text
http://127.0.0.1:8081/physio/check
```

Custom host or port:

```powershell
server\.venv\Scripts\python.exe server\physio\main.py --host 0.0.0.0 --port 8091
```

## Pages

### `GET /physio/check`

Pre-task check page. This page is not part of the F18 task flow.

It shows:

- service enabled/running/error state
- current mode and subject
- sample storage mode
- current vendor CSV session path
- current raw sample file path
- current task written row count
- live stream Hz and latest values for PPG, EDA, ACC, GYRO, HR, SKT, ENV, O2
- warnings
- export result

### `GET /physio/dashboard`

Live dashboard page for fuller monitoring.

It shows stream Hz, latest values, and short live traces.

## API

### `GET /api/physio/status`

Returns current service, collector, storage, and task state.

Example response shape:

```json
{
  "ok": true,
  "enabled": true,
  "running": true,
  "error": null,
  "time_ns": 1779700000000000000,
  "state": {
    "mode": "experiment",
    "subject_id": "S001",
    "run_id": "abc123",
    "task_name": "RADAR_TARGETING",
    "trial_id": null,
    "trial_name": null,
    "recent_markers": []
  },
  "collector": {
    "vendor_root": "D:\\hengzhi\\data",
    "project": null,
    "available_projects": [],
    "source_session_path": "D:\\hengzhi\\data\\project\\_DYN...",
    "streams": {
      "ppg": {
        "hz": 64,
        "last_seen_ns": 1779700000000000000,
        "last_value": {"value": 1.23},
        "points": []
      }
    },
    "warnings": []
  },
  "db_path": "D:\\codes\\F18-Radar\\server\\data\\physio\\experiment_data.sqlite3",
  "export_dir": "D:\\codes\\F18-Radar\\server\\data\\physio\\exports",
  "raw_dir": "D:\\codes\\F18-Radar\\server\\data\\physio\\raw",
  "sample_storage": "file",
  "sample_file": {
    "active_run_id": "abc123",
    "active_subject_id": "S001",
    "active_trial_id": null,
    "active_file_path": "D:\\codes\\F18-Radar\\server\\data\\physio\\raw\\S001\\abc123\\samples.csv",
    "active_row_count": 1280,
    "first_sample_ns": 1779700000000000000,
    "last_sample_ns": 1779700001000000000,
    "streams": ["ppg", "eda"]
  },
  "formal_sample_count": 1280
}
```

### `POST /api/physio/export`

Exports samples, markers, and metadata.

Request body may be empty, or may filter by context:

```json
{
  "subject_id": "S001",
  "run_id": "abc123",
  "trial_id": null
}
```

Response:

```json
{
  "ok": true,
  "samples_csv": "D:\\codes\\F18-Radar\\server\\data\\physio\\exports\\export_..._samples.csv",
  "markers_csv": "D:\\codes\\F18-Radar\\server\\data\\physio\\exports\\export_..._markers.csv",
  "metadata_json": "D:\\codes\\F18-Radar\\server\\data\\physio\\exports\\export_..._metadata.json"
}
```

Export reads raw file metadata from `task_runs` and merges the referenced raw
CSV files. Markers are always exported from SQLite.

## Internal Service Methods

These methods are used by F18 task lifecycle integration.

### `set_subject(subject_id, metadata=None)`

Sets the current subject context. New data does not write a separate `subjects`
table; subject metadata is folded into `task_runs.metadata_json`.

### `clear_subject()`

Closes any active raw sample writer, ends the active task row, and clears the
current subject context.

### `start_task(task_name, metadata=None, run_id=None)`

Creates a `task_runs` row and starts the current physio run. When F18 provides
`run_id`, it is the same value as the gaze/business `task_id`.

The raw file is created lazily after the first real sample arrives:

```text
server/data/physio/raw/<subject_id>/<run_id>/samples.csv
```

### `stop_task()`

Flushes and closes the current raw sample writer and updates the active
`task_runs` row.

### `marker(name, payload=None)`

Writes an event marker into SQLite. F18 currently writes markers for task start,
settings updates, antenna adjustments, target/threat clicks, and task result
confirmation.

### `export_data(subject_id=None, run_id=None, trial_id=None)`

Exports raw samples, markers, and metadata to the configured export directory.
`trial_id` is accepted for compatibility; new physio data is not segmented into
a `trials` table.

## Environment Variables

### `PHYSIO_RING_ENABLED`

Default: `true`

Set to `false`, `0`, `no`, or `off` to disable service creation.

### `PHYSIO_VENDOR_ROOT`

Default:

```text
D:\hengzhi\data
```

Root directory where vendor CSV sessions are discovered.

### `PHYSIO_DB_PATH`

Default:

```text
server/data/physio/experiment_data.sqlite3
```

SQLite database for task lifecycle, marker events, and raw sample file metadata.

### `PHYSIO_EXPORT_DIR`

Default:

```text
server/data/physio/exports
```

Directory for exported CSV/JSON files.

### `PHYSIO_RAW_DIR`

Default:

```text
server/data/physio/raw
```

Root directory for raw sample CSV files.

### `PHYSIO_SAMPLE_STORAGE`

Default:

```text
file
```

New data is always file-backed: high-frequency samples are written to raw CSV
files, and SQLite exposes only task metadata and markers. `sqlite` is ignored if
set in the environment.

### `PHYSIO_STREAMS`

Default:

```text
ppg,eda,acc,gyro,hr,skt,env,o2
```

Comma-separated stream list. The collector looks for matching CSV files such as
`ppg.csv`, `eda.csv`, and `hr.csv` in the active vendor session directory.

### `PHYSIO_HOST`

Standalone service only.

Default:

```text
127.0.0.1
```

### `PHYSIO_PORT`

Standalone service only.

Default:

```text
8081
```

## SQLite Tables

### `task_runs`

One physio run per formal F18 scene/question. For F18 tasks, `run_id` is the
same value as the gaze/business `task_id`.

This table also stores the raw sample file path, row count, sample time range,
and stream list.

### `markers`

Event markers aligned by `service_time_ns`.

## Raw Sample CSV Format

Each raw sample CSV uses this header:

```csv
stream,service_time_ns,device_time_ms,subject_id,run_id,trial_id,values_json,source_session_path
```

Default path:

```text
server/data/physio/raw/<subject_id>/<run_id>/samples.csv
```

## F18 Lifecycle Mapping

Practice mode does not write formal physio samples.

Formal radar and SA tasks:

- task start: set subject, start physio task, write `task_start` marker
- settings update: write `settings_update` marker
- antenna adjusted: write `antenna_adjusted` marker
- target selected: write `target_selected` marker
- threat clicked: write `threat_clicked` marker
- task result confirmed: write `task_result_confirmed` marker, stop task, clear subject
