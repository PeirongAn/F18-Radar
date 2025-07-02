# 雷达系统服务器 - 模块化架构

## 🚀 快速开始

### 启动服务器
```bash
# 方式一：使用启动脚本（推荐）
python start.py

# 方式二：直接运行主文件
python main.py

# 方式三：使用旧版本（兼容）
python legacy/radar_server.py
```

### 日志级别控制
```bash
# 设置日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）
LOG_LEVEL=DEBUG python start.py

# 启用文件日志
LOG_TO_FILE=true python start.py

# 组合使用
LOG_LEVEL=INFO LOG_TO_FILE=true python start.py
```

### 运行测试
```bash
# 测试模块导入
python tests/test_imports.py

# 测试日志系统
python tests/test_logger.py

# 测试连接
python tests/test_connection.py

# 运行所有测试
python tests/test.py
```

## 📁 项目结构

```
server/
├── 🎯 core/                    # 核心业务逻辑
│   ├── __init__.py
│   └── message_handler.py      # 消息处理器
│
├── 🔧 managers/                # 功能管理器
│   ├── __init__.py
│   ├── config_manager.py       # 配置管理
│   ├── database_manager.py     # 数据库管理
│   ├── logger_manager.py       # 日志管理 ⭐
│   ├── task_manager.py         # 任务管理
│   ├── target_manager.py       # 目标管理
│   └── threat_manager.py       # 威胁管理
│
├── 🌐 network/                 # 网络通信
│   ├── __init__.py
│   └── websocket_server.py     # WebSocket服务器
│
├── 💾 data/                    # 数据存储
│   └── radar_operations.db     # SQLite数据库
│
├── 🧪 tests/                   # 测试文件
│   ├── __init__.py
│   ├── test_imports.py         # 导入测试
│   ├── test_logger.py          # 日志测试 ⭐
│   ├── test_connection.py      # 连接测试
│   └── test.py                 # 主测试文件
│
├── 📚 docs/                    # 项目文档
│   ├── project_structure.md    # 详细架构说明
│   ├── logging_guide.md        # 日志使用指南 ⭐
│   ├── README_refactoring.md   # 重构文档
│   └── readme.md              # 原始说明
│
├── 📦 legacy/                  # 旧版备份
│   ├── radar_server.py         # 原始服务器
│   └── radar_server_backup.py  # 备份文件
│
├── main.py                     # 主入口文件
├── start.py                    # 启动脚本
├── requirements.txt            # 依赖列表
└── README.md                   # 本文件
```

## ✨ 新架构优势

1. **清晰的职责分离**: 每个模块专注于特定功能
2. **易于维护**: 修改某个功能不影响其他模块
3. **便于测试**: 每个模块可以独立测试
4. **扩展性强**: 可以轻松添加新的管理器或功能
5. **团队协作**: 不同开发者可以并行开发不同模块
6. **统一日志**: 🆕 完整的日志系统，支持级别控制和彩色输出

## 🔧 配置要求

- Python 3.7+
- 依赖包: `pip install -r requirements.txt`
- 配置文件: `../public/agent_level.json`
- 可选依赖: `colorama` (用于彩色日志输出)

## 📋 模块说明

### Core 模块
- **message_handler.py**: 处理所有客户端消息的核心业务逻辑

### Managers 模块
- **config_manager.py**: 管理配置文件加载和访问
- **database_manager.py**: 处理数据库连接和异步写入
- **logger_manager.py**: 🆕 统一日志管理，支持级别控制和彩色输出
- **task_manager.py**: 管理用户任务和进度
- **target_manager.py**: 管理雷达目标生成和更新
- **threat_manager.py**: 管理SA威胁系统

### Network 模块
- **websocket_server.py**: WebSocket服务器实现

## 🆕 日志系统特性

### 🎨 彩色日志输出
- 🔍 **DEBUG**: 青色 - 调试信息
- ✅ **INFO**: 绿色 - 一般信息
- ⚠️ **WARNING**: 黄色 - 警告信息
- ❌ **ERROR**: 红色 - 错误信息
- 🚨 **CRITICAL**: 紫色 - 严重错误

### 🔧 级别控制
```bash
# 环境变量控制
export LOG_LEVEL=DEBUG    # 显示所有日志
export LOG_LEVEL=INFO     # 默认级别
export LOG_LEVEL=WARNING  # 只显示警告和错误
export LOG_LEVEL=ERROR    # 只显示错误

# 启动时设置
LOG_LEVEL=DEBUG python start.py
```

### 📁 文件日志
```bash
# 启用文件日志（可选）
export LOG_TO_FILE=true
python start.py

# 日志文件位置: logs/radar_system_YYYY-MM-DD.log
```

### 📦 模块化日志
每个模块都有独立的日志标识：
- `database`: 数据库相关日志
- `websocket`: WebSocket服务器日志
- `config`: 配置管理日志
- `main`: 主程序日志

## 🚦 启动流程

1. **环境检查**: 检查依赖项和配置文件
2. **日志初始化**: 🆕 设置日志级别和输出格式
3. **数据库初始化**: 自动创建必要的数据库表
4. **管理器启动**: 初始化所有功能管理器
5. **服务器启动**: 启动WebSocket服务器
6. **就绪状态**: 等待客户端连接

## 🔄 从旧版本迁移

如果您之前使用的是单文件版本：

1. 新架构完全兼容旧版本的数据库
2. 配置文件路径保持不变
3. WebSocket接口保持不变
4. 🆕 所有print语句已替换为结构化日志
5. 如有问题，可随时回退到 `legacy/radar_server.py`

## 🛠️ 开发指南

### 添加新功能
1. 在相应的管理器中添加功能
2. 在 `message_handler.py` 中添加消息处理
3. 更新相应的 `__init__.py` 文件
4. 🆕 使用统一的日志系统记录操作

### 日志最佳实践
```python
# 导入日志模块
from managers.logger_manager import get_logger

# 在类中使用
class MyClass:
    def __init__(self):
        self.logger = get_logger("my_module")
    
    def do_something(self):
        self.logger.info("开始执行操作")
        try:
            # 业务逻辑
            self.logger.debug("详细的调试信息")
        except Exception as e:
            self.logger.error(f"操作失败: {e}", exc_info=True)
```

### 运行测试
```bash
# 导入测试
python tests/test_imports.py

# 日志系统测试
python tests/test_logger.py

# 功能测试
python tests/test.py
```

### 调试模式
```bash
# 启用详细日志
LOG_LEVEL=DEBUG python start.py

# 启用文件日志进行故障排查
LOG_TO_FILE=true LOG_LEVEL=DEBUG python start.py
```

## 📞 支持

如果遇到问题：
1. 查看 `docs/` 目录下的详细文档
2. 🆕 查看 `docs/logging_guide.md` 了解日志系统
3. 运行测试脚本检查环境
4. 检查日志输出中的错误信息
5. 使用 `LOG_LEVEL=DEBUG` 获取详细信息

## 📝 更新日志

- **v2.1**: 🆕 集成统一日志系统
  - 添加彩色日志输出
  - 支持日志级别控制
  - 模块化日志管理
  - 可选文件日志输出
  - 替换所有print语句
- **v2.0**: 模块化架构重构
- **v1.0**: 原始单文件版本（保留在legacy目录） 