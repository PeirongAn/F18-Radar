# 外部TDC控制Hook使用说明

## 概述

新创建的 `useExternalTDCControl` Hook 专门处理来自8765端口的外部设备TDC控制数据，与现有的 `useRadarData` 完全分离，提供更清晰的架构和更好的可维护性。

## 文件结构

```
src/
├── hooks/
│   ├── useRadarData.ts          # 原有的雷达数据Hook
│   └── useExternalTDCControl.ts # 新的外部TDC控制Hook
└── components/
    └── ExternalTDCController.tsx # 外部TDC控制器组件
```

## Hook特性

### 1. 独立的WebSocket连接
- 直接连接到8765端口的外部设备服务
- 自动重连机制
- 连接状态管理

### 2. 智能变化检测
- 只有ForceSwitch坐标发生显著变化时才触发更新
- 可配置的变化检测阈值（默认0.001）
- 静默跳过重复数据

### 3. 数据转换和验证
- 自动将ForceSwitch数据转换为TDC坐标格式
- 坐标范围验证和限制（-1到1）
- 完整的错误处理

## 基本使用方法

### 1. 简单使用

```typescript
import useExternalTDCControl from '../hooks/useExternalTDCControl';

function MyComponent() {
  const { connected, lastTDCCoordinate, error } = useExternalTDCControl();

  return (
    <div>
      <div>连接状态: {connected ? '已连接' : '未连接'}</div>
      {error && <div>错误: {error}</div>}
      {lastTDCCoordinate && (
        <div>
          最新坐标: ({lastTDCCoordinate.x:.3f}, {lastTDCCoordinate.y:.3f})
        </div>
      )}
    </div>
  );
}
```

### 2. 带回调函数使用

```typescript
import useExternalTDCControl, { TDCCoordinateMessage } from '../hooks/useExternalTDCControl';

function RadarWithExternalTDC() {
  const [tdcPosition, setTdcPosition] = useState({ x: 0, y: 0 });

  // TDC坐标更新回调
  const handleTDCUpdate = useCallback((coordinate: TDCCoordinateMessage) => {
    console.log('收到外部TDC坐标:', coordinate);
    
    // 转换归一化坐标为像素坐标
    const pixelX = (coordinate.x + 1) * radarWidth / 2;
    const pixelY = (coordinate.y + 1) * radarHeight / 2;
    
    setTdcPosition({ x: pixelX, y: pixelY });
  }, []);

  const { connected, error } = useExternalTDCControl(
    'ws://localhost:8765',
    handleTDCUpdate
  );

  return (
    <div>
      {/* 雷达显示 */}
      <RadarDisplay tdcPosition={tdcPosition} />
      
      {/* 连接状态 */}
      <div>外部TDC: {connected ? '🟢' : '🔴'}</div>
    </div>
  );
}
```

### 3. 完整集成示例

```typescript
// 在Radar.tsx中集成外部TDC控制
import useExternalTDCControl, { TDCCoordinateMessage } from '../hooks/useExternalTDCControl';

const Radar: React.FC<RadarProps> = ({ ... }) => {
  const [tdcPosition, setTdcPosition] = useState({ x: 300, y: 300 });
  
  // 外部TDC坐标转换函数
  const convertExternalTDCToPixel = useCallback((coordinate: TDCCoordinateMessage) => {
    // 将归一化坐标(-1,1)转换为雷达屏幕像素坐标
    const pixelX = framePositions.startX + radarConfig.padding + 
      (coordinate.x + 1) * (radarConfig.mainBoxWidth - 2 * radarConfig.padding) / 2;
    
    const pixelY = framePositions.startY + radarConfig.padding + 
      (coordinate.y + 1) * (radarConfig.mainBoxHeight - 2 * radarConfig.padding) / 2;
    
    return { x: pixelX, y: pixelY };
  }, [framePositions, radarConfig]);

  // 外部TDC更新处理
  const handleExternalTDCUpdate = useCallback((coordinate: TDCCoordinateMessage) => {
    const pixelCoordinate = convertExternalTDCToPixel(coordinate);
    setTdcPosition(pixelCoordinate);
    
    console.log(`[外部TDC] 坐标更新: (${coordinate.x:.3f}, ${coordinate.y:.3f}) -> (${pixelCoordinate.x:.1f}, ${pixelCoordinate.y:.1f})`);
  }, [convertExternalTDCToPixel]);

  // 使用外部TDC控制Hook
  const externalTDC = useExternalTDCControl(
    'ws://localhost:8765',
    handleExternalTDCUpdate
  );

  // 检测是否有外部TDC活跃控制
  const hasExternalTDCControl = useCallback(() => {
    if (!externalTDC.lastTDCCoordinate) return false;
    const timeSinceLastUpdate = Date.now() - externalTDC.lastTDCCoordinate.timestamp;
    return timeSinceLastUpdate < 2000; // 2秒内有更新
  }, [externalTDC.lastTDCCoordinate]);

  // 键盘控制（当没有外部TDC控制时启用）
  const enableKeyboardControl = !hasExternalTDCControl();

  // ... 其他逻辑

  return (
    <div>
      {/* 雷达显示 */}
      <RadarDisplay 
        tdcPosition={tdcPosition}
        // ... 其他props
      />
      
      {/* 外部TDC状态指示 */}
      <div className="external-tdc-status">
        <span>外部TDC: {externalTDC.connected ? '🟢' : '🔴'}</span>
        {externalTDC.error && <span>错误: {externalTDC.error}</span>}
      </div>
    </div>
  );
};
```

## Hook API参考

### 参数

```typescript
useExternalTDCControl(
  wsUrl?: string,                                    // WebSocket URL，默认 'ws://localhost:8765'
  onTDCUpdate?: (coordinate: TDCCoordinateMessage) => void  // TDC坐标更新回调
)
```

### 返回值

```typescript
{
  // 状态
  connected: boolean;                    // 连接状态
  error: string | null;                  // 错误信息
  lastTDCCoordinate: TDCCoordinateMessage | null;  // 最后的TDC坐标
  messageCount: number;                  // 消息计数
  connectionAttempts: number;            // 连接尝试次数
  
  // 方法
  connect: () => void;                   // 手动连接
  disconnect: () => void;                // 断开连接
  setChangeThreshold: (threshold: number) => void;  // 设置变化阈值
  sendTestMessage: (forceSwitch: [number, number]) => void;  // 发送测试消息
  
  // 配置
  changeThreshold: number;               // 当前变化阈值
  wsUrl: string;                        // WebSocket URL
}
```

### 消息接口

```typescript
// TDC坐标消息
interface TDCCoordinateMessage {
  type: 'tdc_coordinate';
  x: number;        // -1 到 1 的归一化坐标
  y: number;        // -1 到 1 的归一化坐标
  timestamp: number;
  source?: string;  // 消息来源标识
}

// 外部设备原始消息
interface ExternalDeviceMessage {
  RawInput: number;
  YawInput: number;
  PitchInput: number;
  Fire: boolean;
  Throttle: number;
  PawnControl: boolean;
  ForcePress: boolean;
  ForceSwitch: [number, number];  // TDC坐标数据
  timestamp: number;
}
```

## 优势

### 1. 关注点分离
- 外部TDC控制与雷达数据处理完全分离
- 独立的状态管理和错误处理
- 更清晰的代码结构

### 2. 高性能
- 智能变化检测，避免重复处理
- 可配置的阈值设置
- 最小化不必要的重渲染

### 3. 易于测试
- 独立的Hook，便于单元测试
- 内置测试消息发送功能
- 详细的日志输出

### 4. 灵活配置
- 可配置的WebSocket URL
- 可调整的变化检测阈值
- 可选的回调函数

## 调试功能

### 1. 控制台日志
Hook会输出详细的调试信息：
```
[useExternalTDCControl] 尝试连接到: ws://localhost:8765
[useExternalTDCControl] ✅ 连接成功
[useExternalTDCControl] ForceSwitch变化: [0.500000, -0.300000]
[useExternalTDCControl] TDC坐标已更新: x=0.500000, y=-0.300000
```

### 2. 测试功能
```typescript
// 发送测试坐标
sendTestMessage([0.5, -0.3]);

// 调整变化阈值
setChangeThreshold(0.005);
```

### 3. 状态监控
```typescript
console.log('连接状态:', connected);
console.log('消息计数:', messageCount);
console.log('最后坐标:', lastTDCCoordinate);
```

## 与现有系统的集成

这个新的Hook可以与现有的TDC控制系统完美集成：

1. **保持兼容性**：不影响现有的键盘和内部WebSocket控制
2. **优先级管理**：可以通过时间戳判断哪种控制方式是活跃的
3. **平滑切换**：在不同控制方式之间无缝切换

这个架构提供了更好的可维护性和扩展性，同时保持了高性能和用户友好的体验。
