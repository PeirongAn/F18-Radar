# 外部平台任务 WebSocket 协议

本文档定义了"平台控制"和"武器发射"两类外部平台任务与雷达服务端之间的 WebSocket 通信协议。

## 通信方式

WebSocket，与现有 radar/SA 任务共用同一连接。

## 通用字段

以下字段在所有生命周期消息中都需要（任务结果消息除外）：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| TaskName | string | 是 | 任务名称，用于区分任务类别。包含"平台"归为平台控制，包含"武器"/"发射"归为武器发射 |
| ID | string | 是 | 用户 ID |
| Action | string | 是 | 事件类型，见下方各消息定义 |
| Gender | string | 否 | 性别（"0"=女, "1"=男） |

> **注意：** 客户端无需存储任何会话信息（如 task_id），所有 ID 生成和关联由服务端负责。

---

## 消息类型

### 1) 整体任务开始

当一轮完整任务开始时发送。服务端收到后生成内部 task_id 并开始跟踪。

**请求：**

```json
{
  "TaskName": "平台任务",
  "ID": "12345",
  "Gender": "1",
  "DefaultControlMode": "0",
  "AIAutonomyLeve": "3",
  "TaskMode": "1",
  "Difficulty": "3",
  "TaskNumber": "3",
  "aiprecision": "1",
  "Action": "task_start"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| Action | string | 是 | 固定 `"task_start"` |
| DefaultControlMode | string | 否 | "0"=人工, "1"=AI |
| AIAutonomyLeve | string | 否 | AI 自主等级 |
| TaskMode | string | 否 | "0"=练习, "1"=正式 |
| Difficulty | string | 否 | 难度等级 |
| TaskNumber | string | 否 | 任务编号/轮数 |
| aiprecision | string | 否 | AI 精度 |

**响应：**

```json
{
  "type": "platform_task_ack",
  "status": "ok",
  "task_id": 42,
  "task_category": "platform_control"
}
```

---

### 2) 单个子任务开始

当一轮中的某个子任务开始时发送。服务端自动分配子任务序号（从 1 开始递增）。

**请求：**

```json
{
  "TaskName": "平台任务",
  "ID": "12345",
  "Action": "sub_start"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| Action | string | 是 | 固定 `"sub_start"` |
| TaskName | string | 是 | 需与 task_start 时一致 |
| ID | string | 是 | 需与 task_start 时一致 |

其余字段可选，如有则记录。

**响应：**

```json
{
  "type": "platform_task_ack",
  "status": "ok",
  "task_id": 42,
  "sub_task_seq": 1
}
```

---

### 3) 单个子任务结束

当一个子任务结束时发送。可以在 `result` 字段中附带该子任务的结果数据。

**请求：**

```json
{
  "TaskName": "平台任务",
  "ID": "12345",
  "Action": "sub_end",
  "result": {
    "CurrentRedcord": [
      {
        "CurrentTime": 27.04,
        "taskid": 0,
        "unitsid": 101,
        "Distance": 4434.36,
        "CurrentMode": "User"
      }
    ],
    "Fire": [
      {
        "FireResult": true,
        "CurrentTime": 5.28
      }
    ],
    "AITIME": {
      "AiRemindTime": 2.34
    },
    "AIcontrolTime": 10.31,
    "PersonControlTime": 18.95,
    "SwitchInfo": [
      {
        "Time": 2.93,
        "SwitchTo": "ToUser"
      }
    ]
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| Action | string | 是 | 固定 `"sub_end"` |
| TaskName | string | 是 | 需与 task_start 时一致 |
| ID | string | 是 | 需与 task_start 时一致 |
| result | object | 否 | 子任务结果数据，包含 CurrentRedcord、Fire、AITIME、AIcontrolTime、PersonControlTime、SwitchInfo |

**响应：**

```json
{
  "type": "platform_task_ack",
  "status": "ok",
  "task_id": 42,
  "sub_task_seq": 1
}
```

---

### 4) 整体任务结束（可选）

显式标记整体任务结束。如果不发送此消息，服务端会在收到任务结果时自动清除活跃状态。

**请求：**

```json
{
  "TaskName": "平台任务",
  "ID": "12345",
  "Action": "task_end"
}
```

**响应：**

```json
{
  "type": "platform_task_ack",
  "status": "ok",
  "task_id": 42,
  "event_type": "task_end"
}
```

---

### 5) 任务结果

整体任务结束后，发送任务结果数据。**格式与前面的生命周期消息不同**，需要加 `type` 字段。

**请求：**

```json
{
  "type": "platform_task_result",
  "ID": "12345",
  "CurrentRedcord": [
    {
      "CurrentTime": 27.04,
      "taskid": 0,
      "unitsid": 101,
      "Distance": 4434.36,
      "CurrentMode": "User"
    }
  ],
  "Fire": [
    {
      "FireResult": true,
      "CurrentTime": 5.28
    }
  ],
  "AITIME": {
    "AiRemindTime": 2.34
  },
  "AIcontrolTime": 10.31,
  "PersonControlTime": 18.95,
  "SwitchInfo": [
    {
      "Time": 2.93,
      "SwitchTo": "ToUser"
    }
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| type | string | 是 | 固定 `"platform_task_result"` |
| ID | string | 是 | 用户 ID，用于关联到对应的活跃任务 |
| CurrentRedcord | array | 是 | 控制记录快照（平台控制任务有数据，武器发射任务可为空） |
| Fire | array | 是 | 开火记录（武器发射任务有数据，平台控制任务可为空） |
| AITIME | object | 是 | AI 提醒时间 |
| AIcontrolTime | number | 是 | AI 控制总时长（秒） |
| PersonControlTime | number | 是 | 人工控制总时长（秒） |
| SwitchInfo | array | 是 | 人机切换记录 |

**响应：**

```json
{
  "type": "platform_task_ack",
  "status": "ok",
  "task_id": 42,
  "event_type": "task_result"
}
```

---

## 武器发射任务示例

武器发射任务与平台控制任务使用相同的协议，区别在于 `TaskName` 包含"武器"/"发射"等关键词，结果数据中 `Fire` 有数据而 `CurrentRedcord` 为空。

### 整体任务开始

```json
{
  "TaskName": "武器发射任务",
  "ID": "12345",
  "Gender": "1",
  "DefaultControlMode": "1",
  "AIAutonomyLeve": "2",
  "TaskMode": "1",
  "Difficulty": "2",
  "TaskNumber": "5",
  "aiprecision": "1",
  "Action": "task_start"
}
```

响应中 `task_category` 为 `"weapon_launch"`：

```json
{
  "type": "platform_task_ack",
  "status": "ok",
  "task_id": 43,
  "task_category": "weapon_launch"
}
```

### 子任务开始 / 结束

```json
{
  "TaskName": "武器发射任务",
  "ID": "12345",
  "Action": "sub_start"
}
```

```json
{
  "TaskName": "武器发射任务",
  "ID": "12345",
  "Action": "sub_end",
  "result": {
    "CurrentRedcord": [],
    "Fire": [
      {
        "FireResult": true,
        "CurrentTime": 5.28
      }
    ],
    "AITIME": {
      "AiRemindTime": 2.34
    },
    "AIcontrolTime": 9.50,
    "PersonControlTime": 0,
    "SwitchInfo": []
  }
}
```

### 独立任务结果（可选，与 sub_end 中的 result 二选一）

```json
{
  "type": "platform_task_result",
  "ID": "12345",
  "CurrentRedcord": [],
  "Fire": [
    {
      "FireResult": true,
      "CurrentTime": 5.28
    }
  ],
  "AITIME": {
    "AiRemindTime": 2.34
  },
  "AIcontrolTime": 9.50,
  "PersonControlTime": 0,
  "SwitchInfo": []
}
```

### 两类任务结果数据对比

| 字段 | 平台控制 | 武器发射 |
|---|---|---|
| CurrentRedcord | 有数据（控制记录快照） | 通常为空 `[]` |
| Fire | 通常为空 `[]` | 有数据（开火记录，含 FireResult 和 CurrentTime） |
| AIcontrolTime | AI 控制总时长 | AI 控制总时长 |
| PersonControlTime | 人工控制总时长 | 人工控制总时长（可能为 0） |
| SwitchInfo | 有数据（人机切换记录） | 通常为空 `[]` |
| AITIME.AiRemindTime | 通常为 0 | 有数据（AI 提醒时间） |

---

## 错误响应

当消息校验失败时，服务端返回：

```json
{
  "type": "platform_task_ack",
  "status": "error",
  "message": "错误描述"
}
```

常见错误场景：
- 缺少必填的 `ID` 字段
- `sub_start` / `sub_end` 时找不到对应的活跃任务（未先发送 `task_start`）
- 未知的 `Action` 值

---

## 典型调用时序

### 平台控制任务

```
客户端                              服务端
  |                                   |
  |-- task_start (平台任务) --------->|  生成 task_id=42, 开始跟踪
  |<--------- ack (task_id=42) ------|
  |                                   |
  |-- sub_start ---------------------->|  sub_task_seq=1
  |<--------- ack (seq=1) ------------|
  |                                   |
  |-- sub_end (带 result) ----------->|  记录 seq=1 结束 + 结果
  |<--------- ack (seq=1) ------------|
  |                                   |
  |-- sub_start ---------------------->|  sub_task_seq=2
  |<--------- ack (seq=2) ------------|
  |                                   |
  |-- sub_end (带 result) ----------->|  记录 seq=2 结束 + 结果
  |<--------- ack (seq=2) ------------|
  |                                   |
```

### 武器发射任务

```
客户端                              服务端
  |                                   |
  |-- task_start (武器发射任务) ----->|  生成 task_id=43, 开始跟踪
  |<--------- ack (task_id=43) ------|
  |                                   |
  |-- sub_start ---------------------->|  sub_task_seq=1
  |<--------- ack (seq=1) ------------|
  |                                   |
  |-- sub_end (带 result) ----------->|  记录 seq=1 结束 + 开火结果
  |<--------- ack (seq=1) ------------|
  |                                   |
  |-- sub_start ---------------------->|  sub_task_seq=2
  |<--------- ack (seq=2) ------------|
  |                                   |
  |-- sub_end (带 result) ----------->|  记录 seq=2 结束 + 开火结果
  |<--------- ack (seq=2) ------------|
  |                                   |
```

---

## 服务端存储

所有事件和结果统一存入 `platform_external_tasks` 表，通过 `task_id` 关联同一轮任务的全部记录。

| event_type | sub_task_seq | 说明 |
|---|---|---|
| task_start | NULL | 整体任务开始 |
| sub_start | 1 | 第 1 个子任务开始 |
| sub_end | 1 | 第 1 个子任务结束 |
| sub_start | 2 | 第 2 个子任务开始 |
| sub_end | 2 | 第 2 个子任务结束 |
| task_result | NULL | 结果数据（含提取的关键指标） |

---

## 问卷提交

任务结束后需要收集被试的信任度问卷。四类任务的问卷入口不同：

| 任务类型 | 问卷入口 | 说明 |
|---|---|---|
| 传感器操作 (`RADAR_TARGETING`) | React Modal | 由前端 `QuestionnaireModal` 组件弹出，通过 WebSocket 提交 |
| 威胁排序 (`SA_THREAT_RESPONSE`) | React Modal | 同上 |
| 平台控制 (`PLATFORM_CONTROL`) | HTML 页面 URL | 独立页面，外部平台在任务结束后打开此 URL |
| 武器发射 (`WEAPON_FIRING`) | HTML 页面 URL | 同上 |

### 问卷页面 URL（平台控制 / 武器发射）

外部平台在任务结束后，通过浏览器打开以下 URL 让被试填写问卷：

```
http://<server>:8080/questionnaire.html?userId=<用户ID>&taskType=<任务类型>&difficulty=<难度>&autonomyLevel=<自主等级>&isPractice=<是否练习>&experimentNo=<当前序号>&total=<总数>
```

**参数说明：**

| 参数 | 类型 | 必填 | 说明 | 可选值 |
|---|---|---|---|---|
| userId | string | 是 | 被试 ID，应与 task_start 中的 `ID` 一致 | 如 `12345` |
| taskType | string | 是 | 任务类型常量 | `PLATFORM_CONTROL` / `WEAPON_FIRING` |
| difficulty | string | 否 | 任务难度 | `low` / `medium` / `high` |
| autonomyLevel | string | 否 | AI 自主等级，对应平台字段 `AIAutonomyLevel` / `AIAutonomyLeve`。页面也兼容直接传 `AIAutonomyLevel` / `AIAutonomyLeve` | `L0` / `L1` / `L2` 或 `1` / `2` / `3` |
| isPractice | string | 否 | 是否练习模式 | `true` / `false` |
| experimentNo | string | 否 | 当前实验序号 | 如 `3` |
| total | string | 否 | 总实验数 | 如 `10` |
| q1 ~ q7 | string | 否 | 预填答案（1=非常不同意，5=非常同意） | `1` ~ `5` |

**平台控制任务示例：**

```
http://localhost:8080/questionnaire.html?userId=12345&taskType=PLATFORM_CONTROL&difficulty=high&autonomyLevel=L2&isPractice=false&experimentNo=3&total=10
```

**武器发射任务示例：**

```
http://localhost:8080/questionnaire.html?userId=12345&taskType=WEAPON_FIRING&difficulty=medium&autonomyLevel=L1&isPractice=false&experimentNo=5&total=10
```

### 问卷提交方式

问卷页面提交时优先使用 WebSocket，若 WebSocket 不可用则 fallback 到 HTTP 接口。

#### 方式一：WebSocket（自动）

页面与服务端 `/ws` 保持 WebSocket 连接，提交时发送：

```json
{
  "type": "questionnaire_submitted",
  "taskType": "PLATFORM_CONTROL",
  "userId": "12345",
  "repetitionCurrent": 3,
  "repetitionTotal": 10,
  "answers": { "1": 5, "2": 4, "3": 3, "4": 4, "5": 5, "6": 3, "7": 4 },
  "taskInfo": {
    "difficulty": "high",
    "autonomyLevel": "L2",
    "isPractice": false
  },
  "timestamp": 1712567890123,
  "source": "html_page"
}
```

服务端返回：

```json
{
  "type": "questionnaire_saved",
  "ok": true,
  "msg": "问卷已保存"
}
```

#### 方式二：HTTP POST（fallback）

当 WebSocket 不可用时，页面自动 fallback 到 HTTP 接口：

```
POST /api/questionnaire
Content-Type: application/json
```

请求体与 WebSocket 消息体一致（不含 `type` 字段）。

**响应：**

```json
{
  "ok": true,
  "msg": "问卷已保存"
}
```

### 问卷数据存储

问卷数据存入 `questionnaire_responses` 表：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER | 自增主键 |
| user_id | TEXT | 被试 ID |
| task_type | TEXT | 任务类型（`PLATFORM_CONTROL` / `WEAPON_FIRING` / `RADAR_TARGETING` / `SA_THREAT_RESPONSE`） |
| repetition_current | INTEGER | 当前实验序号 |
| repetition_total | INTEGER | 总实验数 |
| difficulty | TEXT | 任务难度 |
| autonomy_level | TEXT | AI 自主等级（`L0` / `L1` / `L2`） |
| is_ai_active | BOOLEAN | 兼容旧数据字段；新问卷对外使用 `autonomy_level` |
| is_practice | BOOLEAN | 是否练习 |
| answers_json | TEXT | 答案 JSON，如 `{"1":5,"2":4,...}` |
| source | TEXT | 来源标识：`html_page` / `websocket` / `react_modal` / `http_api` |
| client_timestamp | INTEGER | 客户端提交时间戳（ms） |
| created_at | TIMESTAMP | 服务端入库时间 |

### 典型调用时序（含问卷）

```
外部平台客户端                        服务端                          浏览器
  |                                   |                               |
  |-- task_start (平台任务) --------->|                               |
  |<--------- ack (task_id=42) ------|                               |
  |                                   |                               |
  |-- sub_start --------------------->|                               |
  |-- sub_end (带 result) ----------->|                               |
  |                                   |                               |
  |-- task_end ---------------------->|                               |
  |<--------- ack -------------------|                               |
  |                                   |                               |
  |  打开问卷 URL -------------------------------------------------->|
  |  questionnaire.html?userId=12345&taskType=PLATFORM_CONTROL&...   |
  |                                   |                               |
  |                                   |<-- questionnaire_submitted ---|  (WS 或 HTTP)
  |                                   |--- questionnaire_saved ------>|
  |                                   |  写入 questionnaire_responses |
  |                                   |                               |
```
