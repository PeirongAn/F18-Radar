#!/bin/bash
# 创建Python离线部署包脚本 (Linux/macOS版本)
# 使用方法: chmod +x create_offline_package.sh && ./create_offline_package.sh

echo "📦 创建Python离线部署包"
echo "=================================================="

# 检查Python是否存在
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3未安装，请先安装Python 3.12"
    exit 1
fi

echo "✅ Python版本检查通过"

# 创建离线包目录
OFFLINE_DIR="radar-offline-package"
if [ -d "$OFFLINE_DIR" ]; then
    rm -rf "$OFFLINE_DIR"
fi
mkdir -p "$OFFLINE_DIR"

echo "📁 创建目录结构..."

# 复制服务器代码（排除不需要的文件）
rsync -av --exclude='__pycache__' \
          --exclude='*.pyc' \
          --exclude='venv' \
          --exclude='radar_env' \
          --exclude='*.tar' \
          --exclude='node_modules' \
          . "$OFFLINE_DIR/server/"

# 复制前端文件
if [ -d "../dist" ]; then
    cp -r "../dist" "$OFFLINE_DIR/"
    echo "✅ 复制前端文件完成"
else
    echo "⚠️ 前端文件不存在，请先构建前端项目"
fi

# 复制配置文件
if [ -d "../public" ]; then
    cp -r "../public" "$OFFLINE_DIR/"
    echo "✅ 复制配置文件完成"
fi

# 下载Python依赖包
echo "📦 下载Python依赖包..."
mkdir -p "$OFFLINE_DIR/python-packages"

# 使用pip download下载所有依赖
pip3 download -r requirements.txt -d "$OFFLINE_DIR/python-packages"

if [ $? -ne 0 ]; then
    echo "❌ 依赖包下载失败"
    exit 1
fi

echo "✅ Python依赖包下载完成"

# 创建离线安装脚本
echo "📝 创建离线安装脚本..."

# Linux/macOS安装脚本
cat > "$OFFLINE_DIR/install_offline.sh" << 'EOF'
#!/bin/bash
# 雷达系统离线安装脚本
# 使用方法: chmod +x install_offline.sh && ./install_offline.sh

echo "🚀 雷达系统离线安装"
echo "=================================================="

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3未安装，请先安装Python 3.12"
    exit 1
fi

echo "✅ Python版本检查通过"

# 创建虚拟环境
echo "📦 创建虚拟环境..."
python3 -m venv radar_env

# 激活虚拟环境并安装依赖
echo "📦 安装Python依赖..."
source radar_env/bin/activate
pip install --no-index --find-links python-packages -r server/requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ 依赖安装失败"
    exit 1
fi

echo "✅ 依赖安装完成"

# 创建启动脚本
echo "📝 创建启动脚本..."
cat > start_radar.sh << 'SCRIPT_EOF'
#!/bin/bash
cd "$(dirname "$0")"
source radar_env/bin/activate
cd server
python main.py
SCRIPT_EOF

chmod +x start_radar.sh

echo "🎉 安装完成！"
echo
echo "📋 使用说明:"
echo "1. 运行 ./start_radar.sh 启动服务器"
echo "2. 访问 http://localhost:8080 使用系统"
echo "3. WebSocket端口: ws://localhost:8080/ws"
echo "4. 外部设备端口: 8765"
echo
EOF

chmod +x "$OFFLINE_DIR/install_offline.sh"

# Windows安装脚本
cat > "$OFFLINE_DIR/install_offline.bat" << 'EOF'
@echo off
REM 雷达系统离线安装脚本
REM 使用方法: install_offline.bat

echo 🚀 雷达系统离线安装
echo ==================================================

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python未安装，请先安装Python 3.12
    pause
    exit /b 1
)

echo ✅ Python版本检查通过

REM 创建虚拟环境
echo 📦 创建虚拟环境...
python -m venv radar_env

REM 激活虚拟环境并安装依赖
echo 📦 安装Python依赖...
call radar_env\Scripts\activate.bat
pip install --no-index --find-links python-packages -r server\requirements.txt

if errorlevel 1 (
    echo ❌ 依赖安装失败
    pause
    exit /b 1
)

echo ✅ 依赖安装完成

REM 创建启动脚本
echo 📝 创建启动脚本...
(
echo @echo off
echo cd /d "%%~dp0"
echo call radar_env\Scripts\activate.bat
echo cd server
echo python main.py
echo pause
) > start_radar.bat

echo 🎉 安装完成！
echo.
echo 📋 使用说明:
echo 1. 运行 start_radar.bat 启动服务器
echo 2. 访问 http://localhost:8080 使用系统
echo 3. WebSocket端口: ws://localhost:8080/ws
echo 4. 外部设备端口: 8765

pause
EOF

# 创建README文件
cat > "$OFFLINE_DIR/README.md" << 'EOF'
# 雷达系统离线部署包

## 📦 包内容

- `server/` - 服务器代码
- `dist/` - 前端文件
- `public/` - 配置文件
- `python-packages/` - Python依赖包
- `install_offline.bat` - Windows安装脚本
- `install_offline.sh` - Linux/macOS安装脚本

## 🚀 安装步骤

### Windows:
```cmd
install_offline.bat
```

### Linux/macOS:
```bash
chmod +x install_offline.sh
./install_offline.sh
```

## 📋 系统要求

- Python 3.12+
- 约500MB磁盘空间
- 端口8080和8765可用

## 🌐 访问地址

- 前端应用: http://localhost:8080
- WebSocket: ws://localhost:8080/ws
- 外部设备: ws://localhost:8765

## 🔧 故障排除

1. 确保Python 3.12已安装
2. 确保端口8080和8765未被占用
3. 检查防火墙设置

EOF

echo "✅ 离线部署包创建完成！"
echo
echo "📁 部署包位置: $OFFLINE_DIR"
echo "📦 包大小: $(du -sh $OFFLINE_DIR | cut -f1)"

echo
echo "📋 下一步:"
echo "1. 将整个 $OFFLINE_DIR 文件夹复制到目标环境"
echo "2. 在目标环境运行对应的安装脚本"
echo "3. 使用 start_radar 脚本启动服务器"
