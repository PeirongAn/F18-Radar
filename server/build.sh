#!/bin/bash

# 雷达系统Docker构建脚本
# 使用方法: ./build.sh [镜像名称] [标签]

set -e

# 默认参数
IMAGE_NAME=${1:-"radar-server"}
TAG=${2:-"latest"}
FULL_IMAGE_NAME="${IMAGE_NAME}:${TAG}"

echo "🚀 开始构建雷达系统Docker镜像..."
echo "📦 镜像名称: ${FULL_IMAGE_NAME}"
echo "=" * 50

# 检查Docker是否运行
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker未运行，请先启动Docker"
    exit 1
fi

# 构建镜像
echo "🔨 构建Docker镜像..."
docker build -t "${FULL_IMAGE_NAME}" .

# 检查构建结果
if [ $? -eq 0 ]; then
    echo "✅ Docker镜像构建成功!"
    echo "📋 镜像信息:"
    docker images "${IMAGE_NAME}"
    
    echo ""
    echo "🚀 运行容器:"
    echo "docker run -d -p 8080:8080 -p 8765:8765 --name radar-server ${FULL_IMAGE_NAME}"
    
    echo ""
    echo "🌐 访问地址:"
    echo "前端应用: http://localhost:8080"
    echo "WebSocket: ws://localhost:8080/ws"
    
    echo ""
    echo "📋 其他命令:"
    echo "查看日志: docker logs radar-server"
    echo "停止容器: docker stop radar-server"
    echo "删除容器: docker rm radar-server"
    
else
    echo "❌ Docker镜像构建失败!"
    exit 1
fi
