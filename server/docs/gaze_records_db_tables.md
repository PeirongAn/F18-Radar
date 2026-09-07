# `gaze_records.db` 数据结构与代码写入链路

本文从代码实现角度说明 `gaze_records.db` 的结构：每张表由谁创建、
在什么业务事件下写入、字段之间如何关联，以及外部任务如何映射到眼动库。
本文不讨论当前数据库中的记录数量或统计分布。

主要代码入口：

- `server/tobii/gaze_service.py`：眼动任务、目标区域、提醒、Marker 和逐帧文件的核心实现；
- `server/network/platform_task_bridge.py`：外部任务到眼动任务及 Marker 的映射；
- `server/main.py`：创建 `GazeService`，并把服务注入 HTTP、WebSocket 和外部任务处理链路；
- 历史提交 `f173276` 中的 `server/tobii/gaze_service.py`：当前数据库里
  `gaze_aoi_snapshots` 表的建表和写入实现。当前 `gaze` 分支已不再包含这段 AOI 写入代码。

## 1. 整体存储模型

`GazeService` 同时维护三类状态：

```text
进程内状态
  _current_task
  _task_active
  当前帧数、有效帧数、命中帧数
  当前注意力区域

SQLite：gaze_records.db
  gaze_tasks
  gaze_targets
  gaze_feedback_events
  gaze_markers
  gaze_aoi_snapshots（历史 AOI 版本实现）

逐帧文件
  raw/{user_id}/{task_id}/raw_gaze.jsonl
```

SQLite 保存任务索引、生命周期和低频事件；每一帧的注视点不写入 SQLite，
而是写入 `raw_gaze.jsonl`。`gaze_tasks.data_dir` 是二者之间的文件索引。

表关系为：

```text
gaze_tasks.task_id
  ├─ gaze_targets.task_id
  ├─ gaze_feedback_events.task_id
  ├─ gaze_aoi_snapshots.task_id
  └─ gaze_markers.task_id        （代码逻辑关联，没有数据库外键）
```

`gaze_tasks` 是眼动库的中心表，但它表示“一次实际眼动任务/子任务”，
不是外部任务组。外部任务组及完整业务生命周期保存在
`radar_operations.db` 的 `task_groups`、`task_runs`、`task_events` 等表中。

## 2. 数据库初始化和异步写入机制

创建 `GazeService` 时，`__init__()` 会：

1. 根据 `data_dir` 得到 `_db_path = data_dir/gaze_records.db`；
2. 创建 `_writer_queue`；
3. 启动后台线程 `_run_writer()`。

后台线程负责实际文件和数据库写入：

```text
业务线程
  └─ _enqueue_db(sql, params)
       └─ 把 db_exec 放入 _writer_queue

Tobii 回调线程
  └─ 把 gaze_frame 放入 _writer_queue

后台 writer 线程
  ├─ SQLite 使用 WAL 模式
  ├─ 调用 _init_gaze_db() 幂等建表/补字段
  ├─ db_exec：执行 SQL 后 commit
  └─ gaze_frame：追加写入 raw_gaze.jsonl
```

因此 `start_task()`、`record_marker()`、`stop_task()` 返回时，SQL 通常只是已经
进入队列，并不等于此刻一定已经落盘。写入顺序由同一个 FIFO 队列保证。

当前 `_init_gaze_db()` 创建：

- `gaze_tasks`
- `gaze_targets`
- `gaze_feedback_events`
- `gaze_markers`

并通过 `_ensure_column()` 兼容补充 `gaze_tasks` 的历史字段。
`gaze_aoi_snapshots` 由曾启用动态 AOI 的代码版本创建；SQLite 不会因为当前代码
不再建表而自动删除已有表。

## 3. `gaze_tasks`：眼动任务生命周期主表

### 3.1 代码职责

`GazeService.start_task()` 创建任务，`stop_task()` 结束任务。

开始任务时，代码执行以下动作：

1. 把外部传入的 `task_id` 转成字符串；未提供时生成 UUID；
2. 构造 `raw/{user_id}/{task_id}` 目录；
3. 初始化 `_current_task`，帧计数从 0 开始；
4. 执行 `INSERT OR REPLACE INTO gaze_tasks`，状态写为 `active`；
5. 如果开始时已经提供注意力区域，同时插入一条 `gaze_targets`。

如果已有另一个活动任务，`start_task()` 会先以
`end_trigger = auto_closed_by_new_task` 调用 `stop_task()` 自动结束旧任务。

结束任务时，代码把内存中的帧统计一次性回写到 `gaze_tasks`，将状态改为
`completed`，随后关闭该任务的 `raw_gaze.jsonl` 文件句柄。

### 3.2 字段结构

| 字段 | 代码语义 |
| --- | --- |
| `id` | SQLite `AUTOINCREMENT` 代理主键，业务代码不使用它关联任务。 |
| `task_id` | 业务主键，TEXT、唯一。外部任务数字 ID 进入眼动服务后也会转成字符串。 |
| `user_id` | 调用方传入的用户/被试 ID。 |
| `task_source` | 调用来源或任务类别。普通任务可为 `manual`、`AI`；外部任务桥接层传入 `category`，例如 `platform_control`。 |
| `task_name` | 标准任务类型，例如 `RADAR_TARGETING`、`SA_THREAT_RESPONSE`、`PLATFORM_CONTROL`、`WEAPON_FIRING`。 |
| `data_dir` | 由 `_build_task_dir()` 生成的逐帧文件目录绝对路径。 |
| `start_time_us` | `start_task()` 使用的开始时间，微秒。 |
| `end_time_us` | `stop_task()` 使用的结束时间，微秒。活动任务为 `NULL`。 |
| `start_trigger` | 调用方提供的启动事件。普通任务通常是 `task_start`；外部子任务通常是 `sub_start`。 |
| `end_trigger` | 调用方提供的结束事件，例如 `sub_end`、`task_result_confirmed`、`task_end`、`auto_closed_by_new_task`。 |
| `duration_ms` | `stop_task()` 按 `(结束微秒 - 开始微秒) / 1000` 计算。 |
| `total_frames` | `_gaze_data_callback()` 在活动任务期间收到的总帧数，结束时统一写入。 |
| `valid_frames` | 合并注视点有效的帧数，结束时统一写入。 |
| `in_region_frames` | 命中当前注意力区域的帧数，对应 `gaze_targets` 和逐帧 `hit/hits` 语义。 |
| `status` | `start_task()` 写 `active`，`stop_task()` 写 `completed`。 |
| `created_at` | SQLite 插入该行的时间。 |

帧统计在任务运行过程中主要存在 `_current_task` 内存对象中，不会每帧更新 SQLite。
若进程异常退出而没有执行 `stop_task()`，数据库可能保留 `active` 状态和默认帧计数，
即使 `raw_gaze.jsonl` 已经写入了一部分帧。

## 4. `gaze_targets`：注意力检测区域的版本时间窗

### 4.1 代码职责

此表由 `start_task()`、`set_task_bbox()` 和 `stop_task()` 共同维护。

- `start_task()`：如果初始区域非空，插入第一条区域记录；
- `set_task_bbox()`：先关闭当前所有 `disappear_time_us IS NULL` 的区域记录，
  再在新区域非空时插入一条新记录；
- `stop_task()`：关闭仍未关闭的区域，并将 `auto_closed` 设为 1。

因此一行不是“一个矩形”，而是“一版区域集合在一段时间内有效”。
同一个 `task_id` 可以有多条连续的时间窗。

### 4.2 字段结构

| 字段 | 代码语义 |
| --- | --- |
| `id` | SQLite 自增主键。 |
| `task_id` | 所属眼动任务，声明外键到 `gaze_tasks.task_id`。 |
| `bbox_json` | 旧版原始区域兼容字段。当前代码插入新记录时写 `NULL`。 |
| `normalized_bbox_json` | `_normalize_regions()` 的输出 JSON，是当前注意力检测实际使用的区域集合。 |
| `screen_width` | 归一化时使用的屏幕宽度。 |
| `screen_height` | 归一化时使用的屏幕高度。 |
| `appear_time_us` | 该版区域开始生效的服务器时间。 |
| `disappear_time_us` | 该版区域被替换、清除或随任务结束的时间。未关闭时为 `NULL`。 |
| `auto_closed` | 只有 `stop_task()` 自动收尾未关闭区域时写为 1；正常区域更新关闭时保持 0。 |
| `created_at` | SQLite 插入时间。 |

`_gaze_data_callback()` 不查询该表。活动区域同时保存在
`_current_task["regions"]` 中，逐帧回调直接读取内存并调用 `_region_hits()`。
数据库中的 `gaze_targets` 是这段内存状态的历史记录。

## 5. `gaze_feedback_events`：注意力提醒事件

### 5.1 代码职责

`_gaze_data_callback()` 对每一帧执行：

1. 获取合并注视点及有效性；
2. 用 `_region_hits()` 判断是否命中当前注意力区域；
3. 无效注视或未命中时累计 `_consecutive_out_of_box_false`；
4. 达到 `OUT_OF_BOX_FALSE_THRESHOLD` 且满足冷却时间时，调用
   `_push_attention_feedback()`；
5. `_push_attention_feedback()` 向前端广播提醒，并插入本表。

如果当前任务没有注意力区域，代码会清空连续未命中状态，不产生提醒。

### 5.2 字段结构

| 字段 | 代码语义 |
| --- | --- |
| `id` | SQLite 自增主键。 |
| `task_id` | 触发提醒的活动任务，声明外键到 `gaze_tasks.task_id`。 |
| `event_time_ms` | `_push_attention_feedback()` 生成的服务器时间，毫秒。此表使用毫秒，不是微秒。 |
| `reason` | 当前代码固定为 `consecutive_not_in_target`。 |
| `consecutive_false_count` | 触发时连续无效/未命中的累计帧数。 |
| `threshold` | 触发时的 `OUT_OF_BOX_FALSE_THRESHOLD` 配置值。 |
| `payload_json` | 经 `_sanitize_feedback_payload()` 处理后的前端广播负载。 |
| `created_at` | SQLite 插入时间。 |

本表只记录已触发的提醒，不记录每一帧为何未命中。逐帧有效性和 `hit` 状态在
`raw_gaze.jsonl` 中。

## 6. `gaze_markers`：离散业务事件

### 6.1 代码职责

`GazeService.record_marker()` 用于把业务事件放到眼动时间轴上。它会：

1. 校验 `name` 非空；
2. 生成唯一 `marker_id`；
3. 对 `payload` 调用 `_sanitize_marker_payload()`；
4. 如果有活动任务，使用活动任务 ID，并拒绝与活动任务不一致的显式 `task_id`；
5. 插入 `gaze_markers`。

没有活动任务时也允许记录 Marker，所以本表没有声明到 `gaze_tasks` 的外键，
`task_id` 和 `user_id` 也允许为空字符串。

`_sanitize_marker_payload()` 会从 JSON 中删除已经由独立列承载的重复键：

```text
task_id, user_id, event_type, gaze_task_id,
timestamp, timestamp_ms, timestamp_us
```

因此分析最终数据库时，应从 `gaze_markers.task_id`、`user_id`、`name`、
`event_time_us` 读取这些信息，而不是要求 `payload_json` 再保存一份。

### 6.2 字段结构

| 字段 | 代码语义 |
| --- | --- |
| `id` | SQLite 自增主键。 |
| `marker_id` | `uuid.uuid4().hex` 生成的唯一 Marker ID。 |
| `task_id` | Marker 绑定的眼动任务 ID；允许为空。 |
| `user_id` | Marker 绑定的用户 ID；允许为空。活动任务存在时可从任务上下文补齐。 |
| `name` | 事件名称，例如 `sub_start`、`sub_end`、`task_result`。代码不把它限制为固定枚举。 |
| `event_time_us` | Marker 业务时间，微秒。 |
| `payload_json` | 事件上下文 JSON。结构由上层调用方定义。 |
| `created_at` | SQLite 插入时间。 |

## 7. 外部任务如何写入眼动库

眼动库没有单独的 `external_tasks` 表。外部任务通过
`platform_task_bridge.py` 映射到 `gaze_tasks` 和 `gaze_markers`。

### 7.1 外部子任务开始

`_start_external_subtask_context()` 为每个实际子任务生成独立 `task_id`，并保存到：

```text
active["task_id"]
active["current_subtask_task_id"]
```

同一个 ID 先写入 `radar_operations.db.task_runs`，随后
`_start_external_marker_context()` 调用：

```python
gaze_svc.start_task(
    bbox=[],
    screen_size=None,
    task_id=gaze_task_id,
    user_id=user_id,
    task_source=category,
    task_name=task_type,
    system_time=timestamp_ms * 1000,
    start_trigger=event_type,
)
```

因此外部任务在 `gaze_tasks` 中的结构是：

| `gaze_tasks` 字段 | 外部任务来源 |
| --- | --- |
| `task_id` | 当前实际子任务的 `current_subtask_task_id`，同时对应主库 `task_runs.task_id`。 |
| `user_id` | 外部消息解析出的用户/平台任务标识。 |
| `task_source` | 外部任务类别 `category`，例如 `platform_control`。 |
| `task_name` | 标准化任务类型 `task_type`。 |
| `start_time_us` | 外部消息毫秒时间戳乘以 1000。 |
| `start_trigger` | 外部事件名，通常是 `sub_start`；总任务首次启动也会作为第一个真实子任务。 |

开始眼动任务后，桥接层立即调用 `record_marker()` 写一条开始 Marker。

### 7.2 外部 Marker 负载

`_external_marker_payload()` 首先构造完整事件对象，随后
`GazeService.record_marker()` 会调用 `_sanitize_marker_payload()` 删除与独立列重复的键。
最终持久化结构如下：

| 数据位置 | 来源/含义 |
| --- | --- |
| `gaze_markers.task_id` | 实际绑定的眼动任务 ID。由活动 `gaze_task_id` 或当前外部子任务 ID 决定。 |
| `gaze_markers.user_id` | 外部用户标识。 |
| `gaze_markers.name` | `sub_start`、`sub_end` 等 `event_type`。 |
| `gaze_markers.event_time_us` | 外部事件毫秒时间戳乘以 1000。 |
| `payload_json.source` | 固定为 `F18-Radar`。 |
| `payload_json.task_type` | 标准任务类型。 |
| `payload_json.task_category` | 外部任务类别。 |
| `payload_json.platform_task_id` | 外部消息中的平台任务/用户标识。 |
| `payload_json.sub_task_seq` | 当前子任务序号。 |
| `payload_json.expected_subtasks` | 预计子任务数量。 |
| `payload_json.completed_subtasks` | 已完成子任务数量。 |
| `payload_json.message` | 原始外部业务消息对象。 |
| `payload_json.external_task_id` | `_record_external_gaze_marker()` 补入的当前外部子任务 ID；该键不会被清理。 |

构造阶段的 `task_id`、`user_id`、`event_type`、`gaze_task_id`、
`timestamp_ms` 和 `timestamp_us` 会在入库前从 `payload_json` 删除，
因为它们已经分别由 Marker 独立列承载。

外部任务身份不是由某一个布尔字段判断，而是由
`gaze_tasks.task_source/task_name/start_trigger` 与 Marker 中的
`task_id` 列、`task_category` 和 `external_task_id` 共同表达。

### 7.3 外部子任务结束

`_stop_external_marker_context()` 的顺序是：

```text
先 _emit_external_marker(...)
  └─ gaze_svc.record_marker(event_type, payload)

再 _stop_external_gaze_task(...)
  └─ gaze_svc.stop_task(task_id=gaze_task_id, end_trigger=event_type)
```

所以结束 Marker 仍能绑定活动眼动任务，随后同一外部事件时间被用于更新
`gaze_tasks.end_time_us`、`duration_ms`、帧统计和 `status`。

外部任务的完整配置、任务组、运行状态、原始事件和结果仍以
`radar_operations.db` 为主；`gaze_records.db` 只保存与眼动采集时间轴有关的投影。

## 8. `gaze_aoi_snapshots`：历史动态分析 AOI 版本表

### 8.1 代码来源

当前 `gaze` 分支的 `GazeService` 不再创建或写入该表。当前数据库仍有此表，是因为
曾启用动态 AOI 的代码版本会在 `_init_gaze_db()` 中创建它，并通过
`set_analysis_aoi_snapshot()` 写入。

历史实现的写入逻辑是：

1. 只接受活动眼动任务，显式 `task_id` 必须匹配活动任务；
2. 把前端区域归一化到 `display_area_normalized`；
3. 对坐标系、显示信息、区域几何和语义绑定计算 SHA-256 `layout_signature`；
4. 签名未变化时不新增 revision；
5. 签名变化时关闭上一条 `valid_to_us IS NULL` 的快照；
6. 插入新 revision，并把 revision/regions/alignment 状态放入 `_current_task`；
7. 逐帧文件写入 `aoi_revision`，只有 `alignment_valid` 时才写 `aoi_hits`；
8. 任务结束时关闭最后一版快照。

这套分析 AOI 与 `gaze_targets` 完全独立：

- `gaze_targets` 决定注意力提醒及逐帧 `hit/hits`；
- `gaze_aoi_snapshots` 决定分析用 `aoi_revision/aoi_hits`；
- 更新分析 AOI 不应改变注意力提醒区域。

### 8.2 字段结构

| 字段 | 历史代码语义 |
| --- | --- |
| `id` | SQLite 自增主键。 |
| `snapshot_id` | 服务端为每一版布局生成的 UUID，唯一。 |
| `task_id` | 所属眼动任务，外键到 `gaze_tasks.task_id`。 |
| `trial_id` | 试次 ID；未提供时回退为活动 `task_id`。 |
| `task_group_id` | 任务组 ID，可为 `NULL`。 |
| `task_type` | 标准任务类型。 |
| `revision` | 同一任务内递增版本号，`task_id + revision` 唯一。 |
| `valid_from_us` | 本版开始生效的服务器微秒时间。 |
| `valid_to_us` | 下一版生效或任务结束时写入的失效时间。 |
| `change_reasons_json` | 前端提供的布局变化原因数组。 |
| `layout_signature` | 规范化布局的 SHA-256 签名，用于去重。 |
| `coordinate_space` | 存储坐标系，历史代码固定写 `display_area_normalized`。 |
| `display_json` | 屏幕、视口、像素比、全屏和对齐状态。 |
| `regions_json` | 带语义 ID、矩形、可见性和 binding 的 AOI 列表。 |
| `alignment_valid` | 当前显示环境能否与眼动坐标可靠对齐。 |
| `client_captured_at_ms` | 前端测量 DOM 布局的时间。 |
| `client_snapshot_id` | 前端快照请求 ID，用于请求/应答关联。 |
| `created_at` | SQLite 插入时间。 |

## 9. `sqlite_sequence`：SQLite 内部表

该表不是业务代码显式创建的。只要表使用 `INTEGER PRIMARY KEY AUTOINCREMENT`，
SQLite 就会用 `sqlite_sequence(name, seq)` 保存已经分配过的最大自增值。

业务代码不查询、不关联也不应修改该表。`seq` 不是当前行数，删除业务记录不会保证
它回退。

## 10. 逐帧文件与数据库字段的对应关系

`_gaze_data_callback()` 生成的基础帧结构为：

```json
{
  "ts_us": 1779250000000000,
  "gaze": [0.421, 0.913],
  "hit": true,
  "hits": ["region_1"]
}
```

随后 `_extract_tobii_raw_fields()` 补充设备时间戳、SDK 时间戳和左右眼原始字段。
这些帧通过 writer 线程追加到 `raw_gaze.jsonl`。

| 逐帧字段/结果 | 数据库对应结构 |
| --- | --- |
| `ts_us` | 用于和任务、target、Marker、AOI 的时间窗对齐，不单独写 SQLite。 |
| `gaze` 是否有效 | 累计到内存 `valid_frames`，任务结束后写 `gaze_tasks.valid_frames`。 |
| 每收到一帧 | 累计到 `total_frames`，任务结束后写 `gaze_tasks.total_frames`。 |
| `hit/hits` | 基于当前 `gaze_targets` 对应的内存区域；命中时累计 `in_region_frames`。 |
| `aoi_revision/aoi_hits` | 仅历史动态 AOI 实现写入，基于 `gaze_aoi_snapshots`。 |
| 连续无效或未命中 | 达到阈值后产生 `gaze_feedback_events`，不是逐帧逐条写库。 |

## 11. 结构层面的注意事项

- 时间单位并不统一：任务、target、Marker 和 AOI 主时间使用微秒；
  feedback 和前端快照时间使用毫秒；`duration_ms` 是时长。
- `created_at` 是 SQLite 写入时间，不是业务事件时间。
- JSON 字段只是 TEXT，字段级结构由调用代码维护，SQLite 不校验内部键。
- `gaze_targets`、`gaze_feedback_events`、`gaze_aoi_snapshots` 声明了外键，
  但当前 writer 连接没有显式执行 `PRAGMA foreign_keys = ON`。
- `gaze_markers` 有意不声明外键，以支持无活动任务时的 Marker。
- `INSERT OR REPLACE INTO gaze_tasks` 会在相同 `task_id` 下替换任务行；业务关联应始终
  使用 `task_id`，不要依赖自增 `id`。
- SQLite 与 `raw_gaze.jsonl` 由同一 writer 线程处理，但它们不是一个事务；
  异常退出时需要分别检查任务状态和逐帧文件。
