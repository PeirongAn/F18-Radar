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
from joystick import JoystickEventHandler

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
    
    # 3. 初始化操纵杆事件处理器
    info("3. 初始化操纵杆事件处理器...", "main")
    joystick_handler = JoystickEventHandler()
    
    # 4. 将操纵杆处理器集成到WebSocket服务器
    info("4. 集成操纵杆处理器到WebSocket服务器...", "main")
    websocket_server.set_joystick_handler(joystick_handler)
    
    # 5. 启动操纵杆事件处理器（在异步上下文中启动）
    info("5. 启动操纵杆事件处理器...", "main")
    # 给操纵杆处理器一个机会获取事件循环
    await asyncio.sleep(0.1)
    joystick_handler.start()
    
    info("=== 系统初始化完成 ===", "main")
    
    return joystick_handler

async def main():
    """主函数"""
    joystick_handler = None
    
    try:
        # 初始化系统
        joystick_handler = await initialize_system()
        
        # 启动WebSocket服务器
        info("6. 启动WebSocket服务器...", "main")
        # 创建服务器启动任务
        server_task = asyncio.create_task(websocket_server.start_server())
        
        # 等待服务器启动完成
        await server_task
        
    except KeyboardInterrupt:
        info("收到中断信号，正在关闭服务器...", "main")
    except Exception as e:
        error(f"服务器启动失败: {e}", "main", exc_info=True)
        sys.exit(1)
    finally:
        # 清理资源
        if joystick_handler:
            info("正在清理操纵杆资源...", "main")
            try:
                joystick_handler.stop()
            except Exception as e:
                error(f"清理操纵杆资源时出错: {e}", "main")

if __name__ == "__main__":
    info("雷达系统服务器 v2.0 - 模块化架构", "main")
    info("=" * 50, "main")
    asyncio.run(main()) 