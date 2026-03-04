# 雷达系统离线部署指南 (使用 server/venv)

## 📋 概述

本指南专门针对使用 `server/venv` 虚拟环境的雷达系统，提供完整的离线部署解决方案。

## ✅ 环境验证

运行测试脚本确认环境准备就绪：
```cmd
test_venv_scripts.bat
```

测试内容包括：
- ✅ 虚拟环境存在性检查
- ✅ Python 和 pip 功能测试
- ✅ 依赖文件完整性检查
- ✅ 前端文件和配置文件检查

## 🎯 部署方案选择

### 方案一：便携式部署（推荐）

**特点**：
- ✅ 包含完整虚拟环境
- ✅ 目标环境无需安装Python
- ✅ 一键启动，即开即用
- 📦 包大小：约1GB

**创建便携包**：
```cmd
create_portable_package_venv.bat
```

**使用方法**：
1. 将生成的 `radar-portable-package` 文件夹复制到目标环境
2. 运行启动脚本：
   - Windows: `start_radar.bat`
   - Linux/macOS: `./start_radar.sh`

### 方案二：离线依赖包部署

**特点**：
- ✅ 包大小较小
- ✅ 适合有Python环境的目标机器
- ✅ 灵活性高
- 📦 包大小：约200MB

**创建离线包**：
```cmd
create_offline_package_venv.bat
```

**使用方法**：
1. 将生成的 `radar-offline-package` 文件夹复制到目标环境
2. 运行安装脚本：
   - Windows: `install_offline.bat`
   - Linux/macOS: `./install_offline.sh`
3. 使用生成的启动脚本运行系统

### 方案三：Docker部署（最稳定）

**特点**：
- ✅ 环境一致性最好
- ✅ 部署最简单
- ✅ 适合生产环境
- 📦 包大小：约311MB

**使用现有Docker镜像**：
```cmd
deploy.bat  # Windows
./deploy.sh # Linux/macOS
```

## 📁 文件结构说明

### 便携式部署包结构
```
radar-portable-package/
├── server/                    # 服务器代码
├── venv/                      # Python虚拟环境（完整）
├── dist/                      # 前端文件
├── public/                    # 配置文件
├── start_radar.bat            # Windows启动脚本
├── start_radar.sh             # Linux启动脚本
├── stop_radar.bat             # Windows停止脚本
└── README.md                  # 使用说明
```

### 离线依赖包结构
```
radar-offline-package/
├── server/                    # 服务器代码
├── python-packages/           # Python依赖包
├── dist/                      # 前端文件
├── public/                    # 配置文件
├── install_offline.bat        # Windows安装脚本
├── install_offline.sh         # Linux安装脚本
└── README.md                  # 使用说明
```

## 🚀 快速开始

### 步骤1：选择部署方案
根据目标环境选择合适的部署方案：
- 目标环境无Python → **便携式部署**
- 目标环境有Python → **离线依赖包部署**
- 目标环境有Docker → **Docker部署**

### 步骤2：创建部署包
```cmd
# 便携式部署
create_portable_package_venv.bat

# 或离线依赖包部署
create_offline_package_venv.bat
```

### 步骤3：复制到目标环境
将生成的整个文件夹复制到目标环境。

### 步骤4：在目标环境部署
```cmd
# 便携式部署 - 直接运行
start_radar.bat

# 离线依赖包部署 - 先安装后运行
install_offline.bat
# 然后运行
start_radar.bat
```

## 🌐 访问地址

部署成功后，通过以下地址访问：
- **前端应用**: http://localhost:8080
- **WebSocket**: ws://localhost:8080/ws
- **外部设备**: ws://localhost:8765

## 🔧 故障排除

### 1. 虚拟环境问题
```cmd
# 检查虚拟环境
test_venv_scripts.bat

# 重新激活虚拟环境
call venv\Scripts\activate.bat
```

### 2. 端口冲突
```cmd
# 检查端口占用
netstat -an | findstr 8080
netstat -an | findstr 8765
```

### 3. 依赖问题
```cmd
# 检查已安装的包
pip list

# 重新安装依赖
pip install -r requirements.txt
```

### 4. 前端文件缺失
```cmd
# 检查前端文件
dir ..\dist

# 如果缺失，需要构建前端
cd ..
npm run build
# 或
pnpm build
```

## 📋 系统要求

### 便携式部署
- 磁盘空间：1GB+
- 端口：8080, 8765可用
- 操作系统：Windows 10+, Linux, macOS

### 离线依赖包部署
- Python：3.12+
- 磁盘空间：500MB+
- 端口：8080, 8765可用
- 操作系统：Windows 10+, Linux, macOS

### Docker部署
- Docker：20.10+
- 磁盘空间：500MB+
- 端口：8080, 8766可用

## 🔄 更新部署

### 便携式部署更新
1. 备份数据：`server/data/`
2. 重新创建便携包
3. 替换除数据目录外的所有文件
4. 恢复数据目录

### 离线包部署更新
1. 备份数据：`server/data/`
2. 重新运行安装脚本
3. 恢复数据目录

## 📝 注意事项

1. **数据备份**：部署前备份 `server/data/` 目录
2. **防火墙设置**：确保端口8080和8765开放
3. **权限问题**：Windows环境可能需要管理员权限
4. **路径问题**：避免使用包含空格或特殊字符的路径
5. **编码问题**：如遇中文显示问题，使用 `*_fixed.bat` 版本脚本

## 🆘 技术支持

如遇问题，请提供：
- 操作系统版本
- 使用的部署方案
- 错误信息或日志
- `test_venv_scripts.bat` 的运行结果

---

**推荐流程**：
1. 运行 `test_venv_scripts.bat` 验证环境
2. 选择合适的部署方案
3. 创建部署包
4. 在目标环境测试部署
5. 配置防火墙和访问权限
