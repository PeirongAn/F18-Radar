@echo off
REM 雷达系统Docker构建脚本 (Windows版本)
REM 使用方法: build.bat [镜像名称] [标签]

setlocal enabledelayedexpansion

REM 默认参数
if "%1"=="" (
    set IMAGE_NAME=radar-server
) else (
    set IMAGE_NAME=%1
)

if "%2"=="" (
    set TAG=latest
) else (
    set TAG=%2
)

set FULL_IMAGE_NAME=%IMAGE_NAME%:%TAG%

echo 🚀 开始构建雷达系统Docker镜像...
echo 📦 镜像名称: %FULL_IMAGE_NAME%
echo ==================================================

REM 检查Docker是否运行
docker info >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker未运行，请先启动Docker
    exit /b 1
)

REM 构建镜像
echo 🔨 构建Docker镜像...
docker build -t %FULL_IMAGE_NAME% .

REM 检查构建结果
if errorlevel 1 (
    echo ❌ Docker镜像构建失败!
    exit /b 1
)

echo ✅ Docker镜像构建成功!
echo 📋 镜像信息:
docker images %IMAGE_NAME%

echo.
echo 🚀 运行容器:
echo docker run -d -p 8080:8080 -p 8765:8765 --name radar-server %FULL_IMAGE_NAME%

echo.
echo 🌐 访问地址:
echo 前端应用: http://localhost:8080
echo WebSocket: ws://localhost:8080/ws

echo.
echo 📋 其他命令:
echo 查看日志: docker logs radar-server
echo 停止容器: docker stop radar-server
echo 删除容器: docker rm radar-server

pause
