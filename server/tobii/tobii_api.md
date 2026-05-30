# Tobii 眼动服务接口

本文档描述 `server/tobii/` 当前支持的眼动联调接口。主服务模式指 `server/main.py` 启动后由 `server/network/http_server.py` 提供的 `http://127.0.0.1:8080`；独立模式指直接运行 `server/tobii/main.py` 后的 HTTP `8081` 和 WebSocket `8082`。

## 测试页面

`GET /tobii/test-ui`

返回同源 HTML 测试页，用于单独验证：

- `gaze_data` / `gaze_point` 轮询和注视点 overlay。
- `/tobii/hand` 目标区域设置与清除。
- `/tobii/marker` 写入 Tobii gaze marker。
- WebSocket 接收真实 `attention_feedback` 广播。

## 数据存储

新采集数据以 `server/data/gaze/gaze_records.db` 为元数据入口：

- `gaze_tasks`：任务生命周期、用户、任务来源、开始/结束触发、帧数统计和任务目录。
- `gaze_markers`：任务 marker；`payload_json` 不再重复保存 `task_id/user_id/event_type/gaze_task_id/timestamp` 等 envelope 字段。
- `gaze_targets`：注意力区域变化；新写入记录以 `normalized_bbox_json` 和屏幕尺寸为分析主数据。
- `gaze_feedback_events`：注意力反馈事件；重复 envelope 信息由列保存。

任务目录只保留高频逐帧数据：

```text
server/data/gaze/raw/<user_id>/<task_id>/raw_gaze.jsonl
```

`raw_gaze.jsonl` 每行使用瘦身格式：

```json
{"ts_us": 1779950284858328, "gaze": [0.736, 0.951], "hit": false}
{"ts_us": 1779950284865778, "gaze": null, "hit": false}
{"ts_us": 1779950285000000, "gaze": [0.42, 0.31], "hit": true, "hits": ["antenna_prompt"]}
```

新任务目录不再写 `markers.jsonl` 或 `summary.json`；marker、target、feedback 和任务摘要都从 SQLite 查询。

主服务访问：

```text
http://127.0.0.1:8080/tobii/test-ui
```

独立 Tobii 服务访问：

```text
http://127.0.0.1:8081/tobii/test-ui
```

## POST /tobii/hand

更新当前 gaze task 的注意力区域。主服务集成模式下，gaze task 由 F18 主任务 `task_start` 创建，`/tobii/hand` 只负责设置或清空区域，不负责结束主任务。独立 `server/tobii/main.py` 模式保留旧行为：`box_visible=true` 会 `start_task`，`box_visible=false` 会 `stop_task`。

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `box_visible` | boolean | 是 | `true` 设置目标区域，`false` 清除目标区域。 |
| `task_id` | string/number | 否 | 提供时必须匹配当前 active gaze task。 |
| `coordinate_space` | string | 否 | `display_area_normalized` 或 `physical_pixel`。缺省时按坐标值推断。 |
| `regions` | array | 否 | 推荐使用的区域列表，支持 `rect` 和 `ellipse`。 |
| `bbox` | array | 否 | 兼容旧格式 `[[left, top, right, bottom]]`。 |
| `screen_data` | array | 否 | `[width, height]`，仅 `physical_pixel` 坐标需要。 |
| `user_id` | string | 否 | 独立模式创建任务时写入任务元数据。 |
| `task_source` | string | 否 | 独立模式创建任务时写入任务来源。 |
| `task_name` | string | 否 | 独立模式创建任务时写入任务名称。 |

归一化区域示例：

```json
{
  "box_visible": true,
  "task_id": "42",
  "coordinate_space": "display_area_normalized",
  "regions": [
    {
      "shape": "rect",
      "id": "antenna_prompt",
      "left": 0.35,
      "top": 0.30,
      "right": 0.65,
      "bottom": 0.55
    }
  ]
}
```

物理像素区域示例：

```json
{
  "box_visible": true,
  "task_id": "42",
  "coordinate_space": "physical_pixel",
  "regions": [
    {
      "shape": "rect",
      "left": 720,
      "top": 360,
      "right": 1260,
      "bottom": 660
    }
  ],
  "screen_data": [1920, 1080]
}
```

清除区域：

```json
{
  "box_visible": false,
  "task_id": "42"
}
```

主服务响应：

```json
{
  "ok": true,
  "msg": "bbox updated",
  "task_id": "42"
}
```

## POST /tobii/marker

写入 Tobii gaze marker。marker 不复用 `server/physio/` 的生理 marker 表，而是写入 `server/data/gaze/gaze_records.db` 的 `gaze_markers` 表。

没有 active task 时仍允许写 DB 级 marker；如果传入的 `task_id` 与当前 active task 不一致，则返回 400，且不会写入 marker。

请求示例：

```json
{
  "name": "manual_marker",
  "task_id": "42",
  "user_id": "S001",
  "payload": {
    "note": "operator clicked marker",
    "target": "antenna_prompt"
  }
}
```

响应示例：

```json
{
  "ok": true,
  "type": "tobii_marker_result",
  "marker": {
    "marker_id": "b4c9...",
    "task_id": "42",
    "user_id": "S001",
    "name": "manual_marker",
    "event_time_us": 1779250000000000,
    "payload": {
      "note": "operator clicked marker"
    }
  }
}
```

## GET /tobii/gaze_point

返回最新有效注视点。坐标为 Tobii display area 归一化坐标。

成功响应：

```json
{
  "ok": true,
  "gaze_point": [0.42, 0.31],
  "timestamp": 1779250000000
}
```

当没有设备数据或数据过期时返回 404。

## GET /tobii/gaze_data

返回当前眼动状态，适合测试页轮询。

查询参数：

| 参数 | 默认 | 范围 | 说明 |
| --- | --- | --- | --- |
| `max_age_ms` | `1000` | `1..60000` | 最新注视点最大有效期。 |
| `limit` | `60` | `0..600` | 返回最近窗口帧数，`0` 表示不返回窗口帧。 |

响应示例：

```json
{
  "ok": true,
  "msg": null,
  "gaze_point": [0.42, 0.31],
  "timestamp": 1779250000000,
  "active_task_id": "42",
  "screen_size": [1920, 1080],
  "window": [
    {
      "system_time_stamp": 1779250000000000,
      "gaze_point": [0.42, 0.31],
      "valid": true
    }
  ],
  "window_count": 1,
  "max_age_ms": 1000
}
```

## WebSocket

主服务 WebSocket：

```text
ws://127.0.0.1:8080/ws
```

独立 Tobii WebSocket：

```text
ws://127.0.0.1:8082
```

### tobii_hand

主服务支持：

```json
{
  "type": "tobii_hand",
  "box_visible": true,
  "task_id": "42",
  "coordinate_space": "display_area_normalized",
  "regions": [
    {
      "shape": "rect",
      "left": 0.35,
      "top": 0.30,
      "right": 0.65,
      "bottom": 0.55
    }
  ]
}
```

响应：

```json
{
  "type": "tobii_hand_result",
  "ok": true,
  "task_id": "42"
}
```

独立服务的旧 WebSocket 消息类型是 `hand`，本次仍保留；测试页默认通过 HTTP `/tobii/hand` 设置区域。

### tobii_marker

主服务支持 `type: "tobii_marker"`；独立服务支持 `type: "marker"` 和 `type: "tobii_marker"`。

```json
{
  "type": "tobii_marker",
  "name": "manual_marker",
  "task_id": "42",
  "user_id": "S001",
  "payload": {
    "note": "ws marker"
  }
}
```

响应：

```json
{
  "type": "tobii_marker_result",
  "ok": true,
  "marker": {
    "marker_id": "b4c9...",
    "task_id": "42",
    "name": "manual_marker"
  }
}
```

### attention_feedback

`attention_feedback` 是服务端广播，不是测试页人工触发接口。当前触发条件是 gaze 连续未命中目标区域达到 `GAZE_OUT_OF_BOX_FALSE_THRESHOLD`。

广播示例：

```json
{
  "ok": true,
  "type": "attention_feedback",
  "action": "flash_mode",
  "should_flash": true,
  "duration_ms": 3000,
  "reason": "consecutive_not_in_target",
  "consecutive_false_count": 200,
  "task_id": "42",
  "server_time_ms": 1779250000000
}
```

同时写入 SQLite 表 `gaze_feedback_events`。
