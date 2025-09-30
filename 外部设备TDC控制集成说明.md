# 外部设备TDC控制集成说明

## 概述

已成功为雷达系统集成了外部设备TDC控制功能。系统现在可以同时接收来自三种不同来源的TDC控制：

1. **键盘控制**：传统方向键控制
2. **内部WebSocket控制**：通过8080端口的WebSocket发送tdc_coordinate消息
3. **外部设备控制**：通过8765端口接收外部设备的ForceSwitch数据

## 架构设计

### 双WebSocket服务器架构

```
外部设备 (8765端口)  →  外部设备WebSocket服务器  →  雷达客户端 (8080端口)
     ↓                        ↓                        ↓
ForceSwitch数据         tdc_coordinate转换         TDC位置更新
```

### 数据流转换

```json
// 外部设备输入 (8765端口)
{
  "RawInput": 0.0,
  "YawInput": 0.04,
  "PitchInput": 0.0,
  "Fire": false,
  "Throttle": 0.0,
  "PawnControl": false,
  "ForcePress": false,
  "ForceSwitch": [0.5, -0.3],  // ← TDC坐标数据
  "timestamp": 1759229118.9065819
}

// 转换后广播给雷达客户端
{
  "type": "tdc_coordinate",
  "x": 0.5,
  "y": -0.3,
  "timestamp": 1759229118.9065819,
  "source": "external_device"
}
```

## 新增文件

### 1. `server/network/external_device_server.py`
外部设备WebSocket服务器，负责：
- 监听8765端口
- 解析外部设备消息
- 提取ForceSwitch数据
- 转换为tdc_coordinate格式
- 广播给所有雷达客户端

### 2. `test_external_device_simulator.py`
外部设备模拟器，用于测试功能：
- 模拟外部设备发送控制数据
- 支持手动输入坐标
- 提供自动测试序列
- 圆形轨迹运动测试

## 修改的文件

### 1. `server/main.py`
- 添加外部设备服务器启动逻辑
- 新增命令行参数：
  - `--external-port`: 外部设备端口（默认8765）
  - `--no-external`: 禁用外部设备服务器
- 并发启动多个WebSocket服务器

### 2. `server/network/http_server.py`
- 雷达客户端连接时自动注册到外部设备服务器
- 断开连接时自动注销
- 确保TDC坐标能够实时转发

## 使用方法

### 启动服务器

```bash
# 标准启动（包含外部设备服务器）
python server/main.py

# 自定义外部设备端口
python server/main.py --external-port 9999

# 禁用外部设备服务器
python server/main.py --no-external

# 仅启动WebSocket（包含外部设备服务器）
python server/main.py --ws-only
```

### 外部设备连接

外部设备需要连接到：`ws://localhost:8765`

发送JSON格式的控制数据，其中`ForceSwitch`数组包含TDC坐标：
```json
{
  "ForceSwitch": [x, y],  // x,y 范围 -1.0 到 1.0
  "timestamp": <当前时间戳>
}
```

### 测试外部设备功能

```bash
# 运行外部设备模拟器
python test_external_device_simulator.py

# 在模拟器中：
# - 输入 'test' 运行自动测试
# - 输入 'x,y' 发送指定坐标
# - 输入 'q' 退出
```

## 坐标系统

### ForceSwitch坐标映射
- `ForceSwitch[0]` → TDC X坐标
- `ForceSwitch[1]` → TDC Y坐标
- 坐标范围：-1.0 到 1.0
- 坐标系：
  - `(-1, -1)`: 雷达显示区域左下角
  - `(1, 1)`: 雷达显示区域右上角
  - `(0, 0)`: 雷达显示区域中心

## 智能控制切换

系统会自动在不同控制方式之间切换：

1. **外部设备控制优先级最高**：当有外部设备数据时，会覆盖其他控制方式
2. **内部WebSocket控制次之**：通过8080端口的tdc_coordinate消息
3. **键盘控制优先级最低**：当没有其他活跃控制时启用

### 切换逻辑
- 2秒内有外部设备或内部WebSocket更新 → 禁用键盘控制
- 超过2秒没有WebSocket更新 → 恢复键盘控制
- 实时检测，无缝切换

## 日志和调试

### 服务器日志
```
INFO - 外部设备WebSocket服务器已启动: ws://localhost:8765
INFO - 外部设备已连接: ('127.0.0.1', 54321)
INFO - 外部设备TDC坐标: x=0.500, y=-0.300
INFO - 已向雷达客户端发送TDC坐标
```

### 前端日志
```
[TDC WebSocket] 收到坐标数据: {x: 0.5, y: -0.3, source: "external_device"}
[TDC坐标转换] 归一化坐标(0.500, -0.300) -> 像素坐标(450.0, 280.0)
[TDC键盘] WebSocket控制活跃，忽略up操作
```

## 错误处理

### 1. 连接错误
- 外部设备连接失败时，系统继续正常运行
- 雷达客户端可以正常使用键盘和内部WebSocket控制

### 2. 数据验证
- ForceSwitch数据自动限制在(-1, 1)范围内
- 无效数据会被记录但不会影响系统运行

### 3. 网络异常
- 外部设备断开连接时自动清理资源
- 雷达客户端断开时自动从外部设备服务器注销

## 性能特性

- **低延迟**：直接WebSocket转发，最小化处理延迟
- **高并发**：支持多个雷达客户端同时接收外部设备控制
- **资源高效**：异步处理，不阻塞主服务器
- **实时同步**：所有连接的雷达客户端同时接收TDC更新

## 扩展性

系统设计支持未来扩展：
- 可以轻松添加更多外部设备类型
- 支持不同的消息协议格式
- 可以添加设备认证和权限控制
- 支持设备状态监控和管理

这个集成方案为雷达系统提供了完整的外部设备TDC控制能力，同时保持了系统的稳定性和可扩展性。
