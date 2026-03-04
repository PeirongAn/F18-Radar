#!/usr/bin/env python3
"""
雷达系统服务器主入口
重构后的模块化架构
支持静态文件服务和WebSocket连接
"""

import asyncio
import sys
import os
import argparse

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(__file__))

from managers import config_manager, db_manager, target_manager, info, error
from network import websocket_server
from joystick.joystick_event_handler import JoystickEventHandler
from network.http_server import http_server

async def initialize_system():
    """初始化系统组件"""
    info("=== 雷达系统初始化 ===", "main")
    
    # 1. 初始化数据库
    info("1. 初始化数据库...", "main")
    db_manager.initialize_database()
    info("✅ 数据库初始化完成", "main")
    
    # 2. 初始化目标管理器（使用默认难度）
    info("2. 初始化目标管理器...", "main")
    default_difficulty_name = config_manager.get_game_settings().get('current_difficulty', 'low')
    default_difficulty_config = config_manager.get_difficulty_levels().get(default_difficulty_name, {})
    target_manager.initialize_targets(default_difficulty_config)
    info("✅ 目标管理器初始化完成", "main")
    
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

def setup_static_directory(static_dir=None):
    """设置静态文件目录"""
    if static_dir:
        # 使用用户指定的目录
        if not os.path.isabs(static_dir):
            # 相对路径转换为绝对路径
            static_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), static_dir))
    else:
        # 默认使用项目根目录下的 dist 文件夹
        static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dist')
    
    info(f"静态文件目录设置为: {static_dir}", "main")
    
    # 检查目录是否存在
    if os.path.exists(static_dir):
        info("静态文件目录存在，可以提供前端文件服务", "main")
    else:
        info("静态文件目录不存在，请确保已将前端文件打包到该目录", "main")
        info("提示: 使用 'npm run build' 或 'pnpm build' 构建前端项目", "main")
    
    return static_dir

def setup_static_directory(static_dir=None):
    """设置静态文件目录"""
    if static_dir:
        # 使用用户指定的目录
        if not os.path.isabs(static_dir):
            # 相对路径转换为绝对路径
            static_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), static_dir))
    else:
        # 默认使用项目根目录下的 dist 文件夹
        static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dist')
    
    info(f"静态文件目录设置为: {static_dir}", "main")
    
    # 检查目录是否存在
    if os.path.exists(static_dir):
        info("静态文件目录存在，可以提供前端文件服务", "main")
    else:
        info("静态文件目录不存在，请确保已将前端文件打包到该目录", "main")
        info("提示: 使用 'npm run build' 或 'pnpm build' 构建前端项目", "main")
    
    return static_dir

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='雷达系统服务器')
    parser.add_argument('--static-dir', type=str, help='静态文件目录路径 (默认: ../dist)')
    parser.add_argument('--http-port', type=int, default=8080, help='HTTP服务器端口 (默认: 8080)')
    parser.add_argument('--ws-only', action='store_true', help='仅启动WebSocket服务器（不提供静态文件服务）')
    args = parser.parse_args()
    
    joystick_handler = None
    
    try:
        # 初始化系统
        joystick_handler = await initialize_system()
        
        if args.ws_only:
            # 仅启动WebSocket服务器
            info("启动模式: 仅WebSocket服务器", "main")
            await websocket_server.start_server()
        else:
            # 启动HTTP服务器（包含静态文件服务和WebSocket）
            info("启动模式: HTTP服务器 (静态文件 + WebSocket)", "main")
            
            # 设置静态文件目录
            static_dir = setup_static_directory(args.static_dir)
            
            # 配置HTTP服务器
            http_server.port = args.http_port
            http_server.update_static_directory(static_dir)
            
            # 启动HTTP服务器
            await http_server.start_server()
        
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
    info("支持静态文件服务和WebSocket连接", "main")
    info("=" * 50, "main")
    asyncio.run(main()) 