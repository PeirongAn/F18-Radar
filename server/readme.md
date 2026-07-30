# 雷达与威胁排序系统说明
## 🚀 快速开始

**解压 radar.tar包**
### 文件目录说明
- public -- 配置项与用户手册
- dist -- 前端打包文件
- server -- 服务端（运行入口） 



### 🐍 Python环境构建

#### 1. Python版本要求
- **Python 3.7+** （推荐 Python 3.12）
- 检查Python版本：`python --version` 或 `python3 --version`

#### 2. 创建虚拟环境（推荐）
```bash
# 在项目根目录创建虚拟环境
python -m venv radar_env

# 激活虚拟环境
# Windows:
radar_env\Scripts\activate
# macOS/Linux:
source radar_env/bin/activate

# 确认虚拟环境已激活（命令行前会显示 (radar_env)）
```

#### 3. 安装依赖
```bash
# 进入server目录
cd server

# 安装所需依赖
pip install -r requirements.txt

# 或者使用国内镜像源（推荐）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
```

#### 4. 验证安装
```bash
# 测试模块导入
python tests/test_imports.py

# 如果看到 "✅ 所有模块导入成功" 表示环境配置正确
```

### 🖥️ 启动服务器

```bash
# 基本启动 - 同时提供静态文件服务和WebSocket
python main.py

```

**启动后访问：**
- 🌐 **前端应用**: http://localhost:8080/index.html
- 🔌 **WebSocket**: ws://localhost:8080/ws



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
│   ├── websocket_server.py     # WebSocket服务器
│   └── http_server.py          # HTTP静态文件服务器 🆕
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
│   ├── static_files_guide.md   # 静态文件服务指南 🆕
│   ├── README_refactoring.md   # 重构文档
│   └── readme.md              # 原始说明
│
├── 📦 legacy/                  # 旧版备份
│   ├── radar_server.py         # 原始服务器
│   └── radar_server_backup.py  # 备份文件
│
├── main.py                     # 主入口文件 ⭐
├── start.py                    # 启动脚本
├── requirements.txt            # 依赖列表 ⭐
└── README.md                   # 本文件
```


## 🔧 系统要求

### 基础要求
- **Python 3.7+** （推荐 3.12）
- **操作系统**: Windows 10+, macOS 10.14+, Linux (Ubuntu 18.04+)
- **内存**: 至少 512MB 可用内存
- **磁盘**: 至少 100MB 可用空间

### Python依赖
```txt
numpy==1.26.4          # 数值计算
matplotlib>=3.7.0       # 图形绘制
websockets>=11.0.3      # WebSocket通信
colorama>=0.4.4         # 彩色终端输出
aiohttp>=3.8.0          # HTTP服务器 🆕
```

### 可选配置
- 配置文件: `../public/agent_level.json`
- 前端构建目录: `../dist/` （用于静态文件服务）

## 📋 功能模块说明

### Core 模块
- **message_handler.py**: 处理所有客户端消息的核心业务逻辑

### Managers 模块
- **config_manager.py**: 管理配置文件加载和访问
- **database_manager.py**: 处理数据库连接和异步写入
- **logger_manager.py**: 统一日志管理，支持级别控制和彩色输出
- **task_manager.py**: 管理用户任务和进度
- **target_manager.py**: 管理雷达目标生成和更新
- **threat_manager.py**: 管理SA威胁系统

### Network 模块
- **websocket_server.py**: WebSocket服务器实现
- **🆕 http_server.py**: HTTP静态文件服务器，支持SPA应用


## 📋 配置文件说明

### agent_level.json 配置

位置：`public/agent_level.json`

这是雷达系统的核心配置文件，控制AI智能体行为、游戏难度和系统设置。

#### 🤖 AI智能体级别配置

```json
{
  "current_level": "L3",
  "levels": [
    {
      "level": "L1",
      "desc": "低级智能体，延时最长，自动处理最慢",
      "threat_select_delay_ms": 1000,
      "tdc_select_delay_ms": 1000,
      "decision_probabilities": [0.3, 0.5]
    },
    {
      "level": "L2",
      "desc": "中级智能体，延时适中",
      "threat_select_delay_ms": 500,
      "tdc_select_delay_ms": 500,
      "decision_probabilities": [0.7, 0.9]
    },
    {
      "level": "L3",
      "desc": "高级智能体，延时最短，自动处理最快",
      "threat_select_delay_ms": 100,
      "tdc_select_delay_ms": 100,
      "decision_probabilities": [0.95, 1.0]
    }
  ]
}
```

#### 智能体参数说明

| 参数 | 说明 | 单位 |
|------|------|------|
| `current_level` | 当前激活的智能体级别 | L1/L2/L3 |
| `level` | 智能体级别标识 | 字符串 |
| `desc` | 智能体描述信息 | 字符串 |
| `threat_select_delay_ms` | 威胁选择响应延时 | 毫秒 |
| `tdc_select_delay_ms` | TDC选择响应延时 | 毫秒 |
| `decision_probabilities` | 决策成功概率数组 | 0-1之间 |

服务启动时会根据各等级的 `decision_probabilities` 生成一条固定的12点统计曲线。
曲线种子可通过 `--ai-accuracy-curve-seed <整数>` 或环境变量
`AI_ACCURACY_CURVE_SEED` 指定，优先级为命令行参数、环境变量、默认值
`20260730`。更换种子后需要重启服务。

#### 🎮 游戏设置配置

```json
{
  "game_settings": {
    "current_difficulty": "high",
    "audio_enabled": true,
    "max_repetitions": 10,
    "practice_repetitions": 1,
    "difficulty_levels": {
      "high": {
        "name": "高",
        "threat_count": 10,
        "target_count": 10
      },
      "low": {
        "name": "低", 
        "threat_count": 5,
        "target_count": 5
      }
    },
    "execution_order": {
      "difficulty_order": ["high", "low"],
      "level_order": ["L0", "L1", "L2"],
      "audio_options": [true, false]
    }
  }
}
```

#### 游戏参数说明

| 参数 | 说明 | 类型 |
|------|------|------|
| `current_difficulty` | 当前游戏难度 | high/low |
| `audio_enabled` | 是否启用音频 | 布尔值 |
| `max_repetitions` | 最大重复次数 | 数字 |
| `practice_repetitions` | 练习重复次数 | 数字 |

#### 难度级别设置

| 难度 | 威胁数量 | 目标数量 | 说明 |
|------|----------|----------|------|
| **high** | 10 | 10 | 高难度模式 |
| **low** | 5 | 5 | 低难度模式 |

#### 执行顺序配置

- **difficulty_order**: 难度级别执行顺序 `["high", "low"]`
- **level_order**: 智能体级别执行顺序 `["L0", "L1", "L2"]`  
- **audio_options**: 音频选项执行顺序 `[true, false]`

### 🔧 配置修改

#### 修改智能体级别
```json
{
  "current_level": "L1"  // 改为中级智能体
}
```

#### 修改游戏难度
```json
{
  "game_settings": {
    "current_difficulty": "low"  // 改为低难度
  }
}
```

#### 自定义难度级别
```json
{
  "difficulty_levels": {
    "custom": {
      "name": "自定义",
      "threat_count": 15,
      "target_count": 15
    }
  }
}
```

#### 调整智能体响应时间
```json
{
  "levels": [
    {
      "level": "L0",
      "threat_select_delay_ms": 2000,  // 增加到2秒
      "tdc_select_delay_ms": 1500      // 增加到1.5秒
    }
  ]
}
```

### ⚠️ 配置注意事项

1. **文件格式**: 必须是有效的JSON格式
2. **编码格式**: 使用UTF-8编码保存
3. **备份配置**: 修改前建议备份原始配置
4. **重启生效**: 修改配置后需要重启服务器
5. **参数范围**: 
   - 延时时间建议在50-3000ms之间
   - 概率值必须在0-1之间
   - 数量参数必须为正整数

### 🚀 快速配置模板

#### 训练模式（慢速响应）
```json
{
  "current_level": "L0",
  "game_settings": {
    "current_difficulty": "low",
    "practice_repetitions": 3
  }
}
```

#### 测试模式（快速响应）
```json
{
  "current_level": "L2", 
  "game_settings": {
    "current_difficulty": "high",
    "max_repetitions": 5
  }
}
```

#### 无音频模式
```json
{
  "game_settings": {
    "audio_enabled": false
  }
}
```


