# 雷达威胁排序系统 API 接口文档

## 概述

雷达威胁排序系统提供基于 WebSocket 的实时通信接口和 HTTP 静态文件服务。系统采用事件驱动的消息协议，支持两种主要功能模式：

1. **传感器任务（雷达模式）** - 雷达目标检测、跟踪和识别
2. **威胁排序任务（SA模式）** - 威胁态势感知、优先级排序和应急响应

## 系统架构

系统采用前后端分离架构，通过 WebSocket 实现实时双向通信，支持 AI 智能体和手动操作两种模式。

## 服务器配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| 主机地址 | `0.0.0.0` | HTTP/WebSocket 服务器监听地址 |
| 端口号 | `8080` | HTTP/WebSocket 服务器端口 |
| 静态文件目录 | `../dist` | 前端静态文件目录 |

## 启动参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--static-dir` | string | `../dist` | 静态文件目录路径 |
| `--http-port` | int | `8080` | HTTP服务器端口 |
| `--ws-only` | flag | `false` | 仅启动WebSocket服务器模式 |

### 启动示例

```bash
# 标准启动（HTTP + WebSocket + 静态文件）
python main.py

# 自定义端口
python main.py --http-port 9000

# 自定义静态文件目录
python main.py --static-dir ./build

# 仅WebSocket模式
python main.py --ws-only
```

## HTTP 接口

### 静态文件服务

| 路径 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 返回 index.html（SPA 应用入口） |
| `/{path}` | GET | 静态文件服务（CSS、JS、图片等） |
| `/{spa_route}` | GET | SPA 路由回退到 index.html |

### WebSocket 连接

| 路径 | 协议 | 说明 |
|------|------|------|
| `/ws` | WebSocket | 实时双向通信连接 |

## WebSocket 消息协议

### 连接流程

1. **建立连接**: 客户端连接到 `ws://localhost:8080/ws`
2. **接收初始数据**: 服务器发送初始雷达数据
3. **双向通信**: 客户端发送操作消息，服务器响应状态更新
4. **会话管理**: 每个连接维护独立的会话状态

### 消息格式

所有消息均采用 JSON 格式，包含基础字段：

```json
{
  "type": "消息类型",
  "timestamp": 1234567890000
}
```

---

# 第一部分：传感器任务（雷达模式）接口

传感器任务主要负责雷达目标的检测、跟踪、识别和锁定，包括雷达参数设置、目标选择、IFF识别等功能。

## 雷达任务 - 客户端发送消息（上行）

### 1. 任务开始

**消息类型**: `task_start`

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 固定值："task_start" |
| `user_id` | string | 是 | 用户标识符 |
| `include_ai` | boolean | 否 | 是否启用AI智能体，默认false |
| `is_practice` | boolean | 否 | 是否为练习模式，默认false |
| `timestamp` | number | 否 | 时间戳 |

**示例**:
```json
{
  "type": "task_start",
  "user_id": "pilot_001",
  "include_ai": true,
  "is_practice": false,
  "timestamp": 1703123456789
}
```

### 2. 雷达参数设置

**消息类型**: `settings_update`

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 固定值："settings_update" |
| `range` | number | 是 | 雷达扫描范围（海里）|
| `scanAngle` | number | 是 | 扫描角度（度）|
| `event_owner` | string | 否 | 操作来源："AI" 或 "manual" |
| `timestamp` | number | 否 | 时间戳 |

**示例**:
```json
{
  "type": "settings_update",
  "range": 40,
  "scanAngle": 120,
  "event_owner": "manual",
  "timestamp": 1703123456789
}
```

### 3. 天线仰角调整

**消息类型**: `antenna_adjusted`

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 固定值："antenna_adjusted" |
| `elevation` | number | 是 | 天线仰角（度）|
| `event_owner` | string | 否 | 操作来源："AI" 或 "manual" |
| `timestamp` | number | 否 | 时间戳 |

**示例**:
```json
{
  "type": "antenna_adjusted",
  "elevation": 15.5,
  "event_owner": "manual",
  "timestamp": 1703123456789
}
```

### 4. 目标选择

**消息类型**: `target_selected`

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 固定值："target_selected" |
| `target_id` | string | 是 | 目标唯一标识符 |
| `action` | string | 是 | 操作类型："select" |
| `iff_mode` | boolean | 否 | 是否启用IFF模式 |
| `receive_timestamp` | number | 否 | 外部目标接收时间戳 |
| `event_owner` | string | 否 | 操作来源："AI" 或 "manual" |
| `timestamp` | number | 否 | 时间戳 |

**示例**:
```json
{
  "type": "target_selected",
  "target_id": "target_001",
  "action": "select",
  "iff_mode": true,
  "event_owner": "manual",
  "timestamp": 1703123456789
}
```

### 5. 威胁点击

**消息类型**: `threat_clicked`

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 固定值："threat_clicked" |
| `threat_id` | string | 是 | 威胁唯一标识符 |
| `event_owner` | string | 否 | 操作来源："AI" 或 "manual" |
| `timestamp` | number | 否 | 时间戳 |

**示例**:
```json
{
  "type": "threat_clicked",
  "threat_id": "threat_001",
  "event_owner": "manual",
  "timestamp": 1703123456789
}
```

### 6. 操作记录

**消息类型**: `record_operation`

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 固定值："record_operation" |
| `operation_type` | string | 是 | 操作类型 |
| `details` | object | 否 | 操作详细信息 |
| `event_owner` | string | 否 | 操作来源："AI" 或 "manual" |
| `timestamp` | number | 否 | 时间戳 |

## 雷达任务 - 服务器发送消息（下行）

### 1. 初始设置

**消息类型**: `init_settings`

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 固定值："init_settings" |
| `task_id` | number | 任务唯一标识符 |
| `settings` | object | 推荐雷达参数设置 |
| `task_type` | string | 任务类型："RADAR_TARGETING" |
| `repetition_info` | object | 任务重复信息 |
| `is_ai_active` | boolean | AI是否激活 |
| `audio_enabled` | boolean | 音频是否启用 |
| `timestamp` | number | 时间戳 |

**设置对象结构**:
```json
{
  "range": 40,
  "scanAngle": 120
}
```

**重复信息对象结构**:
```json
{
  "current": 1,
  "total": 10,
  "scenario_index": 1,
  "scenario_total": 5,
  "is_practice": false,
  "difficulty": "medium"
}
```

### 2. 雷达数据更新

**消息类型**: 雷达数据响应（无type字段，直接返回数据对象）

| 字段 | 类型 | 说明 |
|------|------|------|
| `targets` | array | 雷达目标列表 |
| `externalTargets` | array | 外部目标列表（未知目标） |
| `externalTargetsTimestamp` | number | 外部目标接收时间戳 |
| `radar_azimuth` | number | 雷达当前扫描方位角 |
| `own_heading` | number | 自机航向 |
| `timestamp` | number | 数据时间戳 |
| `audioEnabled` | boolean | 音频是否启用 |
| `ai_param_recommendation` | object | AI参数建议（可选） |

**目标对象结构**:
```json
{
  "id": "target_001",
  "position": {"x": 100, "y": 200},
  "speed": 300,
  "direction": 1.57,
  "direction_degrees": 90,
  "type": "friend",
  "quality": 85,
  "threat_level": 3,
  "threat_score": 0.75,
  "history": [{"x": 95, "y": 195}, {"x": 100, "y": 200}],
  "selected": false,
  "relative_heading": 45,
  "trail_length": 5
}
```

**外部目标对象结构**:
```json
{
  "id": "ext_target_001",
  "position": {"x": 150, "y": 250},
  "speed": 250,
  "direction": 2.1,
  "type": "unknown",
  "quality": 70
}
```

### 3. 设置验证

**消息类型**: `settings_validation`

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 固定值："settings_validation" |
| `status` | boolean | 验证是否成功 |
| `message` | string | 验证结果消息 |
| `settings` | object | 验证后的设置参数 |
| `timestamp` | number | 时间戳 |

### 4. 天线调整指令

**消息类型**: `adjust_antenna`

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 固定值："adjust_antenna" |
| `targetElevation` | number | 目标天线仰角（度） |
| `timestamp` | number | 时间戳 |

### 5. AI智能体数据

**消息类型**: `agent_level_data`

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 固定值："agent_level_data" |
| `level` | string | AI智能体等级 |
| `config` | object | AI配置参数 |
| `timestamp` | number | 时间戳 |

### 6. 服务器AI建议

**消息类型**: `server_ai_recommendation`

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 固定值："server_ai_recommendation" |
| `recommendation` | object | AI参数建议 |
| `timestamp` | number | 时间戳 |

**AI建议对象结构**:
```json
{
  "suggested_range": 40,
  "suggested_angle": 120,
  "confidence": 0.85,
  "reason": "optimal_for_current_scenario"
}
```

---

# 第二部分：威胁排序任务（SA模式）接口

威胁排序任务主要负责威胁态势感知、威胁优先级评估、临机事件处理和应急响应决策。

## SA任务 - 客户端发送消息（上行）

### 1. SA 模式切换

**消息类型**: `SwitchSA`

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 固定值："SwitchSA" |
| `user_id` | string | 是 | 用户标识符 |
| `is_practice` | boolean | 否 | 是否为练习模式 |
| `is_ai_active` | boolean | 否 | AI是否激活 |
| `timestamp` | number | 否 | 时间戳 |

**示例**:
```json
{
  "type": "SwitchSA",
  "user_id": "pilot_001",
  "is_practice": false,
  "is_ai_active": true,
  "timestamp": 1703123456789
}
```

### 2. SA 系统重置

**消息类型**: `ResetSA`

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 固定值："ResetSA" |
| `user_id` | string | 是 | 用户标识符 |
| `is_practice` | boolean | 否 | 是否为练习模式 |
| `is_ai_active` | boolean | 否 | AI是否激活 |
| `timestamp` | number | 否 | 时间戳 |

**示例**:
```json
{
  "type": "ResetSA",
  "user_id": "pilot_001",
  "is_practice": false,
  "is_ai_active": true,
  "timestamp": 1703123456789
}
```

### 3. 威胁点击交互

**消息类型**: `threat_clicked`

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 固定值："threat_clicked" |
| `threat_id` | string | 是 | 威胁唯一标识符 |
| `event_owner` | string | 否 | 操作来源："AI" 或 "manual" |
| `timestamp` | number | 否 | 时间戳 |

**示例**:
```json
{
  "type": "threat_clicked",
  "threat_id": "threat_001",
  "event_owner": "manual",
  "timestamp": 1703123456789
}
```

## SA任务 - 服务器发送消息（下行）

### 1. SA 威胁数据（增强协议）

**消息类型**: `sa_task_updated`

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 固定值："sa_task_updated" |
| `threats` | array | 增强威胁对象列表（增强协议） |
| `radar_config` | object | 雷达配置信息（增强协议） |
| `highest_priority_threat_id` | string | 最高优先级威胁ID |
| `generation_timestamp` | number | 生成时间戳 |
| `task_type` | string | 任务类型："SA_THREAT_RESPONSE" |
| `repetition_info` | object | 任务重复信息 |
| `is_ai_active` | boolean | AI是否激活 |
| `ai_level` | string | AI等级 |
| `ai_configs` | object | AI配置 |
| `audio_enabled` | boolean | 音频是否启用 |
| `saThreats` | array | 传统威胁对象列表（传统协议兼容） |
| `timestamp` | number | 时间戳 |

**增强威胁对象结构**:
```json
{
  "id": "threat_001",
  "type": "PrimaryAir",
  "label": "空中主要威胁-1",
  "position": {"x": 150, "y": 250},
  "distance": 25.5,
  "heading": 45,
  "priority": "high",
  "score": 0.85,
  "missile_type": null,
  "creation_timestamp": 1703123456789,
  "enhanced_data": {
    "detailed_classification": "fighter_jet",
    "weapon_systems": ["air_to_air_missile", "cannon"],
    "threat_assessment": "immediate"
  }
}
```

**传统威胁对象结构（兼容性）**:
```json
{
  "id": "threat_001",
  "type": "PrimaryAir",
  "label": "空中主要威胁-1"
}
```

**雷达配置对象结构**:
```json
{
  "canvas_width": 800,
  "canvas_height": 600,
  "radar_range": 50,
  "center_x": 400,
  "center_y": 300
}
```

### 2. SA 紧急事件（增强协议）

**消息类型**: `SAEmergency`

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 固定值："SAEmergency" |
| `event` | string | 事件类型："upgrade" 或 "missile" |
| `enhanced_data` | object | 增强数据信息（增强协议） |
| `radar_config` | object | 雷达配置（增强协议） |
| `missile_threat` | object | 导弹威胁对象（导弹事件时） |
| `updated_threats` | array | 更新后的完整威胁列表（增强协议） |
| `saThreats` | array | 传统威胁列表（传统协议兼容） |
| `missileType` | string | 导弹类型（传统协议兼容） |
| `receivedAt` | number | 接收时间戳（前端生成的唯一标识） |
| `timestamp` | number | 时间戳 |

**导弹来袭事件（增强协议）示例**:
```json
{
  "type": "SAEmergency",
  "event": "missile",
  "enhanced_data": {
    "missile_type": "MissileUp",
    "missile_position": {"x": 200, "y": 300},
    "missile_score": 0.95
  },
  "radar_config": {
    "canvas_width": 800,
    "canvas_height": 600,
    "radar_range": 50
  },
  "missile_threat": {
    "id": "missile_001",
    "type": "MissileUp",
    "label": "来袭导弹",
    "position": {"x": 200, "y": 300},
    "missile_type": "MissileUp",
    "score": 0.95,
    "creation_timestamp": 1703123456789
  },
  "updated_threats": [...],
  "timestamp": 1703123456789
}
```

**威胁升级事件（增强协议）示例**:
```json
{
  "type": "SAEmergency",
  "event": "upgrade",
  "enhanced_data": {
    "upgrade_count": 2,
    "affected_threat_ids": ["threat_001", "threat_002"],
    "specifically_upgraded_threats": [...]
  },
  "radar_config": {
    "canvas_width": 800,
    "canvas_height": 600,
    "radar_range": 50
  },
  "updated_threats": [
    {
      "id": "threat_001",
      "type": "PrimaryAir",
      "label": "空中主要威胁-1",
      "position": {"x": 150, "y": 250},
      "priority": "high",
      "score": 0.92
    }
  ],
  "timestamp": 1703123456789
}
```

**导弹来袭事件（传统协议兼容）示例**:
```json
{
  "type": "SAEmergency",
  "event": "missile",
  "missileType": "MissileUp",
  "saThreats": [],
  "timestamp": 1703123456789
}
```

**威胁升级事件（传统协议兼容）示例**:
```json
{
  "type": "SAEmergency",
  "event": "upgrade",
  "saThreats": [
    {
      "id": "threat_001",
      "type": "PrimaryAir",
      "label": "空中主要威胁-1"
    }
  ],
  "timestamp": 1703123456789
}
```

---

# 第三部分：通用系统接口

以下接口在雷达模式和SA模式中都会使用。

## 通用系统消息

### 1. 任务完成

**消息类型**: `all_tasks_completed`

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 固定值："all_tasks_completed" |
| `task_type` | string | 完成的任务类型 |
| `message` | string | 完成消息 |
| `timestamp` | number | 时间戳 |

### 2. 错误消息

**消息类型**: `error`

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 固定值："error" |
| `message` | string | 错误描述 |
| `error_code` | string | 错误代码（可选） |
| `timestamp` | number | 时间戳 |

## 状态码和错误处理

### WebSocket 连接状态

| 状态 | 说明 |
|------|------|
| 连接中 | WebSocket 正在建立连接 |
| 已连接 | 连接成功，可以收发消息 |
| 断开中 | 连接正在关闭 |
| 已断开 | 连接已关闭 |

### 常见错误

| 错误类型 | 说明 | 解决方法 |
|----------|------|----------|
| JSON解析错误 | 消息格式不正确 | 检查消息JSON格式 |
| 未知消息类型 | 不支持的消息类型 | 使用支持的消息类型 |
| 缺失必需字段 | 必需参数缺失 | 补充必需的字段 |
| 连接异常 | WebSocket连接异常 | 检查网络连接，重新连接 |

## 协议版本和兼容性

### 当前版本
- **协议版本**: v2.0
- **增强消息**: 支持完整威胁数据传输
- **向后兼容**: 支持传统消息格式
- **双协议支持**: 增强协议和传统协议自动切换

### 消息协议特性

| 特性 | 说明 |
|------|------|
| 增强威胁消息 | 包含完整的威胁位置、评分、类型、雷达配置信息 |
| 传统格式兼容 | 自动适配传统客户端，保持 saThreats 字段 |
| 智能协议切换 | 根据消息内容自动选择增强或传统协议 |
| 事件驱动架构 | 基于消息类型的事件处理 |
| 会话状态管理 | 每连接独立的状态管理 |
| 消息去重机制 | 防止重复处理相同消息 |
| 音频触发集成 | 特定事件自动触发音频提示 |

### 协议切换逻辑

| 消息类型 | 增强协议标识 | 传统协议标识 |
|----------|-------------|-------------|
| `sa_task_updated` | 包含 `threats` 和 `radar_config` 字段 | 包含 `saThreats` 字段 |
| `SAEmergency` | 包含 `enhanced_data`、`updated_threats` 字段 | 包含 `saThreats`、`missileType` 字段 |
| `externalTargets` | 完整目标对象结构 | 简化目标列表 |

## 性能和限制

| 项目 | 限制 | 说明 |
|------|------|------|
| 并发连接数 | 1000+ | 支持多个客户端同时连接 |
| 消息大小 | 1MB | 单个消息最大大小 |
| 消息频率 | 100/秒 | 建议最大消息发送频率 |
| 会话超时 | 30分钟 | 无活动连接自动断开 |

## 安全考虑

| 安全措施 | 说明 |
|----------|------|
| 消息验证 | 所有消息进行格式验证 |
| 会话隔离 | 每个连接独立的会话状态 |
| 错误处理 | 完善的异常处理机制 |
| 日志记录 | 完整的操作日志记录 |

## 开发和调试

### 调试工具
- WebSocket 连接测试：可以使用浏览器开发者工具
- 消息监控：服务器提供详细的日志输出
- 错误追踪：完整的错误堆栈信息

### 测试建议
1. 首先测试 WebSocket 连接建立
2. 验证消息格式的正确性
3. 测试各种业务场景的消息流
4. 验证错误处理和异常情况

---

**更新时间**: 2024年12月
**版本**: v2.0
**维护**: 雷达系统开发团队
