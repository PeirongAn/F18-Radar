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
from network.http_server import http_server
# from network.external_device_server import start_external_device_client  # 已注释，客户端直接连接

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

def setup_static_directory(static_dir=None):
    """设置静态文件目录"""
    if static_dir:
        # 使用用户指定的目录
        if not os.path.isabs(static_dir):
            # 相对路径转换为绝对路径
            static_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), static_dir))
    else:
        # 检查是否在Docker容器中运行
        if os.path.exists('/app/dist'):
            # Docker容器环境，使用容器内的路径
            static_dir = '/app/dist'
        else:
            # 本地开发环境，使用项目根目录下的 dist 文件夹
            static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dist')
    
    info(f"静态文件目录设置为: {static_dir}", "main")
    
    # 检查目录是否存在
    if os.path.exists(static_dir):
        info("静态文件目录存在，可以提供前端文件服务", "main")
        # 列出目录内容以便调试
        try:
            files = os.listdir(static_dir)
            info(f"静态文件目录包含 {len(files)} 个文件/目录", "main")
            if 'index.html' in files:
                info("✅ 找到 index.html 文件", "main")
            else:
                info("⚠️ 未找到 index.html 文件", "main")
        except Exception as e:
            info(f"无法读取静态文件目录: {e}", "main")
    else:
        info("静态文件目录不存在，请确保已将前端文件打包到该目录", "main")
        info("提示: 使用 'npm run build' 或 'pnpm build' 构建前端项目", "main")
    
    return static_dir

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='雷达系统服务器')
    parser.add_argument('--static-dir', type=str, help='静态文件目录路径 (默认: ../dist)')
    parser.add_argument('--http-port', type=int, default=8080, help='HTTP服务器端口 (默认: 8080)')
    parser.add_argument('--external-port', type=int, default=8765, help='外部设备WebSocket服务端口 (默认: 8765)')
    parser.add_argument('--ws-only', action='store_true', help='仅启动WebSocket服务器（不提供静态文件服务）')
    parser.add_argument('--no-external', action='store_true', help='不启动外部设备WebSocket客户端')
    args = parser.parse_args()
    
    try:
        # 初始化系统
        await initialize_system()
        
        # 创建任务列表
        tasks = []
        
        # 启动外部设备WebSocket客户端（除非明确禁用） - 已注释，客户端直接连接8765端口
        # if not args.no_external:
        #     info(f"启动外部设备WebSocket客户端，连接到端口: {args.external_port}", "main")
        #     # 异步启动外部设备客户端，不阻塞主流程
        #     tasks.append(asyncio.create_task(start_external_device_client("localhost", args.external_port)))
        # else:
        #     info("外部设备WebSocket客户端已禁用", "main")
        info("外部设备TDC控制: 客户端直接连接8765端口，服务器端转发已禁用", "main")
        
        if args.ws_only:
            # 仅启动WebSocket服务器
            info("启动模式: 仅WebSocket服务器", "main")
            tasks.append(asyncio.create_task(websocket_server.start_server()))
        else:
            # 启动HTTP服务器（包含静态文件服务和WebSocket）
            info("启动模式: HTTP服务器 (静态文件 + WebSocket)", "main")
            
            # 设置静态文件目录
            static_dir = setup_static_directory(args.static_dir)
            
            # 配置HTTP服务器
            http_server.port = args.http_port
            http_server.update_static_directory(static_dir)
            
            # 启动HTTP服务器
            tasks.append(asyncio.create_task(http_server.start_server()))
        
        # 等待所有任务完成
        if tasks:
            await asyncio.gather(*tasks)
        
    except KeyboardInterrupt:
        info("收到中断信号，正在关闭服务器...", "main")
    except Exception as e:
        error(f"服务器启动失败: {e}", "main", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    info("雷达系统服务器 v2.0 - 模块化架构", "main")
    info("支持静态文件服务和WebSocket连接", "main")
    info("=" * 50, "main")
    asyncio.run(main())
