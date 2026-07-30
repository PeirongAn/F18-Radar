from server.statistics.aoi_gaze_statistics import analyze_task


def _eye(point):
    return {
        "gaze_user_mm": point,
        "origin_user_mm": [0.0, 0.0, 0.0],
        "gaze_valid": True,
        "origin_valid": True,
    }


def _frame(ts_us, gaze_x, hits, revision=1):
    point = [gaze_x * 100.0, 0.0, 600.0]
    return {
        "ts_us": ts_us,
        "gaze": [gaze_x, 0.4],
        "aoi_revision": revision,
        "aoi_hits": hits,
        "left_eye": _eye(point),
        "right_eye": _eye(point),
    }


def test_analyze_task_preserves_all_hits_and_assigns_fixation_to_smallest_aoi():
    snapshots = {
        1: {
            "revision": 1,
            "alignment_valid": 1,
            "regions": [
                {
                    "id": "left_candidate_list", "shape": "rect", "visible": True,
                    "left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.9,
                },
                {
                    "id": "left_ai_target", "shape": "rect", "visible": True,
                    "left": 0.35, "top": 0.35, "right": 0.45, "bottom": 0.45,
                },
            ],
        }
    }
    frames = [
        _frame(1_000_000, 0.4000, ["left_ai_target", "left_candidate_list"]),
        _frame(1_050_000, 0.4001, ["left_ai_target", "left_candidate_list"]),
        _frame(1_100_000, 0.4002, ["left_ai_target", "left_candidate_list"]),
        _frame(1_150_000, 0.4003, ["left_ai_target", "left_candidate_list"]),
    ]
    result = analyze_task(
        {
            "task_id": "1", "user_id": "U1", "task_name": "RADAR_TARGETING",
            "status": "completed", "data_dir": "unused",
        },
        snapshots,
        frames,
        1_000_000,
        1_150_000,
        max_gap_ms=100,
        velocity_threshold_deg_s=30,
        min_fixation_ms=100,
        window_source="decision_window",
    )

    target = result["aoi_metrics"]["left_ai_target"]
    candidate_list = result["aoi_metrics"]["left_candidate_list"]
    assert target["valid_sample_count"] == 4
    assert candidate_list["valid_sample_count"] == 4
    assert target["dwell_ms"] == 150
    assert candidate_list["dwell_ms"] == 150
    assert target["fixation_count"] == 1
    assert candidate_list["fixation_count"] == 0
    assert result["fixations"][0]["aoi"] == "left_ai_target"


def test_analyze_task_caps_dwell_gap_and_reports_invalid_alignment():
    snapshots = {
        1: {
            "revision": 1,
            "alignment_valid": 0,
            "regions": [],
        }
    }
    frames = [
        _frame(1_000_000, 0.4, [], revision=1),
        _frame(1_500_000, 0.4, [], revision=1),
    ]
    result = analyze_task(
        {"task_id": "2", "user_id": "U1", "task_name": "SA_THREAT_RESPONSE", "data_dir": "unused"},
        snapshots,
        frames,
        1_000_000,
        1_500_000,
        max_gap_ms=100,
        velocity_threshold_deg_s=30,
        min_fixation_ms=100,
        window_source="decision_window",
    )
    assert result["quality"]["alignment_invalid_ms"] == 100
    assert result["fixations"] == []


def test_analyze_task_reports_ai_statistical_accuracy_as_independent_aoi():
    snapshots = {
        1: {
            "revision": 1,
            "alignment_valid": 1,
            "regions": [{
                "id": "right_ai_history_accuracy",
                "shape": "rect",
                "visible": True,
                "left": 0.68,
                "top": 0.05,
                "right": 1.0,
                "bottom": 0.20,
                "binding": {
                    "metric": "ai_statistical_accuracy",
                    "ai_level": "L2",
                    "curve_seed": 20260730,
                },
            }],
        }
    }
    frames = [
        _frame(1_000_000, 0.8, ["right_ai_history_accuracy"]),
        _frame(1_050_000, 0.8, ["right_ai_history_accuracy"]),
        _frame(1_100_000, 0.8, ["right_ai_history_accuracy"]),
    ]
    result = analyze_task(
        {"task_id": "3", "user_id": "U1", "task_name": "RADAR_TARGETING", "data_dir": "unused"},
        snapshots,
        frames,
        1_000_000,
        1_100_000,
        max_gap_ms=100,
        velocity_threshold_deg_s=30,
        min_fixation_ms=100,
        window_source="decision_window",
    )

    metric = result["aoi_metrics"]["right_ai_history_accuracy"]
    assert metric["valid_sample_count"] == 3
    assert metric["dwell_ms"] == 100
    assert metric["fixation_count"] == 1
    assert result["fixations"][0]["aoi"] == "right_ai_history_accuracy"
