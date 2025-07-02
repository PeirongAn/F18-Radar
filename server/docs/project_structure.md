# 雷达系统服务器项目结构

## 目录结构

```
server/
├── main.py                     # 主入口文件
├── requirements.txt            # Python依赖
│
├── docs/                       # 📚 文档目录
│   ├── README_refactoring.md   # 重构说明
│   ├── readme.md              # 原始说明
│   └── project_structure.md   # 项目结构说明 (本文件)
│
├── core/                       # 🎯 核心业务逻辑
│   ├── __init__.py
│   └── message_handler.py      # 消息处理器
│
├── managers/                   # 🔧 管理器模块
│   ├── __init__.py
│   ├── config_manager.py       # 配置管理
│   ├── database_manager.py     # 数据库管理
│   ├── task_manager.py         # 任务管理
│   ├── target_manager.py       # 目标管理
│   └── threat_manager.py       # 威胁管理
│
├── network/                    # 🌐 网络通信
│   ├── __init__.py
│   └── websocket_server.py     # WebSocket服务器
│
├── data/                       # 💾 数据文件
│   ├── radar_operations.db     # 主数据库
│   ├── radar_operations.db-wal # WAL文件
│   └── radar_operations.db-shm # 共享内存文件
│
├── tests/                      # 🧪 测试文件
│   ├── __init__.py
│   ├── test.py                 # 主测试文件
│   └── test_connection.py      # 连接测试
│
└── legacy/                     # 📦 旧版本备份
    ├── radar_server.py         # 原始服务器文件
    └── radar_server_backup.py  # 备份文件
```

## 模块说明

### 📁 core/ - 核心业务逻辑
- **message_handler.py**: 处理客户端消息的核心业务逻辑
  - 消息路由和分发
  - 业务流程控制
  - 状态管理

### 📁 managers/ - 管理器模块
- **config_manager.py**: 配置文件管理
  - 加载 `agent_level.json`
  - 提供配置访问接口
  
- **database_manager.py**: 数据库操作管理
  - 异步写入队列
  - 连接池管理
  - 表结构维护
  
- **task_manager.py**: 任务场景管理
  - 用户进度跟踪
  - 任务队列管理
  - AI/手动模式切换
  
- **target_manager.py**: 雷达目标管理
  - 目标生成和更新
  - 威胁评估算法
  - 位置计算
  
- **threat_manager.py**: SA威胁管理
  - 威胁生成
  - 紧急事件处理
  - 自动推送

### 📁 network/ - 网络通信
- **websocket_server.py**: WebSocket服务器
  - 客户端连接管理
  - 消息收发
  - 会话状态维护

### 📁 data/ - 数据文件
- 包含SQLite数据库文件
- 用户操作记录
- 任务进度数据

### 📁 tests/ - 测试文件
- 单元测试
- 集成测试
- 连接测试

### 📁 legacy/ - 旧版本
- 保留原始单文件版本
- 用于回退和对比

## 启动方式

### 方式一：使用新架构 (推荐)
```bash
cd server
python main.py
```

### 方式二：使用旧版本 (兼容)
```bash
cd server/legacy
python radar_server.py
```

## 导入关系

```
main.py
├── managers/
│   ├── config_manager
│   ├── db_manager
│   └── target_manager
└── network/
    └── websocket_server
        ├── managers/ (config, target)
        └── core/
            └── message_handler
                └── managers/ (all)
```

## 优势

1. **清晰的职责分离**: 每个模块专注于特定功能
2. **易于维护**: 修改某个功能不影响其他模块
3. **便于测试**: 每个模块可以独立测试
4. **扩展性强**: 可以轻松添加新的管理器或功能
5. **团队协作**: 不同开发者可以并行开发不同模块

## 配置要求

- Python 3.7+
- 依赖包见 `requirements.txt`
- 配置文件 `../public/agent_level.json`

## 数据库位置

数据库文件位于 `data/` 目录下：
- `radar_operations.db`: 主数据库
- `radar_operations.db-wal`: WAL日志
- `radar_operations.db-shm`: 共享内存

## 注意事项

1. 确保所有 `__init__.py` 文件存在
2. 导入路径使用相对导入
3. 数据库文件路径需要相应调整
4. 保持向后兼容性 