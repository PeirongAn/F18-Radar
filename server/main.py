#!/usr/bin/env python3
"""
雷达系统服务器主入口
重构后的模块化架构
"""

import asyncio
import sys
import os

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(__file__))

from managers import config_manager, db_manager, target_manager, info, error
from network import websocket_server

async def initialize_system():
    """初始化系统组件"""
    info("=== 雷达系统初始化 ===", "main")
    
    # 1. 初始化数据库
    info("1. 初始化数据库...", "main")
    db_manager.initialize_database()
    
    # 2. 初始化目标管理器（使用默认难度）
    info("2. 初始化目标管理器...", "main")
    default_difficulty_name = config_manager.get_game_settings().get('current_difficulty', 'low')
    default_difficulty_config = config_manager.get_difficulty_levels().get(default_difficulty_name, {})
    target_manager.initialize_targets(default_difficulty_config)
    
    info("=== 系统初始化完成 ===", "main")

async def main():
    """主函数"""
    try:
        # 初始化系统
        await initialize_system()
        
        # 启动WebSocket服务器
        await websocket_server.start_server()
        
    except KeyboardInterrupt:
        info("收到中断信号，正在关闭服务器...", "main")
    except Exception as e:
        error(f"服务器启动失败: {e}", "main", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    info("雷达系统服务器 v2.0 - 模块化架构", "main")
    info("=" * 50, "main")
    asyncio.run(main()) 