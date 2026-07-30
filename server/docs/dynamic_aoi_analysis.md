# 动态 AOI 采集、计算与验证说明

## 1. 文档目的

本文说明信任调控实验中七类 AOI（Area of Interest，兴趣区）的以下内容：

- 七类 AOI 在 RADAR 与 SA 界面中分别对应什么区域。
- AOI 边界如何从界面坐标转换为 Tobii 坐标。
- 哪些变化会产生新的 AOI 快照，哪些变化不会。
- WebSocket 请求和响应协议的完整结构。
- AOI 快照、原始眼动帧和任务事件分别存在哪里。
- `aoi_hits`、注视时长、注视次数、访问次数和扫视路径如何计算。
- 如何通过数据库、原始文件、离线分析器和人工操作验证实现。

本文描述的是当前代码的实际行为，可作为后续联调、实验验收和数据分析的统一口径。

相关实现：

```text
前端动态测量：src/hooks/useTrustAoiSnapshot.ts
AOI界面标记：src/components/Radar.tsx
             src/components/SAPage.tsx
             src/components/ThreatList.tsx
             src/components/TrustControlPanel.tsx
服务端协议：  server/network/websocket_server.py
             server/network/http_server.py
服务端存储：  server/tobii/gaze_service.py
离线分析：    server/statistics/aoi_gaze_statistics.py
```

---

## 2. 两套区域必须区分

系统同时存在两套用途不同的区域。

### 2.1 注意力提醒区域 `attention_regions`

注意力提醒区域沿用现有 `tobii_hand` 协议，由 GazeService 的 `regions/bbox` 管理。

它决定原始眼动帧中的：

```json
{
  "hit": true,
  "hits": ["antenna_prompt"]
}
```

并参与连续未注视判断和 `attention_feedback` 辉光提醒。

### 2.2 实验分析区域 `analysis_aoi_regions`

七类信任实验 AOI，以及平台控制/武器发射外部任务的四类 AOI，使用新增的
`tobii_aoi_snapshot` 协议管理。

它决定原始眼动帧中的：

```json
{
  "aoi_revision": 7,
  "aoi_hits": ["left_ai_target", "left_candidate_list"]
}
```

分析 AOI 只用于实验数据统计，不会触发注意力提醒，不改变辉光逻辑，也不修改原有 `hit/hits`。

因此验证时必须遵守：

```text
hit / hits
→ 注意力提醒区域结果

aoi_revision / aoi_hits
→ 七类实验 AOI 结果
```

不能使用 `hit=true` 作为“命中了某个实验 AOI”的依据。

---

## 3. 七类 AOI 的界面划分

七类 AOI 的稳定 ID 为：

```text
left_ai_target
left_candidate_list
right_ai_history_accuracy
right_recommendation
right_candidate_list
right_detail
right_comparison
```

所有试次、两类任务和两种信任界面模式都使用相同 ID。`standard` 与 `trust_support` 只改变视觉显著性，不改变 AOI 名称和统计口径。

平台控制和武器发射外部任务使用以下四个稳定 ID：

```text
TrustHistory
TrustStatePanel
SHOOT
Title
AIConfidence
HistoricalResultRecord
AIFlightTrajectory
```

其中 `AIConfidence`、`HistoricalResultRecord`、`AIFlightTrajectory` 是
`PLATFORM_CONTROL` HUD 当前使用的三个区域；其余 ID 继续兼容既有的
`PLATFORM_CONTROL` 和 `WEAPON_FIRING` 快照。外部任务生命周期会先以
当前具体子任务 `task_id` 启动眼动；AOI 消息中的 `task_id`、`trial_id`、
`task_group_id` 如果是空字符串，接入层会把它们视为未提供，其中
`task_id`/`trial_id` 自动绑定当前活动眼动任务，`task_group_id` 保存为 `null`。

### 3.1 区域总表

| AOI ID | 中文含义 | RADAR 对应区域 | SA 对应区域 | 可与其他区域重叠 |
| --- | --- | --- | --- | --- |
| `left_ai_target` | 左侧 AI 推荐目标 | AI 推荐目标中心的 48×48 像素透明矩形 | AI 推荐威胁中心的 56×56 像素透明矩形 | 是 |
| `left_candidate_list` | 左侧任务候选区 | 整个雷达候选目标显示区域 | SA 下方完整威胁/来袭列表 | 是，仅 RADAR 通常与推荐目标重叠 |
| `right_ai_history_accuracy` | 右侧 AI 等级统计准确率 | 右侧顶部独立的 AI 等级准确率波动曲线 | 同左 | 否 |
| `right_recommendation` | 右侧 AI 推荐摘要 | AI 推荐目标编号及推荐目标原始观测 | 同左 | 否 |
| `right_candidate_list` | 右侧候选摘要 | 右侧最多前5个候选目标摘要 | 右侧最多前5个候选威胁摘要 | 否 |
| `right_detail` | 右侧详情区 | TDC 聚焦详情或 Button3 人工复核详情 | 同左 | 否 |
| `right_comparison` | 右侧人机对比区 | 人工选择与 AI 推荐不一致时的证据对比 | 同左 | 否 |

### 3.2 `left_ai_target`

#### RADAR

区域是以当前 AI 推荐目标显示位置为中心的透明矩形：

```text
宽度：48 CSS px
高度：48 CSS px
中心：radarStore.targetDisplayPositions 中 AI 推荐目标的位置
```

只有同时满足以下条件时区域才存在并可见：

- 当前试次已经产生 AI 推荐。
- 推荐目标能够在雷达画面中找到有效显示位置。

#### SA

区域是以当前 AI 推荐威胁显示位置为中心的透明矩形：

```text
宽度：56 CSS px
高度：56 CSS px
中心：fanThreatPositions 中 AI 推荐威胁的位置
```

目标移动导致透明矩形的位置变化时，会触发重新测量。

#### 与左侧候选区重叠

在 RADAR 中，`left_ai_target` 位于整个 `left_candidate_list` 内。因此眼动点落在推荐目标附近时可能同时记录：

```json
"aoi_hits": ["left_ai_target", "left_candidate_list"]
```

这不是重复数据错误，而是在保存“具体推荐目标”和“总体候选区”两个层级的命中。

### 3.3 `left_candidate_list`

#### RADAR

当前区域包围整个 `RadarDisplay` 外层容器，也就是左侧雷达候选目标显示区。它不是右侧文字列表。

该区域适合统计参与者在雷达任务区的总体注视情况。

#### SA

当前区域包围 SA 页面下方完整 `ThreatList` 容器，包括：

- 威胁列表。
- 来袭目标列表。
- 列表为空时的占位内容。

因此 SA 从空列表变成有数据、行数变化或容器尺寸改变时，仍使用同一个 AOI ID，只更新区域快照。

### 3.4 `right_ai_history_accuracy`

对应右侧信任调控面板最上方的独立 AI 等级统计准确率曲线区域。曲线在服务启动时根据 AI 等级的 `decision_probabilities` 和固定种子生成，同一次服务运行期间不随任务结果变化。

- 语义绑定包含 `metric = ai_statistical_accuracy`、当前 `ai_level` 和启动曲线 `curve_seed`。
- 曲线平均值、上下界和完整点列由服务端 `trust_control` 提供，不复制到 AOI 快照。
- 离线分析独立输出该区域的注视点、注视时长、注视次数和扫视路径。

同一 AI 等级和种子下曲线保持稳定；AI 等级或服务启动种子变化时，语义绑定变化并产生新的 AOI 快照。任务难度不参与该曲线。

### 3.5 `right_recommendation`

对应历史准确率区域下方的 AI 推荐摘要，包含 AI 推荐目标编号和推荐目标原始观测。AI 推荐目标改变时，即使物理范围不变，`binding.target_id` 也会改变，因此会产生新的语义快照。

### 3.6 `right_candidate_list`

对应右侧候选目标摘要区。当前界面最多展示候选数组的前5项。

其语义绑定为当前候选 ID 的排序后集合：

```json
{
  "candidate_ids": ["target-1", "target-2", "target-3"]
}
```

候选集合改变时，即使区域大小不变，也会产生新的快照。

注意：这个区域过去误用了 `left_candidate_list`，当前已经修正为独立的 `right_candidate_list`。

### 3.7 `right_detail`

对应右侧 TDC/人工复核详情区，区域本身一直存在，但语义模式会变化。

| 模式 | 触发条件 | `binding.mode` | `binding.target_id` |
| --- | --- | --- | --- |
| 空详情 | 没有 TDC 聚焦且未人工复核 | `empty` | `null` |
| TDC 详情 | TDC 已聚焦候选目标 | `tdc_detail` | 当前聚焦目标 ID |
| 人工复核 | Button3 按住并存在 AI 推荐 | `manual_review` | 按下时固定的 AI 推荐目标 ID |

Button3 按下或松开、TDC 从一个目标切换到另一个目标，都会改变详情区的语义绑定。

### 3.8 `right_comparison`

对应人机证据对比区。

只有满足以下条件时才参与 AOI 命中：

```text
human_selection != ai_recommendation
```

人机一致时，该 DOM 区域仍可能以低透明度占位，但会设置：

```html
data-visible="false"
```

快照仍保存它的几何范围，但：

```json
"visible": false
```

服务端不会把它加入本版本的有效命中区域。

人机不一致时绑定示例：

```json
{
  "mode": "comparison",
  "ai_target_id": "target-2",
  "human_target_id": "target-4"
}
```

---

## 4. AOI 坐标是如何生成的

### 4.1 DOM 测量

前端通过以下属性找到 AOI 元素：

```html
data-gaze-aoi="right_detail"
```

每个元素使用：

```javascript
element.getBoundingClientRect()
```

读取相对于浏览器视口的：

```text
left
top
right
bottom
width
height
```

### 4.2 可见性判断

区域只有同时满足以下条件才标记为 `visible=true`：

- DOM 元素存在。
- `display` 不是 `none`。
- `visibility` 不是 `hidden`。
- 宽高均大于0。
- 没有显式设置 `data-visible="false"`。

找不到 DOM 元素时仍会在快照中保留该 AOI ID，但坐标为0且 `visible=false`，保证七类区域的数据结构稳定。

### 4.3 裁剪与物理像素量化

原始 DOM 边界先裁剪到当前视口：

```text
0 <= x <= viewportWidth
0 <= y <= viewportHeight
```

然后按照设备像素比量化到1个物理像素：

```text
quantizedCss = round(cssCoordinate × devicePixelRatio)
               ÷ devicePixelRatio
```

最后转换为 Tobii 整屏归一化坐标：

```text
normalizedLeft   = quantizedLeft   ÷ viewportWidth
normalizedTop    = quantizedTop    ÷ viewportHeight
normalizedRight  = quantizedRight  ÷ viewportWidth
normalizedBottom = quantizedBottom ÷ viewportHeight
```

归一化结果限制在 `[0, 1]`。

### 4.4 为什么要求固定单显示器全屏

Tobii 的 `gaze_point_on_display_area` 是相对于整块显示器的归一化坐标，而 DOM 坐标默认相对于浏览器视口。

只有浏览器视口和 Tobii 显示区域一致时，二者才能直接比较。因此正式实验要求：

```text
单显示器
全屏或Kiosk运行
浏览器视口缩放为1
窗口位于屏幕原点
```

### 4.5 `alignment_valid` 判定

前端按以下条件判断坐标是否有效：

```text
abs(innerWidth - screen.width) × DPR <= 2物理像素
abs(innerHeight - screen.height) × DPR <= 2物理像素
abs(screenX) × DPR <= 2物理像素
abs(screenY) × DPR <= 2物理像素
abs(visualViewport.scale - 1) <= 0.001
```

全部满足时：

```json
"alignment_valid": true
```

任一不满足时：

```json
"alignment_valid": false
```

坐标无效期间：

- AOI 快照仍然保存，用于记录异常发生的时间和布局。
- 原始 gaze 数据继续保存。
- 原始帧仍保存 `aoi_revision`。
- 不生成 `aoi_hits`，避免产生错误的区域命中结论。

---

## 5. 什么时候重新测量，什么时候真正存储

### 5.1 重新测量触发源

前端在以下情况下请求重新测量：

| 触发源 | 典型场景 | 初始 `change_reason` |
| --- | --- | --- |
| 试次启动 | 第一次获得有效信任试次 | `trial_started` |
| `ResizeObserver` | AOI 或面板宽高改变 | `geometry_changed` |
| `MutationObserver` | AOI 挂载、卸载、样式或 class 改变 | `geometry_changed` |
| `data-visible` 改变 | 人机对比显示/隐藏 | `visibility_changed` |
| 语义状态改变 | AI推荐、候选、TDC、人工复核、人工选择变化 | `semantic_binding_changed` |
| 窗口 resize | 窗口或屏幕布局变化 | `viewport_changed` |
| 页面/容器滚动 | AOI 相对视口位置变化 | `geometry_changed` |
| 全屏状态变化 | 进入或退出全屏 | `fullscreen_changed` |
| `visualViewport` 变化 | 页面缩放或视觉视口移动 | `viewport_changed`/`geometry_changed` |
| WebSocket 重连 | 服务端连接恢复 | `websocket_reconnected` |

`MutationObserver` 当前监听：

```text
document.body 子树的 childList
data-visible 属性
class 属性
style 属性
```

### 5.2 稳定帧判断

一次变化触发后不会立即写库。

处理流程：

```text
收到变化信号
→ requestAnimationFrame测量第1次
→ requestAnimationFrame测量第2次
→ 两次规范化结果完全一致
→ 允许发送
```

如果界面持续移动，无法得到连续两个相同结果，则从本轮测量开始最多等待100毫秒，发送当时最新快照。

### 5.3 发送频率限制

相邻两次发送至少间隔100毫秒：

```text
最大频率 = 10个快照/秒
```

这主要用于限制连续移动的 AI 推荐目标产生过多数据库记录。

### 5.4 前端签名去重

前端将以下数据组成规范对象：

```text
coordinate_space
display
按固定顺序排列的七个regions
每个region的visible、边界和binding
```

然后计算：

- 浏览器支持 `crypto.subtle` 时使用 SHA-256。
- 不支持时回退为 `fnv1a32`。

如果规范对象和上一次成功发送的内容一致，则不再发送。

### 5.5 服务端再次去重

服务端不直接信任客户端传入的 `layout_signature`，而是：

1. 校验 AOI ID。
2. 校验同一个快照中 AOI ID 不重复。
3. 将坐标标准化并裁剪到 `[0,1]`。
4. 按 AOI ID 排序。
5. 使用 SHA-256 重新计算服务端签名。

服务端签名和当前活动版本相同：

```json
"changed": false
```

不会关闭旧版本，也不会插入新记录。

签名不相同：

```json
"changed": true
```

会关闭旧版本并生成新的递增 `revision`。

### 5.6 会产生新版本的变化

以下任一变化会改变签名：

- AOI 移动或缩放达到至少1个物理像素。
- AOI `visible` 改变。
- AI 推荐目标 ID 改变。
- 候选 ID 集合改变。
- TDC 详情目标改变。
- 详情模式在 `empty/tdc_detail/manual_review` 之间改变。
- 人机对比显示状态或对比目标改变。
- 屏幕、视口、DPR、缩放、全屏或坐标有效性改变。

### 5.7 不会产生新版本的变化

如果区域、显示参数和语义绑定未改变，以下变化不会新增数据库记录：

- 辉光颜色变化。
- 闪烁透明度变化。
- 边框、阴影等不改变测量边界的动画。
- 相同数据导致的 React 重渲染。
- 同一 AI 等级、概率范围和曲线种子下重复渲染统计曲线，但区域边界与语义绑定未变化。
- 小于1个物理像素的坐标抖动。
- 收到重复请求但服务端规范化结果不变。

---

## 6. WebSocket 协议

### 6.1 请求消息

消息类型：

```text
tobii_aoi_snapshot
```

完整示例：

```json
{
  "type": "tobii_aoi_snapshot",
  "task_id": "42",
  "trial_id": "42",
  "task_group_id": "8",
  "task_type": "RADAR_TARGETING",
  "client_snapshot_id": "8de7ce55-09d0-4b95-87de-b6f4e86c26bd",
  "captured_at_ms": 1779250000000,
  "change_reasons": [
    "geometry_changed",
    "semantic_binding_changed"
  ],
  "layout_signature": "4be8f61e...",
  "coordinate_space": "display_area_normalized",
  "display": {
    "fullscreen": true,
    "alignment_valid": true,
    "viewport_width_css_px": 1920,
    "viewport_height_css_px": 1080,
    "screen_width_css_px": 1920,
    "screen_height_css_px": 1080,
    "screen_width_physical_px": 1920,
    "screen_height_physical_px": 1080,
    "screen_x_css_px": 0,
    "screen_y_css_px": 0,
    "device_pixel_ratio": 1,
    "visual_viewport_scale": 1
  },
  "regions": [
    {
      "id": "left_ai_target",
      "shape": "rect",
      "visible": true,
      "left": 0.245,
      "top": 0.380,
      "right": 0.270,
      "bottom": 0.424,
      "binding": {
        "target_id": "target-2"
      }
    },
    {
      "id": "left_candidate_list",
      "shape": "rect",
      "visible": true,
      "left": 0.031,
      "top": 0.126,
      "right": 0.650,
      "bottom": 0.921,
      "binding": {
        "candidate_ids": ["target-1", "target-2", "target-3"]
      }
    },
    {
      "id": "right_ai_history_accuracy",
      "shape": "rect",
      "visible": true,
      "left": 0.680,
      "top": 0.090,
      "right": 0.995,
      "bottom": 0.205,
      "binding": {
        "metric": "ai_statistical_accuracy",
        "ai_level": "L1",
        "curve_seed": 20260730
      }
    },
    {
      "id": "right_recommendation",
      "shape": "rect",
      "visible": true,
      "left": 0.680,
      "top": 0.205,
      "right": 0.995,
      "bottom": 0.400,
      "binding": {
        "target_id": "target-2"
      }
    },
    {
      "id": "right_candidate_list",
      "shape": "rect",
      "visible": true,
      "left": 0.680,
      "top": 0.400,
      "right": 0.995,
      "bottom": 0.540,
      "binding": {
        "candidate_ids": ["target-1", "target-2", "target-3"]
      }
    },
    {
      "id": "right_detail",
      "shape": "rect",
      "visible": true,
      "left": 0.680,
      "top": 0.540,
      "right": 0.995,
      "bottom": 0.720,
      "binding": {
        "mode": "manual_review",
        "target_id": "target-2"
      }
    },
    {
      "id": "right_comparison",
      "shape": "rect",
      "visible": false,
      "left": 0.680,
      "top": 0.720,
      "right": 0.995,
      "bottom": 0.835,
      "binding": {
        "mode": "hidden",
        "ai_target_id": "target-2",
        "human_target_id": "target-2"
      }
    }
  ]
}
```

### 6.2 顶层字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `type` | string | 固定为 `tobii_aoi_snapshot` |
| `task_id` | string/null | 当前 GazeService 活动任务 ID；非空时必须匹配，空字符串或缺省时使用活动任务 ID |
| `trial_id` | string/null | 当前试次 ID；空字符串或缺省时使用活动任务 ID |
| `task_group_id` | string/null | 当前任务组 ID；空字符串按 `null` 保存 |
| `task_type` | string | `RADAR_TARGETING`、`SA_THREAT_RESPONSE`、`PLATFORM_CONTROL` 或 `WEAPON_FIRING` |
| `client_snapshot_id` | string | 客户端本次请求唯一 ID，用于响应关联 |
| `captured_at_ms` | integer | 客户端测量完成时间，毫秒 |
| `change_reasons` | string[] | 本轮累计变化原因 |
| `layout_signature` | string | 客户端签名；服务端会独立重算 |
| `coordinate_space` | string | 当前固定为 `display_area_normalized` |
| `display` | object | 屏幕、视口、DPR和坐标质量 |
| `regions` | array | AOI 区域数组 |

### 6.3 区域字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 七类信任实验 AOI 或四类外部任务 AOI 之一 |
| `shape` | string | 当前前端固定为 `rect` |
| `visible` | boolean | 是否参与本版本命中计算 |
| `left/top/right/bottom` | number | `[0,1]` 整屏归一化边界 |
| `binding` | object | 当前区域展示对象或模式，不参与几何命中 |

### 6.4 成功响应

```json
{
  "type": "tobii_aoi_snapshot_result",
  "client_snapshot_id": "8de7ce55-09d0-4b95-87de-b6f4e86c26bd",
  "ok": true,
  "changed": true,
  "task_id": "42",
  "snapshot_id": "cb8dfca0-b7b6-45ef-b443-44632f7b02aa",
  "revision": 7,
  "layout_signature": "e180cb8c..."
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `client_snapshot_id` | 原样返回，便于前端确认是哪次请求 |
| `ok` | 服务端是否接受请求 |
| `changed` | 是否真的生成新版本 |
| `snapshot_id` | 服务端生成的快照 UUID |
| `revision` | 当前任务内递增版本号 |
| `layout_signature` | 服务端重新计算的签名 |

### 6.5 失败响应

无活动眼动任务：

```json
{
  "type": "tobii_aoi_snapshot_result",
  "ok": false,
  "msg": "no active gaze task"
}
```

任务 ID 不匹配：

```json
{
  "type": "tobii_aoi_snapshot_result",
  "ok": false,
  "msg": "task_id mismatch",
  "task_id": "当前服务端任务ID"
}
```

不支持或重复的 AOI ID 会返回对应校验错误。

前端收到失败响应后最多每1秒重试一次，连续自动重试上限为10次；WebSocket 重连或语义/布局再次变化时也会重新发送。

---

## 7. 数据库存储

数据库文件：

```text
server/data/gaze/gaze_records.db
```

AOI 快照表：

```text
gaze_aoi_snapshots
```

### 7.1 表字段

| 字段 | 含义 |
| --- | --- |
| `snapshot_id` | 服务端快照 UUID，唯一 |
| `task_id` | 眼动任务 ID |
| `trial_id` | 信任试次 ID |
| `task_group_id` | 任务组 ID |
| `task_type` | RADAR 或 SA 任务类型 |
| `revision` | 同任务内递增版本号 |
| `valid_from_us` | 该版本开始生效的服务端微秒时间 |
| `valid_to_us` | 该版本停止生效的服务端微秒时间 |
| `change_reasons_json` | 变化原因数组 |
| `layout_signature` | 服务端规范化签名 |
| `coordinate_space` | 坐标系，当前为 `display_area_normalized` |
| `display_json` | 屏幕、视口、DPR、全屏和坐标质量 |
| `regions_json` | 本版本的所有 AOI 区域和语义绑定 |
| `alignment_valid` | 1=坐标可用于命中，0=坐标无效 |
| `client_captured_at_ms` | 客户端测量时间 |
| `client_snapshot_id` | 客户端请求 ID |
| `created_at` | SQLite 写入时间 |

约束：

```text
snapshot_id唯一
(task_id, revision)唯一
同一活动任务最多一个valid_to_us为空的版本
```

### 7.2 版本切换

当新版本生效时，服务端使用同一个 `now_us`：

```text
旧版本.valid_to_us = now_us
新版本.valid_from_us = now_us
```

因此正常版本窗口应该首尾连续、不重叠。

任务结束时，最后一个未关闭版本使用任务结束时间关闭。

### 7.3 查询某任务全部快照

```sql
SELECT
    task_id,
    revision,
    valid_from_us,
    valid_to_us,
    alignment_valid,
    change_reasons_json,
    display_json,
    regions_json
FROM gaze_aoi_snapshots
WHERE task_id = '42'
ORDER BY revision;
```

### 7.4 查询未关闭快照

任务运行期间最多应返回一条，任务结束后应返回0条：

```sql
SELECT task_id, revision, valid_from_us
FROM gaze_aoi_snapshots
WHERE valid_to_us IS NULL;
```

### 7.5 验证版本时间连续

```sql
SELECT
    task_id,
    revision,
    valid_from_us,
    valid_to_us,
    LAG(valid_to_us) OVER (
        PARTITION BY task_id
        ORDER BY revision
    ) AS previous_valid_to_us
FROM gaze_aoi_snapshots
WHERE task_id = '42'
ORDER BY revision;
```

从第2条开始，应满足：

```text
previous_valid_to_us = valid_from_us
```

### 7.6 验证相邻重复签名

连续两条签名不应相同：

```sql
WITH ordered AS (
    SELECT
        task_id,
        revision,
        layout_signature,
        LAG(layout_signature) OVER (
            PARTITION BY task_id
            ORDER BY revision
        ) AS previous_signature
    FROM gaze_aoi_snapshots
)
SELECT *
FROM ordered
WHERE layout_signature = previous_signature;
```

正常应返回0条。非相邻版本允许重新回到历史布局，因此不能简单按全表签名重复判断错误。

---

## 8. 原始眼动帧

每个任务的逐帧数据位于：

```text
server/data/gaze/raw/{user_id}/{task_id}/raw_gaze.jsonl
```

### 8.1 同时命中提醒区域和分析 AOI

```json
{
  "ts_us": 1779250000000000,
  "gaze": [0.421, 0.913],
  "hit": true,
  "hits": ["antenna_prompt"],
  "aoi_revision": 7,
  "aoi_hits": ["left_ai_target", "left_candidate_list"],
  "left_eye": {},
  "right_eye": {}
}
```

### 8.2 未命中任何分析 AOI

当存在有效 AOI 版本但本帧没有命中时：

```json
{
  "aoi_revision": 7,
  "aoi_hits": []
}
```

空数组表示“已经使用版本7进行计算，但未命中”。

### 8.3 坐标对齐无效

```json
{
  "aoi_revision": 8
}
```

没有 `aoi_hits` 表示该版本 `alignment_valid=false`，本帧没有执行 AOI 命中计算。

它不同于：

```json
"aoi_hits": []
```

### 8.4 尚未收到任何 AOI 快照

如果帧中连 `aoi_revision` 都不存在，说明当时 GazeService 尚未安装分析 AOI 快照。常见原因：

- 旧格式历史数据。
- 试次界面尚未完成首次上报。
- 请求因任务 ID 不匹配被拒绝。

### 8.5 单帧命中判定

对矩形区域：

```text
left <= gaze.x <= right
AND
top <= gaze.y <= bottom
```

服务端只遍历当前版本中 `visible=true` 的区域。

一个点可以命中多个 AOI，所有命中 ID 都保存在 `aoi_hits`，不会只保留一个。

---

## 9. 默认分析时间窗

离线分析器优先从 `server/data/radar_operations.db` 的 `task_events` 查找：

```text
开始：最早的 ai_recommendation_shown
结束：最晚的 final_selection_confirmed
```

即：

```text
AI推荐展示
→ 人工最终选择确认
```

结果中标记：

```json
"source": "decision_window"
```

如果上述两个事件没有同时取得，回退为整个 GazeService 任务窗口：

```text
gaze_tasks.start_time_us
→ gaze_tasks.end_time_us
```

并标记：

```json
"source": "gaze_task_fallback"
```

验证结果时应优先检查 `analysis_window.source`，避免把整段任务数据误认为决策阶段数据。

---

## 10. 各项指标如何计算

离线分析器：

```text
server/statistics/aoi_gaze_statistics.py
```

默认参数：

```text
最大采样间隔：100 ms
I-VT速度阈值：30°/s
最短注视持续时间：100 ms
算法版本：aoi-ivt-v2
```

### 10.1 各区域原始注视点

对每个分析窗口内的帧，如果：

```text
AOI_ID in frame.aoi_hits
AND gaze != null
```

则保存：

```json
[ts_us, gaze_x, gaze_y, aoi_revision]
```

同一个重叠点会同时进入多个 AOI 的原始点列表。

### 10.2 有效采样数 `valid_sample_count`

```text
valid_sample_count(AOI)
= 每个包含该AOI ID的aoi_hits帧
```

它是采样帧数，不是注视次数。

### 10.3 注视时长 `dwell_ms`

对分析窗口内按时间排序的每个帧 `i`：

```text
raw_delta_us = frame[i+1].ts_us - frame[i].ts_us

delta_us = max(
    0,
    min(raw_delta_us, 100000)
)
```

如果当前帧命中 AOI：

```text
dwell_us(AOI) += delta_us
```

最终：

```text
dwell_ms = dwell_us / 1000
```

重要边界：

- 数据中断超过100毫秒时，单帧最多只累计100毫秒。
- 最后一帧没有下一帧，当前实现给最后一帧的间隔记0。
- 重叠帧的时长同时计入所有命中的 AOI，因此把所有 AOI 时长相加可能大于总决策时长。

### 10.4 区域访问次数 `visit_count`

访问次数使用逐帧进入事件计算，而不是 I-VT 注视事件：

```text
当前帧命中AOI
AND
上一帧未命中AOI
→ visit_count + 1
```

离开后再次进入会再计一次。

无效坐标版本或没有 `aoi_hits` 的帧会使上一帧命中集合变为空，因此恢复后重新进入可能产生新的 visit。

### 10.5 首次进入延迟 `first_entry_latency_ms`

```text
first_entry_latency_ms
= (第一次命中AOI的ts_us - 分析窗口start_us) / 1000
```

从未命中的 AOI 返回 `null`。

### 10.6 I-VT 注视识别

“注视次数”使用离线 I-VT 识别，不直接用 `aoi_hits` 连续段数量代替。

#### 输入条件

一个帧必须满足：

- `gaze` 有效。
- 至少一只眼的 `gaze_valid=true`。
- 至少一只眼的 `origin_valid=true`。
- 对应眼睛同时具有有限的 `gaze_user_mm` 和 `origin_user_mm` 三维坐标。

#### 单眼视线方向

```text
direction = normalize(gaze_user_mm - origin_user_mm)
```

双眼均有效时，对两只眼的单位方向求平均后再次归一化。

#### 相邻帧角速度

```text
angle_deg = acos(clamp(dot(direction1, direction2), -1, 1))

velocity_deg_s
= angle_deg / ((ts2_us - ts1_us) / 1000000)
```

#### 分段规则

以下任一情况切断当前候选注视段：

```text
相邻采样间隔 <= 0
相邻采样间隔 > 100 ms
角速度 > 30°/s
缺少有效三维视线方向
```

候选段持续时间满足：

```text
segment_end_us - segment_start_us >= 100000 us
```

才认定为一次 fixation。

### 10.7 重叠 AOI 的主归属

原始帧保留全部 `aoi_hits`，但一次 fixation 需要一个主 AOI 才能形成单一路径。

每帧主 AOI 选择规则：

1. 选择当前版本中归一化面积最小的命中 AOI。
2. 面积相同时按固定优先级。

固定优先级：

```text
left_ai_target
right_ai_history_accuracy
right_detail
right_comparison
right_recommendation
left_candidate_list
right_candidate_list
```

因此 RADAR 推荐目标附近同时命中：

```text
left_ai_target
left_candidate_list
```

时，主归属为面积更小的 `left_ai_target`。

一次 fixation 内部各帧的主 AOI 可能不同。当前实现按帧数最多的主 AOI作为该 fixation 的最终 AOI；数量相同时由首次达到最高计数的项目决定。

### 10.8 注视次数 `fixation_count`

```text
fixation_count(AOI)
= 最终主AOI等于该AOI的有效fixation数量
```

如果原始数据没有有效的三维 gaze/origin 字段：

- `dwell_ms`、`visit_count` 仍可计算。
- `fixation_count` 可能为0。
- 不能将0直接解释为参与者没有注视，应先检查原始眼动字段质量。

### 10.9 扫视路径 `scanpath`

对相邻两个有效 fixation 生成一条路径记录：

```text
from_fixation
to_fixation
from_aoi
to_aoi
start_us = 前一个fixation.end_us
end_us   = 后一个fixation.start_us
duration_ms
angular_distance_deg
from_centroid
to_centroid
```

其中：

```text
duration_ms
= max(0, next.start_us - previous.end_us) / 1000
```

角距离使用两个 fixation 的平均三维视线方向计算。

### 10.10 AOI 转移矩阵

对每一条 `scanpath`：

```text
transition_matrix[from_aoi][to_aoi] += 1
```

当前实现保留同一区域到同一区域的连续 fixation 转移，例如：

```json
{
  "right_detail": {
    "right_detail": 2,
    "left_ai_target": 1
  }
}
```

---

## 11. 离线分析器使用方法

### 11.1 分析全部任务

在项目根目录运行：

```powershell
server\.venv\Scripts\python.exe server\statistics\aoi_gaze_statistics.py
```

默认输出目录：

```text
server/data/gaze/derived/
```

每个任务生成：

```text
{task_id}_aoi_gaze.json
```

### 11.2 只分析指定任务

```powershell
server\.venv\Scripts\python.exe server\statistics\aoi_gaze_statistics.py `
  --task-id 42
```

可以重复提供 `--task-id`：

```powershell
server\.venv\Scripts\python.exe server\statistics\aoi_gaze_statistics.py `
  --task-id 42 `
  --task-id 43
```

### 11.3 输出汇总 CSV

```powershell
server\.venv\Scripts\python.exe server\statistics\aoi_gaze_statistics.py `
  --summary-csv server\data\gaze\derived\aoi_summary.csv
```

CSV 每行对应一个“任务 × AOI”，主要字段：

```text
task_id
user_id
task_name
aoi_id
valid_sample_count
dwell_ms
fixation_count
visit_count
first_entry_latency_ms
valid_frame_ratio
alignment_invalid_ms
algorithm_version
```

### 11.4 修改算法参数

```powershell
server\.venv\Scripts\python.exe server\statistics\aoi_gaze_statistics.py `
  --max-gap-ms 80 `
  --velocity-threshold-deg-s 35 `
  --min-fixation-ms 120
```

每份 JSON 都保存实际使用的算法版本和参数，因此不同参数输出可以追溯。

### 11.5 结果质量字段

| 字段 | 说明 |
| --- | --- |
| `legacy_format` | 没有 `gaze_aoi_snapshots` 时为 true |
| `frame_count` | 分析窗口内总帧数 |
| `valid_frame_count` | `gaze != null` 的帧数 |
| `valid_frame_ratio` | 有效 gaze 帧比例 |
| `versioned_frame_count` | 包含 `aoi_revision` 的帧数 |
| `versioned_frame_ratio` | 已关联 AOI 版本的帧比例 |
| `alignment_invalid_ms` | 坐标对齐无效时长 |
| `fixation_input` | 当前固定为 `per_eye_3d_gaze_ray` |

推荐的数据验收最低要求：

```text
legacy_format = false
versioned_frame_ratio 接近1
alignment_invalid_ms = 0
valid_frame_ratio 满足实验设备质量要求
```

---

## 12. 人工验证用例

### 12.1 前置条件

1. 启动后端并确认 Tobii GazeService 已连接。
2. 浏览器置于实验使用的单显示器。
3. 进入全屏或 Kiosk。
4. 浏览器缩放恢复为100%。
5. 启动包含 AI 的 RADAR 或 SA 正式试次。
6. 打开浏览器开发者工具的 Network → WS → Frames。

### 12.2 首次快照

操作：等待 AI 推荐和右侧面板出现。

预期：

- WS 出现 `tobii_aoi_snapshot`。
- `regions` 包含七个稳定 ID。
- 服务端返回 `ok=true`、`changed=true`、`revision=1`。
- 数据库新增一条 `revision=1`。

### 12.3 重复渲染不新增版本

操作：不改变目标、TDC、窗口和页面，仅等待界面刷新。

预期：

- 不持续产生数据库记录。
- 相邻快照频率不会超过10次/秒。
- 相同规范布局被前端或服务端去重。

### 12.4 RADAR 推荐目标移动

操作：等待 AI 推荐目标在雷达显示位置发生明显变化。

预期：

- 新快照 `revision` 增加。
- `left_ai_target` 边界改变。
- `left_candidate_list` 通常保持不变。
- `binding.target_id` 在推荐对象未改变时保持一致。

### 12.5 TDC 详情切换

操作：先聚焦目标1，再聚焦目标2。

预期：

- `right_detail.binding.mode = tdc_detail`。
- `target_id` 从目标1变为目标2。
- 即使详情区矩形大小不变，也生成新的语义版本。

### 12.6 Button3 人工复核

操作：按住 Button3，再松开。

按下时预期：

```json
{
  "id": "right_detail",
  "binding": {
    "mode": "manual_review",
    "target_id": "AI推荐目标ID"
  }
}
```

松开时预期：

- `mode` 恢复为 `tdc_detail` 或 `empty`。
- 推荐目标辉光闪烁动画本身不应每帧产生 AOI 数据库记录。

### 12.7 人机不一致对比

操作：人工选择一个不同于 AI 推荐的目标。

预期：

- `right_comparison.visible` 从 false 变为 true。
- `binding.mode = comparison`。
- 同时保存 AI 和人工目标 ID。
- 产生新版本。

重新选择 AI 推荐目标后预期：

- `right_comparison.visible=false`。
- 后续原始帧不再命中 `right_comparison`。

### 12.8 退出全屏

操作：正式试次中退出全屏。

预期：

- 新快照 `alignment_valid=false`。
- 数据库 `alignment_valid=0`。
- 原始帧仍有 `aoi_revision`。
- 原始帧没有 `aoi_hits`。
- 重新全屏后产生 `alignment_valid=true` 的新版本。

### 12.9 重叠命中

操作：让注视点落在 RADAR AI 推荐目标中心附近。

预期原始帧可能为：

```json
{
  "aoi_hits": [
    "left_ai_target",
    "left_candidate_list"
  ]
}
```

离线 fixation 主归属应优先为面积更小的 `left_ai_target`。

### 12.10 任务结束

操作：正常完成并确认试次。

预期：

- `gaze_aoi_snapshots` 中该任务最后一个版本的 `valid_to_us` 不为空。
- `raw_gaze.jsonl` 正常关闭并可读取。
- 离线分析器能够生成任务 JSON。

---

## 13. 推荐验收 SQL 和命令

### 13.1 查看最近20个 AOI 快照

```powershell
server\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(r'server/data/gaze/gaze_records.db'); [print(r) for r in c.execute('SELECT task_id,revision,valid_from_us,valid_to_us,alignment_valid,change_reasons_json FROM gaze_aoi_snapshots ORDER BY id DESC LIMIT 20')]"
```

### 13.2 查看某任务原始帧末尾

先查询任务目录：

```sql
SELECT data_dir
FROM gaze_tasks
WHERE task_id = '42';
```

再执行：

```powershell
Get-Content "查询得到的目录\raw_gaze.jsonl" -Tail 20
```

重点检查：

```text
ts_us
gaze
hit/hits
aoi_revision
aoi_hits
left_eye/right_eye
```

### 13.3 运行指定任务分析

```powershell
server\.venv\Scripts\python.exe server\statistics\aoi_gaze_statistics.py `
  --task-id 42 `
  --summary-csv server\data\gaze\derived\task_42_summary.csv
```

### 13.4 自动化测试

```powershell
server\.venv\Scripts\python.exe -m pytest `
  server\tests\test_gaze_markers.py `
  server\tests\test_aoi_gaze_statistics.py -q
```

测试覆盖：

- 注意力区域与分析 AOI 相互独立。
- 相同快照去重。
- AOI 版本递增和时间窗口关闭。
- 多区域同时命中。
- 坐标无效时不写 `aoi_hits`。
- 注视时长最大间隔限制。
- 重叠区域 fixation 主归属。

---

## 14. 常见问题定位

### 14.1 `gaze_aoi_snapshots` 没有数据

依次检查：

1. 当前试次是否启用了信任调控 `control.enabled`。
2. 前端是否存在有效 `taskId`。
3. GazeService 是否已经启动活动任务。
4. WS 是否发出了 `tobii_aoi_snapshot`。
5. 响应是否为 `no active gaze task`。
6. 请求 `task_id` 是否与 GazeService 活动任务一致。

### 14.2 有 `aoi_revision` 但没有 `aoi_hits`

优先查询对应快照：

```sql
SELECT alignment_valid, display_json
FROM gaze_aoi_snapshots
WHERE task_id='42' AND revision=7;
```

如果 `alignment_valid=0`，这是坐标质量保护，不是命中算法故障。

### 14.3 `aoi_hits=[]`

表示坐标有效、版本有效，但该眼动点未落入任何 `visible=true` 的 AOI。

### 14.4 快照数量异常多

检查：

- AI 推荐目标是否持续移动。
- 页面是否持续改变 AOI 元素的 `style/class`。
- 边界是否每次变化至少1个物理像素。
- 相邻签名是否真的不同。
- 每秒记录数是否超过10条。

### 14.5 `fixation_count=0` 但 `dwell_ms>0`

检查原始帧中的：

```text
left_eye.gaze_user_mm
left_eye.origin_user_mm
left_eye.gaze_valid
left_eye.origin_valid
right_eye对应字段
```

I-VT 依赖三维视线方向；普通 AOI 时长只依赖 `gaze` 和 `aoi_hits`，二者输入条件不同。

### 14.6 所有 AOI 时长相加大于决策时间

这是重叠 AOI 的正常结果。原始 dwell 对所有命中区域分别累计，例如推荐目标区域与整个雷达候选区会同时累计。

如果需要互斥时长，应使用 fixation 的主 AOI 或按照“最小面积优先”规则重新生成互斥统计。

---

## 15. 当前实现边界

- 正式实验假设单显示器全屏；窗口化或多显示器坐标不作为有效 AOI 数据。
- 当前前端生成的七类 AOI 都是矩形。
- 移动目标最多每100毫秒上报一次边界，极高速移动时采用最近快照近似。
- 原始帧保留全部重叠命中，离线 fixation 才选择单一主 AOI。
- 注视和扫视均为离线计算，运行时不生成 fixation 事件。
- 旧任务没有 `gaze_aoi_snapshots/aoi_revision`，分析结果会标记 `legacy_format=true`。
- 最后一帧的 dwell 增量当前为0，不根据历史中位采样间隔外推。
- `right_comparison` 在人机一致时虽然可能仍有视觉占位，但不作为有效分析 AOI。
- `layout_signature` 的权威值是服务端重算结果，客户端签名主要用于减少无效发送。

---

## 16. 验收结论模板

每次正式设备验收可以按以下格式记录：

```text
任务ID：
用户ID：
任务类型：RADAR / SA
界面模式：standard / trust_support
显示器分辨率：
DPR：
是否全屏：

首次AOI revision：
最后AOI revision：
未关闭快照数：
相邻重复签名数：
alignment_invalid_ms：
versioned_frame_ratio：
valid_frame_ratio：

left_ai_target命中：通过 / 不通过
left_candidate_list命中：通过 / 不通过
right_ai_history_accuracy独立命中与统计：通过 / 不通过
right_recommendation命中：通过 / 不通过
right_candidate_list命中：通过 / 不通过
right_detail模式切换：通过 / 不通过
right_comparison显隐切换：通过 / 不通过
Button3闪烁未造成快照洪泛：通过 / 不通过
任务结束关闭最后快照：通过 / 不通过
离线JSON生成：通过 / 不通过
汇总CSV生成：通过 / 不通过

异常说明：
验收人：
验收时间：
```
