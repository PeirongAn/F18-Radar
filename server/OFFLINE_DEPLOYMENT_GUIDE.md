# 雷达系统离线部署完整指南

## 📋 概述

本指南提供三种将雷达系统部署到非联网环境的方案，适用于不同的目标环境需求。

## 🎯 方案选择

| 方案 | 优势 | 适用场景 | 目标环境要求 | 包大小 |
|------|------|----------|--------------|--------|
| **Docker离线部署** | 环境一致性最好，部署最简单 | 生产环境，服务器部署 | Docker支持 | ~311MB |
| **便携式部署** | 无需安装Python，即开即用 | 快速部署，演示环境 | Windows/Linux | ~1GB |
| **离线依赖包部署** | 灵活性最高，占用空间小 | 开发环境，定制化部署 | Python 3.12+ | ~200MB |

---

## 🐳 方案一：Docker离线部署（推荐）

### 📦 准备工作

您已经有完整的Docker镜像文件：
- `radar-server-v2.tar` (311MB) - 完整版本
- `radar-server.tar` (104MB) - 轻量版本

### 📁 文件清单

将以下文件复制到目标环境：

```
radar-deployment/
├── server/
│   ├── radar-server-v2.tar          # Docker镜像文件
│   ├── deploy.bat                    # Windows部署脚本
│   ├── deploy.sh                     # Linux部署脚本
│   ├── quick-start.bat               # Windows快速启动
│   ├── quick-start.sh                # Linux快速启动
│   ├── docker-compose-v2.yml         # Docker Compose配置
│   └── data/                         # 数据目录（自动创建）
├── dist/                             # 前端文件（必需）
│   ├── index.html
│   ├── assets/
│   └── ...
└── public/                           # 配置文件（可选）
    └── agent_level.json
```

### 🚀 部署步骤

#### Windows环境：
```cmd
# 1. 进入服务器目录
cd server

# 2. 运行部署脚本
deploy.bat
```

#### Linux/macOS环境：
```bash
# 1. 进入服务器目录
cd server

# 2. 给脚本执行权限
chmod +x deploy.sh

# 3. 运行部署脚本
./deploy.sh
```

### 🌐 访问地址

部署成功后：
- **前端应用**: http://localhost:8080
- **WebSocket**: ws://localhost:8080/ws
- **外部设备**: ws://localhost:8766

### 📋 管理命令

```bash
# 查看容器状态
docker ps

# 查看日志
docker logs radar-server

# 实时查看日志
docker logs -f radar-server

# 重启服务
docker restart radar-server

# 停止服务
docker stop radar-server
```

---

## 💼 方案二：便携式部署

### 📦 创建便携包

根据您的虚拟环境位置选择对应脚本：

**如果虚拟环境在 `server/venv`（推荐）：**
```cmd
# Windows
create_portable_package_venv.bat

# Linux/macOS  
chmod +x create_portable_package.sh
./create_portable_package.sh
```

**如果虚拟环境在 `../radar_env`：**
```cmd
# Windows
create_portable_package.bat

# Linux/macOS
chmod +x create_portable_package.sh
./create_portable_package.sh
```

这将创建包含完整虚拟环境的便携包（约1GB）。

### 📁 便携包内容

```
radar-portable-package/
├── server/                    # 服务器代码
├── radar_env/                 # Python虚拟环境（完整）
├── dist/                      # 前端文件
├── public/                    # 配置文件
├── start_radar.bat            # Windows启动脚本
├── start_radar.sh             # Linux启动脚本
├── stop_radar.bat             # Windows停止脚本
└── README.md                  # 使用说明
```

### 🚀 使用方法

将便携包复制到目标环境后：

#### Windows：
```cmd
start_radar.bat
```

#### Linux/macOS：
```bash
chmod +x start_radar.sh
./start_radar.sh
```

### ✨ 特点

- ✅ **无需安装Python** - 包含完整虚拟环境
- ✅ **即开即用** - 一键启动
- ✅ **跨平台支持** - Windows/Linux/macOS
- ✅ **环境隔离** - 不影响系统Python

---

## 📦 方案三：离线依赖包部署

### 📦 创建离线包

根据您的虚拟环境位置选择对应脚本：

**如果虚拟环境在 `server/venv`（推荐）：**
```cmd
# Windows
create_offline_package_venv.bat

# Linux/macOS
chmod +x create_offline_package.sh
./create_offline_package.sh
```

**如果虚拟环境在 `../radar_env`：**
```cmd
# Windows
create_offline_package.bat

# Linux/macOS
chmod +x create_offline_package.sh
./create_offline_package.sh
```

### 📁 离线包内容

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

### 🚀 安装步骤

将离线包复制到目标环境后：

#### Windows：
```cmd
install_offline.bat
```

#### Linux/macOS：
```bash
chmod +x install_offline.sh
./install_offline.sh
```

安装完成后使用对应的启动脚本：
- Windows: `start_radar.bat`
- Linux/macOS: `./start_radar.sh`

---

## 🔧 系统要求对比

| 方案 | Python要求 | Docker要求 | 磁盘空间 | 内存要求 |
|------|------------|------------|----------|----------|
| Docker部署 | 无 | Docker 20.10+ | 500MB | 512MB |
| 便携式部署 | 无 | 无 | 1GB | 256MB |
| 离线包部署 | Python 3.12+ | 无 | 500MB | 256MB |

## 🌐 网络端口

所有方案使用相同的端口配置：

| 服务 | 端口 | 说明 |
|------|------|------|
| HTTP服务器 | 8080 | 前端应用访问 |
| WebSocket | 8080/ws | 前端WebSocket连接 |
| 外部设备 | 8765/8766 | 外部设备控制接口 |

## 🐛 故障排除

### 1. 端口冲突
```bash
# 检查端口占用
netstat -an | grep 8080
netstat -an | grep 8765

# Windows检查
netstat -an | findstr 8080
```

### 2. Docker相关问题
```bash
# 检查Docker状态
docker info

# 检查镜像
docker images

# 查看容器日志
docker logs radar-server
```

### 3. Python环境问题
```bash
# 检查Python版本
python --version
python3 --version

# 检查虚拟环境
source radar_env/bin/activate  # Linux/macOS
call radar_env\Scripts\activate.bat  # Windows
```

### 4. 权限问题

#### Linux/macOS：
```bash
# 给脚本执行权限
chmod +x *.sh

# 检查文件权限
ls -la
```

#### Windows：
- 以管理员身份运行命令提示符
- 检查防火墙设置

## 📊 性能优化建议

### Docker部署优化
```yaml
# docker-compose-v2.yml 中添加资源限制
services:
  radar-server:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1.0'
        reservations:
          memory: 512M
          cpus: '0.5'
```

### 系统优化
1. **关闭不必要的服务** - 释放端口和内存
2. **配置防火墙** - 允许8080和8765端口
3. **定期清理日志** - 避免磁盘空间不足
4. **监控资源使用** - 确保系统稳定运行

## 🔄 更新部署

### Docker更新
```bash
# 停止容器
docker stop radar-server
docker rm radar-server

# 导入新镜像
docker load -i radar-server-v2-new.tar

# 重新部署
./deploy.sh
```

### 便携式更新
1. 备份数据目录：`server/data/`
2. 替换整个便携包
3. 恢复数据目录

### 离线包更新
1. 备份数据目录
2. 重新运行安装脚本
3. 恢复数据目录

## 📝 注意事项

1. **数据备份**：定期备份 `data/` 目录中的数据库文件
2. **日志管理**：定期清理日志文件，避免磁盘空间不足
3. **安全考虑**：在生产环境中配置适当的防火墙规则
4. **监控告警**：建议配置服务监控和告警机制
5. **文档维护**：保持部署文档与实际环境同步

## 🆘 技术支持

如遇到问题，请提供以下信息：
- 操作系统版本
- 部署方案选择
- 错误日志或截图
- 系统资源使用情况

---

**选择建议**：
- 🏢 **生产环境** → Docker部署
- 🚀 **快速演示** → 便携式部署  
- 🔧 **开发调试** → 离线包部署
