#!/bin/bash

# 雷达系统快速启动脚本
# 使用方法: ./quick-start.sh

echo "🚀 雷达系统快速启动"
echo "=" * 30

# 检查Docker是否运行
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker未运行，请先启动Docker"
    exit 1
fi

# 检查镜像是否存在
if ! docker images radar-server:latest > /dev/null 2>&1; then
    echo "❌ 镜像不存在，请先运行 deploy.sh 部署系统"
    exit 1
fi

# 停止并删除现有容器
if docker ps -a --format "table {{.Names}}" | grep -q "radar-server"; then
    echo "🛑 停止现有容器..."
    docker stop radar-server > /dev/null 2>&1 || true
    docker rm radar-server > /dev/null 2>&1 || true
fi

# 启动容器
echo "🚀 启动容器..."
docker run -d \
    --name radar-server \
    -p 8080:8080 \
    -p 8766:8765 \
    -v "$(pwd)/data:/app/data" \
    -v "$(pwd)/../public:/app/public:ro" \
    -v "$(pwd)/../dist:/app/dist:ro" \
    -e LOG_LEVEL=INFO \
    -e PYTHONPATH=/app \
    radar-server:latest

# 等待启动
sleep 3

# 检查状态
if docker ps --format "table {{.Names}}" | grep -q "radar-server"; then
    echo "✅ 启动成功!"
    echo "🌐 访问地址: http://localhost:8080"
    echo "📋 查看日志: docker logs radar-server"
else
    echo "❌ 启动失败!"
    docker logs radar-server
fi

