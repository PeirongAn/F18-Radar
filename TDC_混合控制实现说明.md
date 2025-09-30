# TDC混合控制实现说明

## 概述

已成功实现TDC（Target Designation Cursor）的混合控制系统，同时支持键盘控制和WebSocket坐标控制两种方式。系统会智能地在两种控制方式之间切换，确保用户体验的流畅性。

## 功能特性

### 1. 双重控制支持
- **键盘控制**：传统的方向键控制（↑↓←→）
- **WebSocket控制**：通过WebSocket接收(-1,1)范围的归一化坐标

### 2. 智能切换机制
- 当WebSocket有活跃控制时（2秒内有更新），自动禁用键盘控制
- 当WebSocket控制停止时，自动恢复键盘控制
- 无缝切换，用户无感知

### 3. 坐标转换
- 归一化坐标(-1,1) ↔ 雷达屏幕像素坐标
- 自动边界限制和范围验证

## 实现架构

### 前端（React/TypeScript）

#### 1. 数据类型定义 (`src/hooks/useRadarData.ts`)
```typescript
interface RadarData {
  // ... 现有字段
  tdcCoordinate?: {
    x: number; // -1 到 1 的归一化坐标
    y: number; // -1 到 1 的归一化坐标
    timestamp: number;
  };
}
```

#### 2. WebSocket消息处理
```typescript
// 在 GlobalWebSocketManager 中处理 tdc_coordinate 消息
if (rawData.type === 'tdc_coordinate') {
  // 更新 radarData.tdcCoordinate
}
```

#### 3. 混合控制逻辑 (`src/components/Radar.tsx`)
```typescript
// 坐标转换函数
const convertNormalizedToPixel = (x, y) => { 
  // 将 (-1,1) 转换为像素坐标
}

// 检测WebSocket控制活跃状态
const hasRecentWebSocketControl = () => {
  // 检查2秒内是否有WebSocket更新
}

// 混合键盘控制
const hybridTdcKeyAction = (action) => {
  if (enableKeyboardControl) {
    handleTdcKeyAction(action); // 执行键盘操作
  } else {
    // 忽略键盘操作，因为WebSocket控制活跃
  }
}
```

### 后端（Python）

#### 1. 消息路由 (`server/core/message_handler.py`)
```python
async def handle_client_message(self, message_str, session_state, websocket):
    # ... 现有消息类型处理
    elif message_type == 'tdc_coordinate':
        return await self._handle_tdc_coordinate(message, session_state, websocket)
```

#### 2. TDC坐标处理
```python
async def _handle_tdc_coordinate(self, message, session_state, websocket):
    x = message.get('x', 0)
    y = message.get('y', 0)
    
    # 验证坐标范围 (-1, 1)
    if not (-1 <= x <= 1 and -1 <= y <= 1):
        return error_response
    
    # 广播给所有客户端
    return {
        'type': 'tdc_coordinate',
        'x': x, 'y': y,
        'timestamp': time.time()
    }, False
```

## 使用方法

### 1. 键盘控制（默认）
- 使用方向键 ↑↓←→ 控制TDC移动
- 每次移动5像素
- 自动边界限制

### 2. WebSocket控制
发送JSON消息到WebSocket：
```json
{
  "type": "tdc_coordinate",
  "x": 0.5,    // -1.0 到 1.0
  "y": -0.3,   // -1.0 到 1.0
  "timestamp": 1634567890123
}
```

#### 坐标系统
- `(-1, -1)`: 雷达显示区域左下角
- `(1, 1)`: 雷达显示区域右上角  
- `(0, 0)`: 雷达显示区域中心
- `(0.5, 0)`: 右侧中间
- `(-0.5, 0)`: 左侧中间

### 3. 测试工具
使用提供的测试脚本：
```bash
python test_tdc_websocket_control.py
```

测试功能：
- 交互式坐标输入
- 自动测试序列
- 实时坐标验证

## 技术细节

### 1. 坐标转换算法
```typescript
const pixelX = framePositions.startX + radarConfig.padding + 
  (clampedX + 1) * availableWidth / 2;

const pixelY = framePositions.startY + radarConfig.padding + 
  (clampedY + 1) * availableHeight / 2;
```

### 2. 智能切换逻辑
- WebSocket控制检测：检查最近2秒内是否有坐标更新
- 键盘控制条件：`enableKeyboardControl = !hasRecentWebSocketControl()`
- 实时状态监控：通过 `useEffect` 监听 `radarData.tdcCoordinate` 变化

### 3. 消息去重
- WebSocket消息包含timestamp避免重复处理
- 但TDC坐标消息总是被处理以确保实时性

## 错误处理

### 1. 坐标范围验证
- 前端：自动clamp到(-1,1)范围
- 后端：验证范围，超出范围返回错误

### 2. WebSocket连接
- 连接失败时自动降级为键盘控制
- 连接断开时保持键盘控制可用

### 3. 边界限制
- 像素坐标自动限制在雷达显示区域内
- 考虑padding和边界约束

## 优势

1. **无缝切换**：用户无需手动切换控制模式
2. **高精度**：WebSocket控制提供像素级精度
3. **实时响应**：低延迟的坐标更新
4. **兼容性**：保持现有键盘控制功能
5. **可扩展**：易于添加其他控制方式（如手柄、鼠标等）

## 调试信息

系统提供详细的控制台日志：
- `[TDC坐标转换]`: 归一化坐标到像素坐标的转换
- `[TDC WebSocket]`: WebSocket坐标接收和处理
- `[TDC键盘]`: 键盘控制的执行或忽略状态
- 后端日志显示坐标验证和广播过程

这个实现为雷达系统提供了灵活、精确、用户友好的TDC控制解决方案。
