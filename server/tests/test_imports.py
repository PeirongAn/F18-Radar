#!/usr/bin/env python3
"""
测试所有模块导入是否正确
"""

import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def test_imports():
    """测试所有模块导入"""
    print("🧪 开始测试模块导入...")
    
    try:
        # 测试managers模块
        print("📦 测试 managers 模块...")
        from managers import (
            config_manager, ConfigManager,
            db_manager, DatabaseManager,
            TaskScenarioManager, generate_task_id,
            target_manager, TargetManager,
            threat_manager, ThreatManager,
            get_logger_manager, get_logger, set_log_level,
            debug, info, warning, error, critical
        )
        print("✅ managers 模块导入成功")
        
        # 测试core模块
        print("📦 测试 core 模块...")
        from core import message_handler, MessageHandler
        print("✅ core 模块导入成功")
        
        # 测试network模块
        print("📦 测试 network 模块...")
        from network import websocket_server, WebSocketServer
        print("✅ network 模块导入成功")
        
        print("🎉 所有模块导入测试通过！")
        return True
        
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 其他错误: {e}")
        return False

def test_main_import():
    """测试主文件导入"""
    print("🧪 测试主文件导入...")
    
    try:
        # 导入主文件中使用的模块
        from managers import config_manager, db_manager, target_manager, info, error
        from network import websocket_server
        print("✅ 主文件导入测试通过！")
        return True
    except Exception as e:
        print(f"❌ 主文件导入错误: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 雷达系统模块导入测试")
    print("=" * 50)
    
    success = True
    success &= test_imports()
    success &= test_main_import()
    
    print("=" * 50)
    if success:
        print("🎉 所有测试通过！新架构可以正常使用。")
    else:
        print("❌ 部分测试失败，请检查导入路径。")
    print("=" * 50) 