# 眼动数据存储与任务关联

## 数据模型

眼动数据按三层组织：

- 任务生命周期：`gaze_tasks` 记录一次任务的 start/end，`task_id` 是主关联键。
- 逐帧眼动数据：`raw_gaze.jsonl` 记录每帧分析用 gaze 点、有效性和区域命中结果。
- 低频事件：`gaze_targets` 记录系统希望用户注视的区域历史，`gaze_feedback_events` 记录系统提醒事件。

`tobii_hand box_visible=true/false` 只更新注意力区域，不代表任务开始或结束。

## 目录结构

新任务的文件写入：

```text
server/data/gaze/
  gaze_records.db
  raw/
    {user_id}/
      {task_id}/
        raw_gaze.jsonl
```

旧的 `server/data/gaze/{task_id}` 和 `server/data/gaze/users/{user_id}/{YYYYMMDD}/{task_id}` 目录不迁移，旧任务仍通过数据库里的 `data_dir` 字段定位。

## SQLite

快速定位任务文件：

```sql
SELECT data_dir
FROM gaze_tasks
WHERE task_id = ?;
```

核心表：

- `gaze_tasks`: `task_id`、`user_id`、`task_source`、`task_name`、`data_dir`、`start_time_us`、`end_time_us`、`start_trigger`、`end_trigger`、帧统计和状态。
- `gaze_targets`: attention regions 更新历史，继续保留 `bbox_json` 和 `normalized_bbox_json` 兼容旧字段。
- `gaze_feedback_events`: 离框提醒事件，只写 SQLite，不再生成 `feedback.jsonl`。

## raw_gaze.jsonl

每帧一行分析数据：

```json
{"ts_us":1779250000000000,"gaze":[0.421,0.913],"hit":true,"hits":["region_1"]}
```

`region_hits` 优先使用 region 自带的 `id`，没有 `id` 时按 `region_1`、`region_2` 生成。

无效 gaze 不再写成 `(0.0, 0.0)`：

```json
{"ts_us":1779250000000000,"gaze":null,"hit":false}
```

新任务目录不再写 `summary.json`；任务摘要由 `gaze_tasks` 查询还原。
