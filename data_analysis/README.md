# F18 Radar Data Analysis Export

This folder contains offline scripts that convert `server/data/radar_operations.db`
into an SFY-style `all_data.db`.

## Export SFY-compatible data

```powershell
server\.venv\Scripts\python.exe data_analysis\step1_read_and_merge_data.py --overwrite
```

Default input:

```text
server/data/radar_operations.db
```

Default outputs:

```text
data_analysis/output/all_data.db
data_analysis/output/quality_report.json
```

## Matching rules

- Radar and SA questionnaire rows match `task_settings` by
  `user_id + task_type + repetition_current`.
- Platform and weapon questionnaire rows match `task_runs` plus
  `task_subtask_results` by `user_id + task_type + repetition_current`.
- `WEAPON_FIRING` questionnaire rows map to `WEAPON_LAUNCH` task rows.
- `questionnaire_responses.is_practice` is ignored because the external page can
  send it incorrectly.
- Task metadata in the output comes from real task records, not questionnaire
  payload fields.

Unmatched questionnaire rows are written only to `quality_report.json`; they are
not inserted into `questionnaire_statistics`.

## Migrated SFY pipeline

The old `step*` scripts from `SFY外协数据分析` are migrated here and default to
reading/writing files under `data_analysis/output`.

```powershell
server\.venv\Scripts\python.exe data_analysis\step1_read_and_merge_data.py --overwrite
server\.venv\Scripts\python.exe data_analysis\step2_build_trust_data.py
server\.venv\Scripts\python.exe data_analysis\step5_task_performance_statistics_AI.py
server\.venv\Scripts\python.exe data_analysis\step5_task_performance_statistics_nonAI.py
```

`step3_multi_task_svm_classification.py` and
`step4_calculate_metrics_from_results.py` are also migrated, but they need enough
records per task/configuration to train and evaluate the SVM pipeline. The
current test database is too small for the old 10-repetition augmentation rule.

`step2`, `step3`, and `step5` need the old SFY Python analysis dependencies
(`pandas`, `numpy`, `scikit-learn`, `matplotlib`, `seaborn`). They are listed in
`requirements.txt`; the current `server/.venv` does not include pandas.

## Field check

Compare the generated `all_data.db` against the SFY reference schema:

```powershell
server\.venv\Scripts\python.exe data_analysis\check_fields.py
```
