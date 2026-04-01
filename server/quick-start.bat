@echo off
REM 雷达系统快速启动脚本 (Windows版本)
REM 使用方法: quick-start.bat

echo 🚀 雷达系统快速启动
echo ==============================

REM 检查Docker是否运行
docker info >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker未运行，请先启动Docker
    pause
    exit /b 1
)

REM 检查镜像是否存在
docker images radar-server:latest >nul 2>&1
if errorlevel 1 (
    echo ❌ 镜像不存在，请先运行 deploy.bat 部署系统
    pause
    exit /b 1
)

REM 停止并删除现有容器
docker ps -a --format "table {{.Names}}" | findstr "radar-server" >nul 2>&1
if not errorlevel 1 (
    echo 🛑 停止现有容器...
    docker stop radar-server >nul 2>&1
    docker rm radar-server >nul 2>&1
)

REM 启动容器
echo 🚀 启动容器...
docker run -d ^
    --name radar-server ^
    -p 8080:8080 ^
    -p 8766:8765 ^
    -v "%cd%\data:/app/data" ^
    -v "%cd%\..\public:/app/public:ro" ^
    -v "%cd%\..\dist:/app/dist:ro" ^
    -e LOG_LEVEL=INFO ^
    -e PYTHONPATH=/app ^
    radar-server:latest

REM 等待启动
timeout /t 3 /nobreak >nul

REM 检查状态
docker ps --format "table {{.Names}}" | findstr "radar-server" >nul 2>&1
if not errorlevel 1 (
    echo ✅ 启动成功!
    echo 🌐 访问地址: http://localhost:8080
    echo 📋 查看日志: docker logs radar-server
) else (
    echo ❌ 启动失败!
    docker logs radar-server
)

pause

