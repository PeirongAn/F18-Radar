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

from managers import config_manager, db_manager, info, error
from network import websocket_server
from joystick.joystick_event_handler import JoystickEventHandler
from network.http_server import http_server

_initialized = False
_joystick_handler = None
_gaze_svc = None  # 全局 GazeService 实例，供 main() finally 块清理

# 眼动数据存储目录（相对本文件）
_GAZE_DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "gaze")

async def initialize_system():
    """初始化系统组件（延迟调用，首次客户端连接时触发）"""
    global _initialized, _joystick_handler, _gaze_svc
    if _initialized:
        return _joystick_handler
    _initialized = True

    info("=== 雷达系统初始化 ===", "main")
    
    # 1. 初始化数据库
    info("1. 初始化数据库...", "main")
    db_manager.initialize_database()
    info("✅ 数据库初始化完成", "main")
    
    # 2. 初始化操纵杆事件处理器
    info("2. 初始化操纵杆事件处理器...", "main")
    _joystick_handler = JoystickEventHandler()
    
    # 3. 将操纵杆处理器集成到WebSocket服务器和HTTP服务器
    info("3. 集成操纵杆处理器到服务器...", "main")
    websocket_server.set_joystick_handler(_joystick_handler)
    http_server.set_joystick_handler(_joystick_handler)
    
    # 4. 启动操纵杆事件处理器（在异步上下文中启动）
    info("4. 启动操纵杆事件处理器...", "main")
    await asyncio.sleep(0.1)
    _joystick_handler.start()

    # 5. 初始化眼动追踪服务
    info("5. 初始化眼动追踪服务...", "main")
    try:
        from tobii.gaze_service import GazeService
        from core import message_handler as _mh
        _gaze_svc = GazeService(data_dir=_GAZE_DATA_DIR)
        # 注入到消息处理器和 HTTP 服务器（即使没有 Tobii 设备，任务元数据和 DB 仍然可用）
        _mh.set_gaze_service(_gaze_svc)
        http_server.set_gaze_service(_gaze_svc)
        websocket_server.set_gaze_service(_gaze_svc)
        # 尝试连接 Tobii 设备（可选：失败也不影响任务记录功能）
        try:
            _gaze_svc.connect()
            info("✅ 眼动追踪服务已启动（设备已连接）", "main")
        except Exception as e:
            info(f"⚠️ Tobii 设备未连接，眼动追踪仅记录任务元数据: {e}", "main")
    except Exception as e:
        error(f"眼动追踪服务初始化失败（已跳过）: {e}", "main")
        # 清理孤儿实例
        if _gaze_svc is not None:
            try:
                _gaze_svc.shutdown()
            except Exception:
                pass
            _gaze_svc = None

    info("=== 系统初始化完成 ===", "main")
    
    return _joystick_handler

def setup_static_directory(static_dir=None):
    """设置静态文件目录"""
    if static_dir:
        if not os.path.isabs(static_dir):
            static_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), static_dir))
    else:
        static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dist')
    
    info(f"静态文件目录设置为: {static_dir}", "main")
    
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
    
    try:
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
        if _joystick_handler:
            info("正在清理操纵杆资源...", "main")
            try:
                _joystick_handler.stop()
            except Exception as e:
                error(f"清理操纵杆资源时出错: {e}", "main")

        if _gaze_svc is not None:
            info("正在关闭眼动追踪服务...", "main")
            try:
                # 若仍有活动任务，先正常结束它（写 summary.json）
                active_id = _gaze_svc.get_active_task_id()
                if active_id:
                    _gaze_svc.stop_task(task_id=active_id)
                # 关闭后台文件写入线程，确保数据落盘
                _gaze_svc.shutdown()
                info("✅ 眼动追踪服务已关闭", "main")
            except Exception as e:
                error(f"关闭眼动追踪服务时出错: {e}", "main")

if __name__ == "__main__":
    info("雷达系统服务器 v2.0 - 模块化架构", "main")
    info("支持静态文件服务和WebSocket连接", "main")
    info("=" * 50, "main")
    asyncio.run(main()) 