# 外部TDC控制Hook完整使用说明

## 概述

`useExternalTDCControl` 是一个专门用于处理外部设备TDC（Target Designation Cursor）控制的React Hook。它通过WebSocket连接到外部设备（默认端口8765），接收ForceSwitch数据，并将其转换为TDC坐标控制信息。

## 主要功能

### 1. 外部设备连接
- 自动连接到指定的WebSocket服务（默认 `ws://localhost:8765`）
- 自动重连机制，连接断开时会自动尝试重连
- 连接状态监控和错误处理

### 2. 数据处理
- 接收外部设备的ForceSwitch数据 `[x, y]`
- 变化检测：只有当数据变化超过设定阈值时才处理
- 坐标范围验证：确保坐标在 -1 到 1 范围内
- 归一化坐标到像素坐标的转换

### 3. TDC控制
- 实时TDC位置更新
- 支持手动设置TDC位置
- TDC控制活跃状态检测
- 像素坐标和归一化坐标的双向转换

## 接口定义

### TDCCoordinateMessage
```typescript
export interface TDCCoordinateMessage {
  type: 'tdc_coordinate';
  x: number; // -1 到 1 的归一化坐标
  y: number; // -1 到 1 的归一化坐标
  timestamp: number;
  source?: string; // 消息来源标识
}
```

### TDCPosition
```typescript
export interface TDCPosition {
  x: number; // 像素坐标
  y: number; // 像素坐标
}
```

### CoordinateConfig
```typescript
export interface CoordinateConfig {
  frameStartX: number;  // 雷达显示区域起始X坐标
  frameStartY: number;  // 雷达显示区域起始Y坐标
  radarWidth: number;   // 雷达显示区域宽度
  radarHeight: number;  // 雷达显示区域高度
  padding: number;      // 内边距
}
```

## Hook参数

```typescript
const useExternalTDCControl = (
  wsUrl?: string,                    // WebSocket地址，默认 'ws://localhost:8765'
  coordinateConfig?: CoordinateConfig, // 坐标转换配置
  onTDCUpdate?: (coordinate: TDCCoordinateMessage, pixelPosition: TDCPosition) => void
) => { ... }
```

## 返回值

### 状态属性
- `connected: boolean` - WebSocket连接状态
- `error: string | null` - 错误信息
- `lastTDCCoordinate: TDCCoordinateMessage | null` - 最后接收的TDC坐标消息
- `messageCount: number` - 接收的消息总数
- `connectionAttempts: number` - 连接尝试次数
- `tdcPosition: TDCPosition | null` - 当前TDC像素位置
- `lastUpdateTime: number` - 最后更新时间戳

### 控制方法
- `connect()` - 手动连接WebSocket
- `disconnect()` - 断开WebSocket连接
- `setTDCPosition(x: number, y: number)` - 手动设置TDC位置（归一化坐标）
- `setChangeThreshold(threshold: number)` - 设置变化检测阈值
- `sendTestMessage(forceSwitch: [number, number])` - 发送测试消息
- `isTDCControlActive(timeoutMs?: number)` - 检查TDC控制是否活跃
- `getCurrentNormalizedCoordinate()` - 获取当前归一化坐标
- `convertNormalizedToPixel(x: number, y: number)` - 坐标转换函数

### 配置属性
- `changeThreshold: number` - 当前变化检测阈值
- `wsUrl: string` - WebSocket地址
- `coordinateConfig: CoordinateConfig` - 坐标转换配置

## 使用示例

### 基本使用

```typescript
import React, { useCallback, useMemo } from 'react';
import useExternalTDCControl, { CoordinateConfig } from '../hooks/useExternalTDCControl';

const RadarComponent: React.FC = () => {
  // 雷达显示区域配置
  const coordinateConfig: CoordinateConfig = useMemo(() => ({
    frameStartX: 100,
    frameStartY: 100,
    radarWidth: 800,
    radarHeight: 600,
    padding: 20
  }), []);

  // TDC更新处理
  const handleTDCUpdate = useCallback((coordinate, pixelPosition) => {
    console.log('TDC位置更新:', {
      normalized: { x: coordinate.x, y: coordinate.y },
      pixel: { x: pixelPosition.x, y: pixelPosition.y }
    });
    
    // 更新TDC显示位置
    setTdcPosition(pixelPosition);
  }, []);

  // 使用Hook
  const tdcControl = useExternalTDCControl(
    'ws://localhost:8765',
    coordinateConfig,
    handleTDCUpdate
  );

  return (
    <div>
      {/* 雷达显示 */}
      <div style={{ position: 'relative' }}>
        {/* TDC光标 */}
        {tdcControl.tdcPosition && (
          <div
            style={{
              position: 'absolute',
              left: tdcControl.tdcPosition.x - 10,
              top: tdcControl.tdcPosition.y - 10,
              width: 20,
              height: 20,
              border: '2px solid yellow',
              borderRadius: '50%',
              pointerEvents: 'none'
            }}
          />
        )}
      </div>
      
      {/* 状态显示 */}
      <div>
        连接状态: {tdcControl.connected ? '已连接' : '未连接'}
        {tdcControl.error && <div>错误: {tdcControl.error}</div>}
      </div>
    </div>
  );
};
```

### 在Radar组件中集成

```typescript
// 在现有的Radar组件中添加
const Radar: React.FC<RadarProps> = ({ ... }) => {
  // ... 现有代码 ...

  // 配置坐标转换
  const coordinateConfig: CoordinateConfig = useMemo(() => ({
    frameStartX: framePositions.startX,
    frameStartY: framePositions.startY,
    radarWidth: radarConfig.mainBoxWidth,
    radarHeight: radarConfig.mainBoxHeight,
    padding: radarConfig.padding
  }), [framePositions, radarConfig]);

  // 处理外部TDC更新
  const handleExternalTDCUpdate = useCallback((
    coordinate: TDCCoordinateMessage, 
    pixelPosition: TDCPosition
  ) => {
    // 更新TDC位置
    setTdcPosition(pixelPosition);
    
    // 标记为外部控制
    setHasRecentWebSocketControl(true);
    
    // 2秒后允许键盘控制
    setTimeout(() => setHasRecentWebSocketControl(false), 2000);
  }, []);

  // 使用外部TDC控制
  const externalTDC = useExternalTDCControl(
    'ws://localhost:8765',
    coordinateConfig,
    handleExternalTDCUpdate
  );

  // 混合控制逻辑
  const enableKeyboardControl = !externalTDC.isTDCControlActive(2000);

  // ... 其余代码 ...
};
```

## 配置说明

### 变化检测阈值
- 默认值：0.001
- 范围：0.0001 - 0.1
- 用途：只有当ForceSwitch数据变化超过此阈值时才处理，避免频繁更新

### 自动重连
- 重连延迟：1000ms * (1.5 ^ 连接尝试次数)
- 最大延迟：5000ms
- 连接断开时自动触发重连

### 坐标转换
- 输入：归一化坐标 (-1 到 1)
- 输出：像素坐标（基于配置的显示区域）
- 自动处理边界限制和坐标映射

## 调试功能

### 测试消息发送
```typescript
// 发送测试ForceSwitch数据
tdcControl.sendTestMessage([0.5, -0.3]);
```

### 手动设置位置
```typescript
// 手动设置TDC到中心位置
tdcControl.setTDCPosition(0, 0);
```

### 状态监控
```typescript
// 检查控制是否活跃
const isActive = tdcControl.isTDCControlActive(2000); // 2秒内有更新

// 获取当前坐标
const coords = tdcControl.getCurrentNormalizedCoordinate();
```

## 注意事项

1. **坐标系统**：外部设备使用归一化坐标(-1到1)，Hook自动转换为像素坐标
2. **变化检测**：只有数据变化超过阈值才会触发更新，提高性能
3. **自动重连**：连接断开时会自动重连，无需手动处理
4. **错误处理**：所有WebSocket错误都会被捕获并通过error状态暴露
5. **性能优化**：使用useCallback和useMemo优化渲染性能

## 与键盘控制的混合使用

Hook提供了`isTDCControlActive()`方法来检测外部控制是否活跃，可以用来实现混合控制：

```typescript
const enableKeyboardControl = !externalTDC.isTDCControlActive(2000);

// 只有在外部控制不活跃时才启用键盘控制
useKeyboardControl(enableKeyboardControl ? handleTdcKeyAction : () => {});
```

这样可以实现外部设备控制优先，键盘控制作为备用的混合控制方案。
