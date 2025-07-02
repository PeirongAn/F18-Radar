#!/usr/bin/env python3
"""
雷达系统服务器启动脚本
提供更好的启动体验和错误处理
"""

import sys
import os
import time
import traceback

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(__file__))

def print_banner():
    """打印启动横幅"""
    print("=" * 60)
    print("🚀 雷达系统服务器 - 模块化架构")
    print("=" * 60)
    print("📁 项目结构:")
    print("  ├── 🎯 core/        - 核心业务逻辑")
    print("  ├── 🔧 managers/    - 功能管理器")
    print("  ├── 🌐 network/     - 网络通信")
    print("  ├── 💾 data/        - 数据存储")
    print("  ├── 🧪 tests/       - 测试文件")
    print("  ├── 📚 docs/        - 项目文档")
    print("  └── 📦 legacy/      - 旧版备份")
    print("=" * 60)

def check_dependencies():
    """检查依赖项"""
    print("🔍 检查依赖项...")
    try:
        import asyncio
        import websockets
        import sqlite3
        import json
        print("✅ 所有依赖项检查通过")
        return True
    except ImportError as e:
        print(f"❌ 缺少依赖项: {e}")
        print("💡 请运行: pip install -r requirements.txt")
        return False

def check_config():
    """检查配置文件"""
    print("🔍 检查配置文件...")
    config_path = "../public/agent_level.json"
    if os.path.exists(config_path):
        print("✅ 配置文件存在")
        return True
    else:
        print(f"❌ 配置文件不存在: {config_path}")
        return False

def check_database():
    """检查数据库"""
    print("🔍 检查数据库...")
    db_path = "data/radar_operations.db"
    if os.path.exists(db_path):
        print("✅ 数据库文件存在")
        return True
    else:
        print(f"❌ 数据库文件不存在: {db_path}")
        print("💡 数据库将在首次运行时自动创建")
        return True  # 数据库可以自动创建

def main():
    """主函数"""
    print_banner()
    
    # 检查环境
    if not check_dependencies():
        sys.exit(1)
    
    if not check_config():
        print("⚠️  配置文件缺失，将使用默认配置")
    
    check_database()
    
    print("🚀 启动服务器...")
    print("=" * 60)
    
    # 设置日志级别（可通过环境变量控制）
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    print(f"📋 日志级别: {log_level}")
    
    try:
        # 导入并启动主程序
        from main import main as start_server
        import asyncio
        asyncio.run(start_server())
    except KeyboardInterrupt:
        print("\n🛑 服务器已停止")
    except Exception as e:
        print(f"\n❌ 服务器启动失败: {e}")
        print("📋 详细错误信息:")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 