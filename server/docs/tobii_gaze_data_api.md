# /tobii/gaze_data 接口说明

用于读取当前 Tobii 眼动数据状态，包含最新注视点、活动任务 ID、server 端屏幕配置和近期注视窗口。

## GET /tobii/gaze_data

查询参数：

- `max_age_ms`：最新注视点最大有效期，默认 `1000`，范围 `1..60000`。
- `limit`：返回近期窗口帧数，默认 `60`，范围 `0..600`。`0` 表示不返回窗口数据。

返回示例：

```json
{
  "ok": true,
  "msg": null,
  "gaze_point": [0.42, 0.31],
  "timestamp": 1779248234427,
  "active_task_id": "1",
  "screen_size": [2560, 1440],
  "window": [
    {
      "system_time_stamp": 1779248234427000,
      "gaze_point": [0.42, 0.31]
    }
  ],
  "window_count": 1,
  "max_age_ms": 1000
}
```

`gaze_point` 是 Tobii `left/right_gaze_point_on_display_area` 的有效点，使用归一化坐标。`screen_size` 来自 `server/.env` 中的 `GAZE_SCREEN_WIDTH` / `GAZE_SCREEN_HEIGHT`。

## 兼容接口

`GET /tobii/gaze_point` 仍保留，只返回最新注视点：

```json
{
  "ok": true,
  "gaze_point": [0.42, 0.31],
  "timestamp": 1779248234427
}
```
