@echo off
REM 雷达系统Docker部署脚本 v2.0 (Windows版本)
REM 支持dist目录挂载的完整版本
REM 使用方法: deploy.bat

setlocal enabledelayedexpansion

echo 🚀 雷达系统Docker部署脚本 v2.0
echo ==================================================

REM 检查Docker是否运行
docker info >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker未运行，请先启动Docker
    pause
    exit /b 1
)

REM 检查tar包是否存在
if not exist "radar-server-v2.tar" (
    echo ❌ 找不到 radar-server-v2.tar 文件
    echo 💡 请确保tar包在当前目录中
    pause
    exit /b 1
)

echo ✅ 找到镜像文件: radar-server-v2.tar

REM 检查dist目录是否存在
if not exist "..\dist" (
    echo ❌ dist目录不存在: ..\dist
    echo 💡 请确保前端文件已构建到dist目录
    pause
    exit /b 1
)

echo ✅ 找到前端文件目录: ..\dist

REM 检查public目录是否存在
if not exist "..\public" (
    echo ⚠️  public目录不存在: ..\public
    echo 💡 将使用默认配置
)

REM 导入镜像
echo 📦 导入Docker镜像...
docker load -i radar-server-v2.tar

REM 检查导入结果
docker images radar-server:latest >nul 2>&1
if errorlevel 1 (
    echo ❌ 镜像导入失败
    pause
    exit /b 1
)

echo ✅ 镜像导入成功

REM 停止并删除现有容器（如果存在）
docker ps -a --format "table {{.Names}}" | findstr "radar-server" >nul 2>&1
if not errorlevel 1 (
    echo 🛑 停止现有容器...
    docker stop radar-server >nul 2>&1
    docker rm radar-server >nul 2>&1
)

REM 创建数据目录
if not exist "data" mkdir data

REM 启动新容器
echo 🚀 启动雷达系统容器...
docker run -d ^
    --name radar-server ^
    -p 8080:8080 ^
    -p 8766:8765 ^
    -v "%cd%\data:/app/data" ^
    -v "%cd%\..\public:/app/public:ro" ^
    -v "%cd%\..\dist:/app/dist:ro" ^
    -e LOG_LEVEL=INFO ^
    -e PYTHONPATH=/app ^
    --restart unless-stopped ^
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
    echo 重启容器: docker restart radar-server
    echo 删除容器: docker rm radar-server
    
    echo.
    echo 🔍 检查服务状态...
    timeout /t 3 /nobreak >nul
    echo 最近的日志:
    docker logs --tail 10 radar-server
    
    echo.
    echo 🎉 部署完成！雷达系统已成功启动
    
) else (
    echo ❌ 容器启动失败!
    echo 📋 错误日志:
    docker logs radar-server
    pause
    exit /b 1
)

pause

