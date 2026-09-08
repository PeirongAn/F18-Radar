"""Backfill SA parent AOIs into an offline database copy; never edit source data.

Preview by default. --apply writes a fresh output directory using SQLite backup.
Geometry must be supplied per snapshot or explicitly inferred from the current
800x600 SA layout. Inferred geometry is not a historical DOM measurement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sqlite3

AOI_ID = "left_target_area"
DEFAULT_DB = Path(__file__).resolve().parents[1] / "data/gaze/gaze_records.db"


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def signature(display, regions):
    return hashlib.sha256(encode({"coordinate_space": "display_area_normalized",
                                 "display": display, "regions": regions}).encode()).hexdigest()


def validate_rect(rect):
    values = [rect[k] for k in ("left", "top", "right", "bottom")]
    if not all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in values):
        raise ValueError("Rectangle coordinates must be finite normalized numbers")
    if rect["left"] >= rect["right"] or rect["top"] >= rect["bottom"]:
        raise ValueError("Rectangle must have positive area")


def parent_region(row, bounds=None, infer=False):
    regions = json.loads(row["regions_json"])
    existing = [r for r in regions if r["id"] == AOI_ID]
    if existing:
        if len(existing) != 1:
            raise ValueError("Duplicate parent AOI")
        validate_rect(existing[0])
        return existing[0], "existing"
    if any(r["id"] == "left_tartet_area" for r in regions):
        raise ValueError("Found misspelled left_tartet_area; resolve explicitly before backfill")
    display = json.loads(row["display_json"])
    if row["coordinate_space"] != "display_area_normalized":
        raise ValueError("Unsupported coordinate space")
    if bounds is not None:
        rect = {k: bounds[k] for k in ("left", "top", "right", "bottom")}
        evidence = bounds.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError("Explicit bounds require an evidence description")
        visible = bounds.get("visible", True)
        if type(visible) is not bool:
            raise ValueError("visible must be boolean")
        method = "explicit_bounds: " + evidence
    elif infer:
        # App: 800x600 canvas, centered 800px list, flex gap 8px,
        # list wrapper border-top 1px. Assumes unclipped current layout.
        if not row["alignment_valid"] or not display.get("alignment_valid"):
            raise ValueError("Cannot infer from an unaligned snapshot")
        w, h = display["viewport_width_css_px"], display["viewport_height_css_px"]
        if w != display["screen_width_css_px"] or h != display["screen_height_css_px"]:
            raise ValueError("Viewport/screen mismatch")
        if not math.isfinite(w) or not math.isfinite(h) or w <= 0 or h <= 0:
            raise ValueError("Invalid viewport")
        if display.get("visual_viewport_scale", 1) != 1:
            raise ValueError("Scaled viewport")
        candidates = [r for r in regions if r["id"] == "left_candidate_list"]
        if len(candidates) != 1:
            raise ValueError("Need exactly one list anchor")
        anchor = candidates[0]
        validate_rect(anchor)
        if not anchor.get("visible") or abs((anchor["right"] - anchor["left"]) * w - 800) > 1:
            raise ValueError("List must be visible and 800 CSS pixels wide")
        if not (0 < anchor["left"] < anchor["right"] < 1 and anchor["bottom"] < 1):
            raise ValueError("Clipped list anchor")
        bottom = anchor["top"] - 9 / h
        rect = dict(left=anchor["left"], right=anchor["right"], top=bottom - 600 / h, bottom=bottom)
        visible = True
        method = "inferred_current_layout_800x600_gap8_border1"
    else:
        raise ValueError("Supply per-snapshot bounds or --infer-current-layout")
    validate_rect(rect)
    for child in regions:
        if child["id"] == "left_ai_target" and child.get("visible"):
            if not (rect["left"] <= child["left"] <= child["right"] <= rect["right"]
                    and rect["top"] <= child["top"] <= child["bottom"] <= rect["bottom"]):
                raise ValueError("Visible AI target is outside inferred/supplied parent")
    return dict(id=AOI_ID, shape="rect", visible=visible, **rect,
                binding={"role": "sa_target_area", "geometry_source": method}), method


def patch_frame(frame, snapshots):
    """Keep legacy hit/hits and all other annotations exactly as supplied."""
    revision = frame.get("aoi_revision")
    row = snapshots.get(revision) if type(revision) is int else None
    if row is None:
        return False
    ts = frame.get("ts_us")
    gaze = frame.get("gaze")
    if type(ts) is not int or not (row["valid_from_us"] <= ts < row["valid_to_us"]):
        return False
    if not row["alignment_valid"] or not isinstance(gaze, list) or len(gaze) < 2:
        return False
    if not all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in gaze[:2]):
        return False
    hits = frame.get("aoi_hits")
    if not isinstance(hits, list) or not all(isinstance(v, str) for v in hits):
        return False
    r = row["parent"]
    inside = r["visible"] and r["left"] <= gaze[0] <= r["right"] and r["top"] <= gaze[1] <= r["bottom"]
    desired = [v for v in hits if v != AOI_ID]
    if inside:
        desired.append(AOI_ID)
    if desired == hits:
        return False
    frame["aoi_hits"] = desired
    return True


def run(db, output, *, apply=False, task_ids=None, bounds=None, infer=False):
    db = Path(db).resolve()
    conn = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN")
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM gaze_aoi_snapshots WHERE task_type='SA_THREAT_RESPONSE' ORDER BY id")
                if task_ids is None or str(r["task_id"]) in task_ids]
        if not rows:
            raise ValueError("No matching SA snapshots")
        tasks = {}
        changes = []
        for row in rows:
            tid = str(row["task_id"])
            if tid not in tasks:
                task = conn.execute("SELECT * FROM gaze_tasks WHERE task_id=?", (tid,)).fetchone()
                if task is None or task["end_time_us"] is None:
                    raise ValueError(f"Task {tid} missing or active")
                tasks[tid] = dict(task)
            if row["valid_to_us"] is None or row["valid_to_us"] <= row["valid_from_us"]:
                raise ValueError("Open or invalid snapshot interval")
            key = str(row["id"])
            entry = bounds.get(key) if bounds is not None else None
            row["parent"], method = parent_region(row, entry, infer)
            regions = json.loads(row["regions_json"])
            if method != "existing":
                regions.append(row["parent"])
                regions.sort(key=lambda r: r["id"])
            row["patched_regions"] = regions
            changes.append(dict(snapshot_id=row["id"], task_id=tid, revision=row["revision"],
                                action="unchanged" if method == "existing" else "add",
                                geometry_source=method, region=row["parent"]))
        raw_outputs = {}
        frame_report = []
        for tid, task in tasks.items():
            source = Path(task["data_dir"]) / "raw_gaze.jsonl"
            selected = {r["revision"]: r for r in rows if str(r["task_id"]) == tid}
            changed = total = 0
            lines = []
            if source.exists():
                for line in source.read_text(encoding="utf-8").splitlines(keepends=True):
                    frame = json.loads(line)
                    if not isinstance(frame, dict):
                        raise ValueError(f"Invalid raw frame in {source}")
                    total += 1
                    if patch_frame(frame, selected):
                        changed += 1
                        line = encode(frame) + "\n"
                    lines.append(line)
            elif task.get("total_frames", 0):
                raise ValueError(f"Missing raw file with nonzero frame count: {source}")
            raw_outputs[tid] = "".join(lines)
            frame_report.append(dict(task_id=tid, source=str(source), frames=total,
                                     changed=changed, raw_missing=not source.exists()))
        report = dict(source_db=str(db), mode="copy" if apply else "preview",
                      snapshots=changes, raw_frames=frame_report)
        if apply:
            if output is None:
                raise ValueError("--output-dir required with --apply")
            output = Path(output).resolve()
            if output.exists():
                raise ValueError("Output directory already exists; choose a new directory")
            output.mkdir(parents=True)
            dest = sqlite3.connect(output / "gaze_records.db")
            try:
                conn.backup(dest)
                with dest:
                    dest.execute("CREATE TABLE IF NOT EXISTS sa_aoi_backfill_audit "
                                 "(id INTEGER PRIMARY KEY, source_db TEXT, report_json TEXT)")
                    for row, change in zip(rows, changes):
                        if change["action"] == "add":
                            dest.execute("UPDATE gaze_aoi_snapshots SET regions_json=?,layout_signature=? WHERE id=?",
                                         (encode(row["patched_regions"]), signature(json.loads(row["display_json"]), row["patched_regions"]), row["id"]))
                    for tid, task in tasks.items():
                        # Hash task id to avoid using untrusted path components.
                        data_dir = output / "raw" / hashlib.sha256(tid.encode()).hexdigest()[:20]
                        data_dir.mkdir(parents=True)
                        (data_dir / "raw_gaze.jsonl").write_text(raw_outputs[tid], encoding="utf-8")
                        dest.execute("UPDATE gaze_tasks SET data_dir=? WHERE task_id=?", (str(data_dir), tid))
                    dest.execute("INSERT INTO sa_aoi_backfill_audit(source_db,report_json) VALUES (?,?)", (str(db), encode(report)))
            finally:
                dest.close()
            (output / "backfill_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            report["output_db"] = str(output / "gaze_records.db")
        return report
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gaze-db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--task-id", action="append")
    parser.add_argument("--bounds-json", type=Path, help="Object keyed by snapshot numeric id; each value is a normalized rectangle with evidence")
    parser.add_argument("--infer-current-layout", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.bounds_json and args.infer_current_layout:
        parser.error("Choose explicit bounds or layout inference, not both")
    bounds = json.loads(args.bounds_json.read_text(encoding="utf-8")) if args.bounds_json else None
    try:
        report = run(args.gaze_db, args.output_dir, apply=args.apply,
                     task_ids=set(args.task_id) if args.task_id else None,
                     bounds=bounds, infer=args.infer_current_layout)
    except (ValueError, KeyError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"Backfill failed: {exc}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
