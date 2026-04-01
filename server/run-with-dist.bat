@echo off
REM 雷达系统Docker启动脚本 (支持dist目录挂载) - Windows版本
REM 使用方法: run-with-dist.bat

setlocal enabledelayedexpansion

echo 🚀 启动雷达系统Docker容器 (支持前端文件)...
echo ==================================================

REM 检查dist目录是否存在
if not exist "..\dist" (
    echo ❌ dist目录不存在: ..\dist
    echo 💡 请确保前端文件已构建到dist目录
    pause
    exit /b 1
)

echo ✅ 找到dist目录: ..\dist

REM 检查Docker是否运行
docker info >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker未运行，请先启动Docker
    pause
    exit /b 1
)

REM 停止并删除现有容器（如果存在）
docker ps -a --format "table {{.Names}}" | findstr "radar-server" >nul 2>&1
if not errorlevel 1 (
    echo 🛑 停止现有容器...
    docker stop radar-server >nul 2>&1
    docker rm radar-server >nul 2>&1
)

REM 启动新容器
echo 🚀 启动新容器...
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

REM 等待容器启动
echo ⏳ 等待容器启动...
timeout /t 5 /nobreak >nul

REM 检查容器状态
docker ps --format "table {{.Names}}" | findstr "radar-server" >nul 2>&1
if not errorlevel 1 (
    echo ✅ 容器启动成功!
    echo.
    echo 📋 容器信息:
    docker ps --filter "name=radar-server" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    
    echo.
    echo 🌐 访问地址:
    echo 前端应用: http://localhost:8080
    echo WebSocket: ws://localhost:8080/ws
    echo 外部设备: ws://localhost:8766
    
    echo.
    echo 📋 管理命令:
    echo 查看日志: docker logs radar-server
    echo 实时日志: docker logs -f radar-server
    echo 停止容器: docker stop radar-server
    echo 删除容器: docker rm radar-server
    
    echo.
    echo 🔍 检查服务状态...
    timeout /t 3 /nobreak >nul
    docker logs --tail 10 radar-server
    
) else (
    echo ❌ 容器启动失败!
    echo 📋 错误日志:
    docker logs radar-server
    pause
    exit /b 1
)

pause
