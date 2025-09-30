# ForcePress功能说明

## 🎯 功能概述

现在外部设备可以通过发送`ForcePress=true`来触发类似按下Enter键的效果，实现目标选择功能。

## 🔧 技术实现

### 1. 数据格式
外部设备需要在JSON消息中设置`ForcePress`字段：

```json
{
  "RawInput": 0.0,
  "YawInput": 0.0,
  "PitchInput": 0.0,
  "Fire": false,
  "Throttle": 0.0,
  "PawnControl": false,
  "ForcePress": true,  // 设置为true触发Enter效果
  "ForceSwitch": [0.5, -0.3],
  "timestamp": 1640995200000
}
```

### 2. 处理流程
1. **外部设备发送** `ForcePress=true` 的消息
2. **Hook检测** `useExternalTDCControl` 检测到ForcePress状态
3. **触发回调** 调用 `onForcePress` 回调函数
4. **模拟Enter键** 在Radar组件中创建并分发Enter键事件
5. **目标选择** RadarDisplay组件的Enter键处理逻辑被触发

### 3. 代码实现

#### Hook层面 (`useExternalTDCControl.ts`)
```typescript
// 检查ForcePress状态
if (data.ForcePress === true && onForcePress) {
  console.log('[useExternalTDCControl] ForcePress激活，触发Enter效果');
  onForcePress();
}
```

#### 组件层面 (`Radar.tsx`)
```typescript
// 处理外部ForcePress（模拟Enter键效果）
const handleExternalForcePress = useCallback(() => {
  console.log('[Radar] 外部ForcePress激活，模拟Enter键效果');
  
  // 创建一个模拟的Enter键事件
  const simulatedEnterEvent = new KeyboardEvent('keydown', {
    key: 'Enter',
    code: 'Enter',
    keyCode: 13,
    which: 13,
    bubbles: true,
    cancelable: true
  });
  
  // 触发键盘事件处理
  document.dispatchEvent(simulatedEnterEvent);
}, []);
```

## 🎮 使用场景

### 典型操作流程
1. **移动TDC**: 通过ForceSwitch调整TDC位置到目标附近
2. **选择目标**: 发送ForcePress=true触发目标选择
3. **确认选择**: 系统自动选择TDC附近的目标

### 示例操作序列
```json
// 1. 移动TDC到目标位置
{
  "ForcePress": false,
  "ForceSwitch": [0.5, -0.3]  // 移动到目标附近
}

// 2. 触发目标选择
{
  "ForcePress": true,         // 激活选择
  "ForceSwitch": [0.5, -0.3]  // 保持位置
}

// 3. 释放按压
{
  "ForcePress": false,        // 释放
  "ForceSwitch": [0.5, -0.3]  // 保持位置
}
```

## 📊 功能对比

| 控制方式 | 触发方式 | 效果 | 用途 |
|---------|---------|------|------|
| 键盘控制 | 按Enter键 | 选择TDC附近目标 | 手动操作 |
| 外部控制 | ForcePress=true | 选择TDC附近目标 | 外部设备控制 |

## 🔍 调试信息

### 控制台日志
当ForcePress被激活时，会看到以下日志：

```
[useExternalTDCControl] ForcePress激活，触发Enter效果
[Radar] 外部ForcePress激活，模拟Enter键效果
RadarDisplay - Enter键被按下，TDC位置: {x: 640, y: 360}
TDC位置已设置，偏移量: 40px
[锁定检测] 目标 T001: 计算位置(635.0, 365.0) vs 实际位置(635.0, 365.0) 距离TDC: 7.1px
找到最近的目标: T001 距离: 7.1
```

### 目标选择逻辑
- 系统会查找距离TDC位置30像素内的目标
- 选择距离最近的目标
- 如果没有找到目标，则取消当前选择

## 🧪 测试方法

### 1. 使用测试脚本
```bash
python test_force_press.py
```

### 2. 手动测试
1. 启动雷达系统
2. 连接到8765端口
3. 发送包含`ForcePress: true`的JSON消息
4. 观察目标选择效果

### 3. 测试数据示例
```json
{
  "RawInput": 0.0,
  "YawInput": 0.0,
  "PitchInput": 0.0,
  "Fire": false,
  "Throttle": 0.0,
  "PawnControl": false,
  "ForcePress": true,
  "ForceSwitch": [0.0, 0.0],
  "timestamp": 1640995200000
}
```

## ⚙️ 配置选项

### 目标选择阈值
在RadarDisplay.tsx中可以调整选择阈值：
```typescript
let minDistance = 30; // 设置一个阈值，只有距离小于这个值的目标才会被选中
```

### 事件处理
ForcePress事件通过标准的KeyboardEvent机制处理，确保与现有的Enter键逻辑完全兼容。

## 🎉 总结

ForcePress功能实现了：
- ✅ **无缝集成**: 与现有Enter键逻辑完全兼容
- ✅ **实时响应**: 外部设备控制的即时反馈
- ✅ **精确选择**: 基于TDC位置的智能目标选择
- ✅ **调试友好**: 详细的日志输出和状态跟踪

现在外部设备可以通过ForcePress字段实现完整的目标选择操作，就像按下Enter键一样！
