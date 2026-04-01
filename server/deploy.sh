#!/bin/bash

# 雷达系统Docker部署脚本 v2.0
# 支持dist目录挂载的完整版本
# 使用方法: ./deploy.sh

set -e

echo "🚀 雷达系统Docker部署脚本 v2.0"
echo "=" * 50

# 检查Docker是否运行
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker未运行，请先启动Docker"
    exit 1
fi

# 检查tar包是否存在
if [ ! -f "radar-server-v2.tar" ]; then
    echo "❌ 找不到 radar-server-v2.tar 文件"
    echo "💡 请确保tar包在当前目录中"
    exit 1
fi

echo "✅ 找到镜像文件: radar-server-v2.tar"

# 检查dist目录是否存在
if [ ! -d "../dist" ]; then
    echo "❌ dist目录不存在: ../dist"
    echo "💡 请确保前端文件已构建到dist目录"
    exit 1
fi

echo "✅ 找到前端文件目录: ../dist"

# 检查public目录是否存在
if [ ! -d "../public" ]; then
    echo "⚠️  public目录不存在: ../public"
    echo "💡 将使用默认配置"
fi

# 导入镜像
echo "📦 导入Docker镜像..."
docker load -i radar-server-v2.tar

# 检查导入结果
if docker images radar-server:latest > /dev/null 2>&1; then
    echo "✅ 镜像导入成功"
else
    echo "❌ 镜像导入失败"
    exit 1
fi

# 停止并删除现有容器（如果存在）
if docker ps -a --format "table {{.Names}}" | grep -q "radar-server"; then
    echo "🛑 停止现有容器..."
    docker stop radar-server > /dev/null 2>&1 || true
    docker rm radar-server > /dev/null 2>&1 || true
fi

# 创建数据目录
mkdir -p data

# 启动新容器
echo "🚀 启动雷达系统容器..."
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

# 等待容器启动
echo "⏳ 等待容器启动..."
sleep 5

# 检查容器状态
if docker ps --format "table {{.Names}}" | grep -q "radar-server"; then
    echo "✅ 容器启动成功!"
    echo ""
    echo "📋 容器信息:"
    docker ps --filter "name=radar-server" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    
    echo ""
    echo "🌐 访问地址:"
    echo "前端应用: http://localhost:8080"
    echo "WebSocket: ws://localhost:8080/ws"
    echo "外部设备: ws://localhost:8766"
    
    echo ""
    echo "📋 管理命令:"
    echo "查看日志: docker logs radar-server"
    echo "实时日志: docker logs -f radar-server"
    echo "停止容器: docker stop radar-server"
    echo "重启容器: docker restart radar-server"
    echo "删除容器: docker rm radar-server"
    
    echo ""
    echo "🔍 检查服务状态..."
    sleep 3
    echo "最近的日志:"
    docker logs --tail 10 radar-server
    
    echo ""
    echo "🎉 部署完成！雷达系统已成功启动"
    
else
    echo "❌ 容器启动失败!"
    echo "📋 错误日志:"
    docker logs radar-server
    exit 1
fi

