# 眼动服务调用与反馈流程

本文说明当前前端任务如何调用眼动服务，以及后端如何记录目标出现、目标消失和注意力反馈。当前涉及两类任务：

- 传感器任务：雷达参数设置完成后进入天线高度调整阶段，前端对天线提示框调用眼动服务。
- 威胁排序任务：SA 页面中仅在 AI 启用时，对 AI 选中的威胁目标调用眼动服务。

## 总体链路

眼动任务生命周期由主任务驱动，注意力区域由前端的 `tobii_hand` 消息更新。

1. 后端任务开始时，`MessageHandler._gaze_start(...)` 调用 `GazeService.start_task(...)`，创建当前 active gaze task。
2. 前端目标出现时，通过 WebSocket 发送 `type: "tobii_hand"` 且 `box_visible: true`，把目标区域写入当前 gaze task。
3. 后端 `websocket_server._handle_tobii_hand(...)` 调用 `GazeService.set_task_bbox(...)`，更新当前任务的 `regions/bbox`。
4. Tobii SDK 每帧回调 `GazeService._gaze_data_callback(...)`，将 gaze 点、有效性、是否命中目标区域写入 `raw_gaze.jsonl`。
5. 后端检测到连续未命中目标达到阈值后，广播 `attention_feedback`。
6. 前端收到 `attention_feedback` 后触发对应目标的闪烁提示。
7. 目标消失时，前端发送 `box_visible: false`，后端清空当前 gaze task 的注意力区域。
8. 主任务结束时，`MessageHandler._gaze_stop(...)` 调用 `GazeService.stop_task(...)`，写入任务 summary 并结束 gaze task。

注意：`tobii_hand box_visible=true/false` 只表示目标区域出现或消失，不等同于任务开始或任务结束。

## 传感器任务

传感器任务的眼动区域来自天线调整提示框。

### 目标出现

传感器任务中，`useRadarData` 只有在 `enableAntennaRound` 为 true 的实例里处理天线眼动回合。天线提示框位置通过浏览器事件 `antenna-prompt-position` 传入。

天线任务当前发送的是 `display_area_normalized` 归一化坐标，不是屏幕原始像素。前端收到提示框的 CSS/viewport 坐标后，会除以 `window.innerWidth` 和 `window.innerHeight`，得到 0 到 1 的 `left/top/right/bottom`。

收到有效提示框坐标后：

1. `lastAntennaPromptPositionRef` 保存提示框坐标。
2. 如果当前没有 active antenna round，则打开一个独立 WebSocket。
3. WebSocket ready 后发送：

```json
{
  "type": "tobii_hand",
  "box_visible": true,
  "bbox": [[left, top, right, bottom]],
  "regions": [
    {
      "shape": "rect",
      "left": left,
      "top": top,
      "right": right,
      "bottom": bottom
    }
  ],
  "coordinate_space": "display_area_normalized",
  "task_source": "web",
  "task_name": "demo_task"
}
```

天线任务不会发送 `screen_data`，因为后端已经收到归一化后的 display area 坐标，不需要再用屏幕宽高换算。

### 目标消失

传感器任务中以下情况会发送目标消失：

- Radar 组件卸载。
- 页面刷新或关闭。
- 回合进行中又收到新的 `antennaAdjustmentRequired`，表示进入新一轮天线调整，需要提前结束旧回合。

发送格式：

```json
{
  "type": "tobii_hand",
  "box_visible": false,
  "task_id": "<后端返回的 gaze task id>",
  "bbox": [[left, top, right, bottom]],
  "regions": [
    {
      "shape": "rect",
      "left": left,
      "top": top,
      "right": right,
      "bottom": bottom
    }
  ],
  "coordinate_space": "display_area_normalized",
  "task_name": "demo_task"
}
```

如果前端还没有收到 `task_id`，会关闭本次回合连接并跳过带 `task_id` 的结束消息。

### 反馈效果

传感器任务收到后端 `attention_feedback` 后，`useRadarData` 调用 `handleAntennaStatusResponse(...)`。如果消息中有：

```json
{
  "type": "attention_feedback",
  "action": "flash_mode",
  "should_flash": true,
  "duration_ms": 3000
}
```

前端会派发 `antenna-prompt-attention` 事件，天线提示框按 `duration_ms` 闪烁。

## 威胁排序任务

威胁排序任务的眼动反馈现在只在 AI 启用时使用，目标为 AI 选中的威胁，而不是默认最高优先级目标。

### 目标出现

SA 页面收到临机事件后会设置 `beginSATobiiServe.current = true`，表示本轮允许启动 SA Tobii 回合。

AI 启用时，`useAIAgent(...)` 会根据 AI 等级配置延迟选择威胁。AI 选择会进入：

```ts
handleThreatIconClick(threat, 'AI')
```

在这个回调中：

1. `aiSelectedThreatRef.current = threat` 记录 AI 选中的目标。
2. 计算该目标在屏幕上的物理像素 bbox。
3. bbox 显式标注 `gazeCoordinateSpace: 'physical_pixel'`。
4. 调用 `startSaTobiiRound(promptPosition)` 打开 SA Tobii WebSocket。
5. 发送 `tobii_hand` 开始消息。

发送格式：

```json
{
  "type": "tobii_hand",
  "box_visible": true,
  "bbox": [[left, top, right, bottom]],
  "regions": [
    {
      "shape": "rect",
      "left": left,
      "top": top,
      "right": right,
      "bottom": bottom
    }
  ],
  "coordinate_space": "physical_pixel",
  "screen_data": [physical_screen_width, physical_screen_height],
  "task_source": "web",
  "task_name": "sa_highest_priority_threat_withAI"
}
```

虽然 `task_name` 保留为 `sa_highest_priority_threat_withAI`，当前实际目标区域取的是 AI 选中的威胁目标。

非 AI 模式下，SA 页面不会自动启动 SA Tobii 回合；即使用户手动选择目标，也不会对该目标启用 SA 眼动反馈。

### 目标消失

威胁排序任务中以下情况会发送目标消失：

- 点击“查看结果”。
- 页面刷新或关闭。
- SAPage 组件卸载。

结束时优先使用 AI 选中目标的位置作为 bbox。如果 AI 没有选中目标，则回退到最高优先级目标位置。

发送格式：

```json
{
  "type": "tobii_hand",
  "box_visible": false,
  "task_id": "<后端返回的 gaze task id>",
  "bbox": [[left, top, right, bottom]],
  "regions": [
    {
      "shape": "rect",
      "left": left,
      "top": top,
      "right": right,
      "bottom": bottom
    }
  ],
  "coordinate_space": "physical_pixel",
  "screen_data": [physical_screen_width, physical_screen_height],
  "task_name": "sa_highest_priority_threat_withAI"
}
```

### 反馈效果

SA 页面监听 `sa-highest-threat-attention` 事件。当前实现增加了两道限制：

- 必须 `agentStore.isAIActive === true`。
- 必须已经存在 `aiSelectedThreatRef.current`。

满足条件时，前端只让 AI 选中的目标闪烁。普通最高优先级目标不会因为眼动反馈而闪烁，除非它正好就是 AI 选中的目标。

## 后端处理

前端通过 WebSocket 发送 `tobii_hand`，后端统一走 `websocket_server._handle_tobii_hand(...)`。

### box_visible=true

后端读取：

- `bbox`
- `regions`
- `coordinate_space`
- `screen_data`
- 可选 `task_id`

然后调用：

```py
GazeService.set_task_bbox(
    bbox=bbox,
    screen_size=screen_data,
    task_id=task_id,
    regions=regions,
    coordinate_space=coordinate_space,
)
```

`GazeService.set_task_bbox(...)` 会：

1. 将 `regions/bbox` 归一化到 display area 坐标。
2. 检查请求的 `task_id` 是否匹配当前 active gaze task。
3. 更新 `_current_task["bbox"]` 和 `_current_task["regions"]`。
4. 清空未命中目标计数。
5. 关闭旧的 `gaze_targets` 记录。
6. 如果新 bbox 非空，插入一条新的 `gaze_targets` 出现记录。

### box_visible=false

后端调用 `set_task_bbox(...)`，传入空 bbox。效果是：

- 清空当前任务的注意力区域。
- 将当前未关闭的 `gaze_targets` 记录写入 `disappear_time_us`。
- gaze task 本身继续存在，直到主任务结果确认后由 `_gaze_stop(...)` 停止。

## 眼动采样与反馈判定

`GazeService` 连接 Tobii 后订阅 `EYETRACKER_GAZE_DATA`。每帧进入 `_gaze_data_callback(...)`。

每帧写入 `raw_gaze.jsonl`：

```json
{
  "ts_us": 1779250000000000,
  "task_id": "1",
  "user_id": "operator",
  "gaze": [0.421, 0.913],
  "valid": true,
  "in_region": true,
  "region_hits": ["region_1"]
}
```

无效 gaze 写成：

```json
{
  "ts_us": 1779250000000000,
  "task_id": "1",
  "user_id": "operator",
  "gaze": null,
  "valid": false,
  "in_region": false,
  "region_hits": []
}
```

反馈判定规则：

- gaze 有效并命中当前目标区域：清空未命中计数。
- gaze 有效但在目标区域外：累计未命中计数。
- gaze 无效：也累计未命中计数。
- 累计达到 `GAZE_OUT_OF_BOX_FALSE_THRESHOLD` 后触发反馈。

默认阈值：

```text
GAZE_OUT_OF_BOX_FALSE_THRESHOLD=200
```

这是帧数，不是毫秒。实际时间取决于 Tobii 采样率。

触发反馈时后端广播：

```json
{
  "ok": true,
  "type": "attention_feedback",
  "action": "flash_mode",
  "should_flash": true,
  "duration_ms": 3000,
  "reason": "consecutive_not_in_target",
  "consecutive_false_count": 200,
  "task_id": "1",
  "server_time_ms": 1779250000000
}
```

同时，反馈事件写入 SQLite 表 `gaze_feedback_events`。

## 坐标约定

前端发送区域时支持两种坐标：

- `display_area_normalized`：`left/top/right/bottom` 都是 0 到 1 的归一化坐标。
- `physical_pixel`：`left/top/right/bottom` 是物理像素坐标，必须配套 `screen_data`。

当前 SA 任务发送的是物理像素：

- SAPage 通过 DOM 位置、浏览器窗口位置和 `devicePixelRatio` 计算目标 bbox。
- payload 中显式带 `gazeCoordinateSpace: 'physical_pixel'`。
- `useRadarData` 将 `window.screen.width/height` 乘以 `devicePixelRatio` 后写入 `screen_data`。

后端最终会把物理像素区域除以 `screen_data`，归一化到 Tobii display area 坐标后再与 gaze 点比较。

当前传感器/天线任务发送的是归一化坐标：

- `antenna-prompt-position` 进入 `useRadarData` 后会转换成 `display_area_normalized`。
- payload 中 `coordinate_space` 为 `display_area_normalized`。
- 不发送 `screen_data`。
- 后端直接使用这些 0 到 1 的区域坐标与 Tobii gaze 点比较。
