import json
from pathlib import Path

import numpy as np
import pandas as pd


BASE = Path(r"D:\codes\模拟器采集特征数据data\模拟器采集特征数据data")
RECEIVED = BASE / "3.眼动仪1_接收.csv"
RAW = BASE / "3.眼动仪1_原始.csv"


def py(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        if np.isnan(v):
            return None
        return float(v)
    return v


r = pd.read_csv(RECEIVED)
o = pd.read_csv(RAW, low_memory=False, skipinitialspace=True)
rc = list(r.columns)

ts = pd.to_numeric(r.iloc[:, 0], errors="coerce")
dt = ts.diff()
positive_dt = dt[dt > 0]

out = {
    "received": {
        "rows": len(r),
        "columns": len(r.columns),
        "column_names": list(r.columns),
        "start_ms": int(ts.min()),
        "end_ms": int(ts.max()),
        "duration_ms": int(ts.max() - ts.min()),
        "start_local": pd.to_datetime(ts.min(), unit="ms", utc=True).tz_convert("Asia/Shanghai").isoformat(),
        "end_local": pd.to_datetime(ts.max(), unit="ms", utc=True).tz_convert("Asia/Shanghai").isoformat(),
        "median_positive_dt_ms": py(positive_dt.median()),
        "mean_positive_dt_ms": py(positive_dt.mean()),
        "p95_positive_dt_ms": py(positive_dt.quantile(0.95)),
        "max_positive_dt_ms": py(positive_dt.max()),
        "zero_dt_rows": int(dt.eq(0).sum()),
        "backward_rows": int(dt.lt(0).sum()),
        "gaps_gt_20ms": int(dt.gt(20).sum()),
        "gaps_gt_50ms": int(dt.gt(50).sum()),
        "unique_timestamps": int(ts.nunique()),
        "effective_rows_per_sec": py((len(r) - 1) * 1000 / (ts.max() - ts.min())),
        "effective_unique_timestamps_per_sec": py((ts.nunique() - 1) * 1000 / (ts.max() - ts.min())),
    }
}

for label, base in (("left", 1), ("right", 8)):
    conf = pd.to_numeric(r.iloc[:, base], errors="coerce")
    pos_x = pd.to_numeric(r.iloc[:, base + 1], errors="coerce")
    pos_y = pd.to_numeric(r.iloc[:, base + 2], errors="coerce")
    diameter = pd.to_numeric(r.iloc[:, base + 3], errors="coerce")
    distance = pd.to_numeric(r.iloc[:, base + 4], errors="coerce")
    screen_x = pd.to_numeric(r.iloc[:, base + 5], errors="coerce")
    screen_y = pd.to_numeric(r.iloc[:, base + 6], errors="coerce")
    conf_valid = conf > 0
    eye = {
        "confidence_counts": {str(py(k)): int(v) for k, v in conf.value_counts(dropna=False).sort_index().items()},
        "confidence_valid_pct": py(conf_valid.mean() * 100),
        "position_valid_pct": py((pos_x.ge(0) & pos_y.ge(0)).mean() * 100),
        "diameter_valid_pct": py(diameter.ge(0).mean() * 100),
        "distance_valid_pct": py(distance.ge(0).mean() * 100),
        "screen_valid_pct": py((screen_x.ge(0) & screen_y.ge(0)).mean() * 100),
        "confidence_valid_but_screen_invalid_rows": int((conf_valid & ~(screen_x.ge(0) & screen_y.ge(0))).sum()),
        "confidence_invalid_but_position_valid_rows": int((~conf_valid & pos_x.ge(0) & pos_y.ge(0)).sum()),
        "position_x_valid_range": [py(pos_x[pos_x >= 0].min()), py(pos_x[pos_x >= 0].median()), py(pos_x[pos_x >= 0].max())],
        "position_y_valid_range": [py(pos_y[pos_y >= 0].min()), py(pos_y[pos_y >= 0].median()), py(pos_y[pos_y >= 0].max())],
        "diameter_valid_range_mm": [py(diameter[diameter >= 0].min()), py(diameter[diameter >= 0].median()), py(diameter[diameter >= 0].max())],
        "distance_valid_range": [py(distance[distance >= 0].min()), py(distance[distance >= 0].median()), py(distance[distance >= 0].max())],
        "screen_x_valid_range": [py(screen_x[screen_x >= 0].min()), py(screen_x[screen_x >= 0].median()), py(screen_x[screen_x >= 0].max())],
        "screen_y_valid_range": [py(screen_y[screen_y >= 0].min()), py(screen_y[screen_y >= 0].median()), py(screen_y[screen_y >= 0].max())],
    }
    out[label] = eye

left_conf = pd.to_numeric(r.iloc[:, 1], errors="coerce") > 0
right_conf = pd.to_numeric(r.iloc[:, 8], errors="coerce") > 0
out["binocular_states"] = {
    "both_valid_rows": int((left_conf & right_conf).sum()),
    "left_only_rows": int((left_conf & ~right_conf).sum()),
    "right_only_rows": int((~left_conf & right_conf).sum()),
    "neither_rows": int((~left_conf & ~right_conf).sum()),
    "either_valid_pct": py((left_conf | right_conf).mean() * 100),
    "both_valid_pct": py((left_conf & right_conf).mean() * 100),
}

# Build the subset of raw columns that should be present in the receiver stream.
raw_map = pd.DataFrame({
    "l_conf": o["Validity Left"].eq(1).astype(float),
    "l_pos_x": o["Pupil Position Left X"],
    "l_pos_y": o["Pupil Position Left Y"],
    "l_diam": o["Pupil Diameter Left[mm]"],
    "l_screen_x": o["Gaze Point Left X[px]"].where(o["Gaze Point Left X[px]"].lt(0), o["Gaze Point Left X[px]"] / 1280),
    "l_screen_y": o["Gaze Point Left Y[px]"].where(o["Gaze Point Left Y[px]"].lt(0), o["Gaze Point Left Y[px]"] / 960),
    "r_conf": o["Validity Right"].eq(1).astype(float),
    "r_pos_x": o["Pupil Position Right X"],
    "r_pos_y": o["Pupil Position Right Y"],
    "r_diam": o["Pupil Diameter Right[mm]"],
    "r_screen_x": o["Gaze Point Right X[px]"].where(o["Gaze Point Right X[px]"].lt(0), o["Gaze Point Right X[px]"] / 1280),
    "r_screen_y": o["Gaze Point Right Y[px]"].where(o["Gaze Point Right Y[px]"].lt(0), o["Gaze Point Right Y[px]"] / 960),
})

recv_map = r.iloc[:, [1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 13, 14]].copy()
recv_map.columns = raw_map.columns

def keys(frame):
    return frame.round(3).apply(lambda row: "|".join(f"{float(v):.3f}" for v in row), axis=1)

raw_key = keys(raw_map)
recv_key = keys(recv_map)
raw_key_set = set(raw_key)
recv_key_set = set(recv_key)

raw_unique_mask = ~raw_key.duplicated(keep=False)
recv_unique_mask = ~recv_key.duplicated(keep=False)
raw_unique = pd.DataFrame({
    "key": raw_key[raw_unique_mask],
    "raw_rel_ms": pd.to_numeric(o.loc[raw_unique_mask, "Recording Time Stamp[ms]"], errors="coerce"),
})
recv_unique = pd.DataFrame({
    "key": recv_key[recv_unique_mask],
    "recv_ts_ms": ts[recv_unique_mask],
})
pairs = raw_unique.merge(recv_unique, on="key", how="inner")
pairs["offset_ms"] = pairs["recv_ts_ms"] - pairs["raw_rel_ms"]
offset = pairs["offset_ms"].median()
residual = pairs["offset_ms"] - offset

session_start = offset + pd.to_numeric(o["Recording Time Stamp[ms]"], errors="coerce").min()
session_end = offset + pd.to_numeric(o["Recording Time Stamp[ms]"], errors="coerce").max()
in_session = ts.between(session_start - 20, session_end + 20)

out["raw_comparison"] = {
    "raw_rows": len(o),
    "received_rows_with_any_exact_raw_content_match": int(recv_key.isin(raw_key_set).sum()),
    "received_exact_match_pct_all": py(recv_key.isin(raw_key_set).mean() * 100),
    "raw_rows_with_any_exact_received_content_match": int(raw_key.isin(recv_key_set).sum()),
    "raw_exact_match_pct": py(raw_key.isin(recv_key_set).mean() * 100),
    "unique_content_pairs_for_clock_fit": len(pairs),
    "estimated_absolute_anchor_ms": py(offset),
    "estimated_anchor_local": pd.to_datetime(offset, unit="ms", utc=True).tz_convert("Asia/Shanghai").isoformat(),
    "clock_residual_ms_quantiles": {str(q): py(residual.quantile(q)) for q in (0, .01, .05, .5, .95, .99, 1)},
    "estimated_session_start_local": pd.to_datetime(session_start, unit="ms", utc=True).tz_convert("Asia/Shanghai").isoformat(),
    "estimated_session_end_local": pd.to_datetime(session_end, unit="ms", utc=True).tz_convert("Asia/Shanghai").isoformat(),
    "received_rows_in_raw_time_window": int(in_session.sum()),
    "received_rows_in_window_matching_raw_content": int((in_session & recv_key.isin(raw_key_set)).sum()),
    "received_window_match_pct": py((in_session & recv_key.isin(raw_key_set)).sum() / in_session.sum() * 100),
}

# Estimate exact field equality among content-matched unique pairs.
if len(pairs):
    start_matches = pairs.sort_values("raw_rel_ms").head(5)
    end_matches = pairs.sort_values("raw_rel_ms").tail(5)
    out["raw_comparison"]["clock_offset_first5_ms"] = [py(x) for x in start_matches["offset_ms"]]
    out["raw_comparison"]["clock_offset_last5_ms"] = [py(x) for x in end_matches["offset_ms"]]

print(json.dumps(out, ensure_ascii=False, indent=2))
