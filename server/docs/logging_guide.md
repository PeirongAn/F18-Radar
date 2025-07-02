# 雷达系统日志模块使用指南

## 🎯 概述

雷达系统现在包含了一个统一的日志管理模块，提供彩色输出、级别控制和模块化日志功能。

## 📋 功能特性

### ✨ 主要特性
- 🎨 **彩色日志输出**: 不同级别使用不同颜色和图标
- 🔧 **级别控制**: 支持 DEBUG、INFO、WARNING、ERROR、CRITICAL 五个级别
- 📦 **模块化日志**: 每个模块都有独立的日志标识
- 🌍 **环境变量控制**: 通过环境变量动态设置日志级别
- 📁 **文件日志**: 可选的文件日志输出
- ⚡ **性能优化**: 轻量级设计，不影响系统性能

### 🎨 日志级别和颜色

| 级别 | 图标 | 颜色 | 用途 |
|------|------|------|------|
| DEBUG | 🔍 | 青色 | 调试信息，详细的执行流程 |
| INFO | ✅ | 绿色 | 一般信息，正常的操作流程 |
| WARNING | ⚠️ | 黄色 | 警告信息，可能的问题 |
| ERROR | ❌ | 红色 | 错误信息，需要关注的问题 |
| CRITICAL | 🚨 | 紫色 | 严重错误，可能导致系统崩溃 |

## 🚀 基本使用

### 导入日志模块

```python
# 方式一：导入便捷函数
from managers.logger_manager import debug, info, warning, error, critical

# 方式二：导入特定模块的日志器
from managers.logger_manager import get_logger

# 方式三：导入日志管理器
from managers.logger_manager import get_logger_manager
```

### 基本日志记录

```python
# 使用便捷函数
info("服务器启动成功", "main")
warning("配置文件未找到，使用默认配置", "config")
error("数据库连接失败", "database")

# 使用模块特定的日志器
logger = get_logger("websocket")
logger.info("WebSocket服务器启动")
logger.error("客户端连接失败", exc_info=True)  # 包含异常堆栈
```

### 异常日志记录

```python
try:
    # 一些可能出错的代码
    result = risky_operation()
except Exception as e:
    error(f"操作失败: {e}", "module_name", exc_info=True)
```

## ⚙️ 配置和控制

### 环境变量控制

```bash
# 设置日志级别
export LOG_LEVEL=DEBUG    # 显示所有日志
export LOG_LEVEL=INFO     # 显示 INFO 及以上级别
export LOG_LEVEL=WARNING  # 只显示警告和错误
export LOG_LEVEL=ERROR    # 只显示错误

# 启用文件日志
export LOG_TO_FILE=true   # 将日志同时写入文件
```

### 动态级别控制

```python
from managers.logger_manager import set_log_level

# 运行时动态设置日志级别
set_log_level('DEBUG')    # 切换到调试模式
set_log_level('ERROR')    # 只显示错误信息
```

### 启动时设置

```bash
# 启动时设置日志级别
LOG_LEVEL=DEBUG python start.py

# 启用文件日志
LOG_TO_FILE=true LOG_LEVEL=INFO python start.py
```

## 📁 文件日志

当启用文件日志时，日志会同时输出到控制台和文件：

- 文件位置: `logs/radar_system_YYYY-MM-DD.log`
- 格式: 标准的时间戳格式（无颜色）
- 自动按日期分割文件

```bash
# 启用文件日志
export LOG_TO_FILE=true
python start.py
```

## 🔧 在各模块中使用

### 数据库模块示例

```python
from .logger_manager import get_logger

class DatabaseManager:
    def __init__(self):
        self.logger = get_logger("database")
    
    def connect(self):
        self.logger.info("正在连接数据库...")
        try:
            # 连接逻辑
            self.logger.info("数据库连接成功")
        except Exception as e:
            self.logger.error(f"数据库连接失败: {e}", exc_info=True)
```

### WebSocket模块示例

```python
from managers import get_logger

class WebSocketServer:
    def __init__(self):
        self.logger = get_logger("websocket")
    
    async def handle_client(self, websocket):
        self.logger.info("客户端已连接")
        try:
            # 处理逻辑
            self.logger.debug("处理客户端消息")
        except Exception as e:
            self.logger.error(f"处理客户端消息失败: {e}", exc_info=True)
```

## 🧪 测试日志系统

运行日志测试脚本：

```bash
# 测试基本功能
python tests/test_logger.py

# 测试不同级别
LOG_LEVEL=DEBUG python tests/test_logger.py
LOG_LEVEL=WARNING python tests/test_logger.py
```

## 📊 最佳实践

### 1. 选择合适的日志级别

```python
# ✅ 好的做法
logger.debug("计算中间结果: {result}")      # 调试信息
logger.info("用户登录成功")                  # 重要事件
logger.warning("配置文件格式过时")            # 潜在问题
logger.error("API调用失败", exc_info=True)   # 错误信息
logger.critical("数据库不可用")              # 严重问题

# ❌ 避免的做法
logger.error("用户点击了按钮")               # 正常操作不应该用ERROR
logger.debug("系统崩溃")                    # 严重问题不应该用DEBUG
```

### 2. 提供有用的上下文信息

```python
# ✅ 好的做法
logger.info(f"处理用户 {user_id} 的请求: {request_type}")
logger.error(f"文件 {filename} 不存在，路径: {file_path}")

# ❌ 避免的做法
logger.info("处理请求")
logger.error("文件不存在")
```

### 3. 合理使用异常信息

```python
# ✅ 包含异常堆栈的错误日志
try:
    process_data()
except Exception as e:
    logger.error(f"数据处理失败: {e}", exc_info=True)

# ✅ 简单的错误信息
if not file.exists():
    logger.warning(f"文件不存在: {filename}")
```

## 🔄 迁移指南

### 从print语句迁移

```python
# 旧代码
print("服务器启动")
print(f"错误: {error}")

# 新代码
from managers.logger_manager import info, error
info("服务器启动", "main")
error(f"操作失败: {error}", "main")
```

### 批量替换建议

1. **INFO级别**: 替换一般的print语句
2. **DEBUG级别**: 替换调试用的print语句
3. **WARNING级别**: 替换警告信息
4. **ERROR级别**: 替换错误信息

## 🎛️ 生产环境配置

### 推荐的生产环境设置

```bash
# 生产环境：只记录重要信息
export LOG_LEVEL=INFO

# 开发环境：记录详细信息
export LOG_LEVEL=DEBUG

# 故障排查：启用文件日志
export LOG_TO_FILE=true
export LOG_LEVEL=DEBUG
```

### 性能考虑

- 日志级别设置为INFO或WARNING可以减少输出量
- DEBUG级别会产生大量日志，仅在开发时使用
- 文件日志会有轻微的性能影响，按需启用

## 📞 故障排查

### 常见问题

1. **颜色不显示**: 确保终端支持ANSI颜色代码
2. **日志不输出**: 检查日志级别设置
3. **文件日志失败**: 检查logs目录权限

### 调试技巧

```bash
# 启用最详细的日志
LOG_LEVEL=DEBUG python start.py

# 查看特定模块的日志
LOG_LEVEL=DEBUG python start.py 2>&1 | grep "database"
```

## 📈 未来扩展

日志系统支持以下扩展：

- 日志轮转（按大小或时间）
- 远程日志服务器
- 结构化日志（JSON格式）
- 性能指标记录
- 自定义格式化器