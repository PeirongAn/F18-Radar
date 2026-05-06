# /tobii/hand 接口说明

`/tobii/hand` 用于在目标框出现或消失时，更新当前眼动任务的注意力区域。

在当前主服务中，眼动任务本身由 `task_start` / 任务结束流程创建和关闭；`/tobii/hand` 只负责更新当前活动任务的 `bbox`，不会重新创建或结束眼动任务。

## HTTP 接口

- Method: `POST`
- Path: `/tobii/hand`
- Content-Type: `application/json`

## 请求参数

| 参数 | 类型 | 必填 | 适用场景 | 说明 |
| --- | --- | --- | --- | --- |
| `box_visible` | boolean | 是 | 全部 | 目标框是否可见。`true` 表示目标框出现或更新；`false` 表示目标框消失。 |
| `task_id` | string / number | 否 | 全部 | 任务 ID。传入时必须匹配当前活动眼动任务，否则 bbox 更新会失败。未传时使用当前活动任务。 |
| `bbox` | array | 否 | `box_visible=true` | 目标框像素坐标列表，格式为 `[[x1, y1, x2, y2], ...]`。服务端会按屏幕尺寸归一化到 0-1 坐标系。未传或为空数组时，相当于没有注意力区域。 |
| `scream_data` | array | 否 | `box_visible=true` | 屏幕尺寸，格式为 `[width, height]`。字段名按当前代码实现为 `scream_data`。未传或非法时默认 `[1, 1]`。 |

## 请求示例

目标框出现或更新：

```json
{
  "box_visible": true,
  "task_id": 123,
  "bbox": [[420, 260, 780, 520]],
  "scream_data": [1920, 1080]
}
```

目标框消失：

```json
{
  "box_visible": false,
  "task_id": 123
}
```

## 响应示例

更新成功：

```json
{
  "ok": true,
  "msg": "bbox 已更新",
  "task_id": "123"
}
```

无活动任务或 `task_id` 不匹配：

```json
{
  "ok": false,
  "msg": "无活动任务，bbox 未更新",
  "task_id": null
}
```

目标框消失：

```json
{
  "ok": true,
  "msg": "目标框消失，bbox 已清空",
  "task_id": "123"
}
```

## 错误响应

眼动服务未注入或未启动：

```json
{
  "ok": false,
  "msg": "眼动追踪服务未启动"
}
```

请求体不是 JSON：

```json
{
  "ok": false,
  "msg": "请求体必须是 JSON"
}
```

缺少 `box_visible`：

```json
{
  "ok": false,
  "msg": "缺少字段: box_visible"
}
```

## WebSocket 等价消息

主 WebSocket 服务也支持等价消息：

```json
{
  "type": "tobii_hand",
  "box_visible": true,
  "task_id": 123,
  "bbox": [[420, 260, 780, 520]],
  "scream_data": [1920, 1080]
}
```

响应类型为 `tobii_hand_result`，其余字段与 HTTP 响应一致。
