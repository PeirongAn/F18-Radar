# 雷达系统Docker部署包使用说明

## 📦 部署包内容

- `radar-server.tar` - Docker镜像文件 (约104MB)
- `Dockerfile` - Docker构建文件
- `docker-compose.yml` - Docker Compose配置文件
- `build.sh` / `build.bat` - 构建脚本

## 🚀 快速部署

### 1. 导入Docker镜像

```bash
# 导入镜像
docker load -i radar-server.tar

# 验证镜像
docker images radar-server
```

### 2. 启动容器

#### 方式一：直接使用Docker命令
```bash
# 启动容器
docker run -d -p 8080:8080 -p 8766:8765 --name radar-server radar-server:latest

# 查看容器状态
docker ps

# 查看日志
docker logs radar-server
```

#### 方式二：使用Docker Compose
```bash
# 启动服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### 3. 访问服务

- **前端应用**: http://localhost:8080
- **WebSocket连接**: ws://localhost:8080/ws
- **外部设备端口**: 8766 (映射到容器内8765端口)

## 🔧 配置说明

### 端口映射
- `8080:8080` - HTTP服务器端口
- `8766:8765` - 外部设备WebSocket端口 (避免与现有服务冲突)

### 环境变量
- `LOG_LEVEL=INFO` - 日志级别
- `PYTHONPATH=/app` - Python路径

### 数据持久化
容器会自动创建 `data/` 目录用于存储SQLite数据库文件。

## 📋 常用命令

### 容器管理
```bash
# 启动容器
docker start radar-server

# 停止容器
docker stop radar-server

# 重启容器
docker restart radar-server

# 删除容器
docker rm radar-server
```

### 日志查看
```bash
# 查看实时日志
docker logs -f radar-server

# 查看最近100行日志
docker logs --tail 100 radar-server
```

### 进入容器
```bash
# 进入容器shell
docker exec -it radar-server /bin/bash

# 查看容器内文件
docker exec radar-server ls -la /app
```

## 🐛 故障排除

### 1. 端口冲突
如果8080或8766端口被占用，可以修改端口映射：
```bash
docker run -d -p 8081:8080 -p 8767:8765 --name radar-server radar-server:latest
```

### 2. 容器启动失败
```bash
# 查看详细错误信息
docker logs radar-server

# 检查镜像是否存在
docker images radar-server
```

### 3. 服务无法访问
```bash
# 检查容器状态
docker ps

# 检查端口映射
docker port radar-server

# 测试服务连通性
curl http://localhost:8080
```

## 📊 系统监控

### 资源使用情况
```bash
# 查看容器资源使用
docker stats radar-server

# 查看容器详细信息
docker inspect radar-server
```

### 健康检查
容器内置健康检查，每30秒检查一次服务状态。

## 🔄 更新部署

### 重新构建镜像
```bash
# 修改代码后重新构建
docker build -t radar-server:latest .

# 重新导出镜像
docker save -o radar-server.tar radar-server:latest
```

### 滚动更新
```bash
# 停止旧容器
docker stop radar-server

# 删除旧容器
docker rm radar-server

# 启动新容器
docker run -d -p 8080:8080 -p 8766:8765 --name radar-server radar-server:latest
```

## 📝 注意事项

1. **配置文件**: 容器启动时会尝试加载 `/app/public/agent_level.json` 配置文件
2. **静态文件**: 前端文件需要挂载到 `/app/dist` 目录
3. **数据备份**: 定期备份 `data/` 目录中的数据库文件
4. **日志管理**: 容器日志会持续增长，建议定期清理

## 🆘 技术支持

如遇到问题，请提供以下信息：
- Docker版本: `docker --version`
- 容器日志: `docker logs radar-server`
- 系统信息: `docker system info`
