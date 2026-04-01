# 雷达系统Docker部署包 v2.0 使用说明

## 📦 部署包内容

- `radar-server-v2.tar` - Docker镜像文件 (约311MB)
- `deploy.sh` / `deploy.bat` - 完整部署脚本
- `quick-start.sh` / `quick-start.bat` - 快速启动脚本
- `docker-compose-v2.yml` - Docker Compose配置文件
- `Dockerfile` - Docker构建文件
- `DOCKER_DEPLOYMENT.md` - 详细部署说明

## 🚀 快速部署

### 方法一：使用部署脚本（推荐）

#### Linux/macOS:
```bash
# 给脚本执行权限
chmod +x deploy.sh

# 运行部署脚本
./deploy.sh
```

#### Windows:
```cmd
# 直接运行批处理文件
deploy.bat
```

### 方法二：使用Docker Compose

```bash
# 导入镜像
docker load -i radar-server-v2.tar

# 启动服务
docker-compose -f docker-compose-v2.yml up -d

# 查看状态
docker-compose -f docker-compose-v2.yml ps
```

### 方法三：手动部署

```bash
# 1. 导入镜像
docker load -i radar-server-v2.tar

# 2. 创建数据目录
mkdir -p data

# 3. 启动容器
docker run -d \
    --name radar-server \
    -p 8080:8080 \
    -p 8766:8765 \
    -v "$(pwd)/data:/app/data" \
    -v "$(pwd)/../public:/app/public:ro" \
    -v "$(pwd)/../dist:/app/dist:ro" \
    -e LOG_LEVEL=INFO \
    -e PYTHONPATH=/app \
    --restart unless-stopped \
    radar-server:latest
```

## 🔄 快速启动

如果已经部署过，可以使用快速启动脚本：

#### Linux/macOS:
```bash
chmod +x quick-start.sh
./quick-start.sh
```

#### Windows:
```cmd
quick-start.bat
```

## 📋 目录结构要求

部署前请确保以下目录结构：

```
project/
├── server/                 # 当前目录
│   ├── radar-server-v2.tar # Docker镜像文件
│   ├── deploy.sh           # 部署脚本
│   └── data/               # 数据目录（自动创建）
├── dist/                   # 前端文件目录（必需）
│   ├── index.html
│   ├── assets/
│   └── ...
└── public/                 # 配置文件目录（可选）
    └── agent_level.json
```

## 🌐 访问地址

部署成功后，可以通过以下地址访问：

- **前端应用**: http://localhost:8080
- **WebSocket连接**: ws://localhost:8080/ws
- **外部设备端口**: ws://localhost:8766

## 📋 常用管理命令

### 容器管理
```bash
# 查看容器状态
docker ps

# 查看日志
docker logs radar-server

# 实时查看日志
docker logs -f radar-server

# 停止容器
docker stop radar-server

# 重启容器
docker restart radar-server

# 删除容器
docker rm radar-server
```

### 使用Docker Compose
```bash
# 启动服务
docker-compose -f docker-compose-v2.yml up -d

# 停止服务
docker-compose -f docker-compose-v2.yml down

# 查看日志
docker-compose -f docker-compose-v2.yml logs -f

# 重启服务
docker-compose -f docker-compose-v2.yml restart
```

## 🔧 配置说明

### 端口映射
- `8080:8080` - HTTP服务器端口
- `8766:8765` - 外部设备WebSocket端口（避免冲突）

### 卷挂载
- `./data:/app/data` - 数据持久化
- `../public:/app/public:ro` - 配置文件（只读）
- `../dist:/app/dist:ro` - 前端文件（只读）

### 环境变量
- `LOG_LEVEL=INFO` - 日志级别
- `PYTHONPATH=/app` - Python路径

## 🐛 故障排除

### 1. 端口冲突
如果8080或8766端口被占用，可以修改端口映射：
```bash
docker run -d --name radar-server -p 8081:8080 -p 8767:8765 ...
```

### 2. 目录不存在
确保以下目录存在：
- `../dist` - 前端文件目录
- `../public` - 配置文件目录（可选）

### 3. 权限问题
确保Docker有权限访问挂载的目录。

### 4. 容器启动失败
```bash
# 查看详细错误
docker logs radar-server

# 检查镜像是否存在
docker images radar-server:latest
```

## 📊 系统监控

### 资源使用
```bash
# 查看容器资源使用
docker stats radar-server

# 查看容器详细信息
docker inspect radar-server
```

### 健康检查
容器内置健康检查，每30秒检查一次服务状态。

## 🔄 更新部署

### 更新镜像
```bash
# 停止容器
docker stop radar-server
docker rm radar-server

# 导入新镜像
docker load -i radar-server-v2-new.tar

# 重新部署
./deploy.sh
```

### 备份数据
```bash
# 备份数据目录
cp -r data data-backup-$(date +%Y%m%d)
```

## 📝 注意事项

1. **前端文件**: 确保 `../dist` 目录包含完整的前端构建文件
2. **配置文件**: `../public` 目录包含系统配置文件（可选）
3. **数据持久化**: 数据存储在 `./data` 目录中
4. **网络访问**: 确保防火墙允许8080和8766端口访问
5. **Docker版本**: 建议使用Docker 20.10+版本

## 🆘 技术支持

如遇到问题，请提供以下信息：
- 操作系统版本
- Docker版本: `docker --version`
- 容器日志: `docker logs radar-server`
- 错误截图或日志

