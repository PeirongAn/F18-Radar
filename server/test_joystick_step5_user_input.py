#!/usr/bin/env python3
"""
等待用户操作的脚本：启动WebSocket服务器并等待用户输入命令
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from network.websocket_server import WebSocketServer
from joystick import JoystickEventHandler
import asyncio
import json
import time

async def handle_user_input(server):
    """处理用户输入"""
    print("=== 等待用户操作 ===")
    print("可用命令:")
    print("  start - 启动服务器")
    print("  stop - 停止服务器")
    print("  clients - 查看当前客户端数量")
    print("  broadcast <message> - 向所有客户端广播消息")
    print("  send <client_id> <message> - 向指定客户端发送消息")
    print("  joystick - 查看操纵杆状态")
    print("  help - 显示帮助信息")
    print("  exit - 退出程序")
    print()
    
    while True:
        try:
            # 读取用户输入
            user_input = input("输入命令: ").strip()
            
            if not user_input:
                continue
                
            # 解析命令
            parts = user_input.split(' ', 1)
            command = parts[0].lower()
            
            if command == "start":
                print("启动服务器...")
                # 启动服务器（非阻塞）
                asyncio.create_task(server.start())
                print("服务器已启动")
                
            elif command == "stop":
                print("停止服务器...")
                await server.stop()
                print("服务器已停止")
                
            elif command == "clients":
                client_count = server.get_client_count()
                print(f"当前客户端数量: {client_count}")
                print(f"客户端列表: {list(server.clients.keys())}")
                
            elif command == "broadcast":
                if len(parts) < 2:
                    print("请提供要广播的消息")
                    continue
                message = parts[1]
                try:
                    # 尝试解析为JSON
                    msg_obj = json.loads(message)
                except json.JSONDecodeError:
                    # 如果不是JSON，创建一个简单消息
                    msg_obj = {"type": "user_message", "content": message}
                
                print(f"广播消息: {msg_obj}")
                await server.broadcast_to_all(msg_obj)
                print("消息已广播")
                
            elif command == "send":
                if len(parts) < 2:
                    print("请提供客户端ID和消息")
                    continue
                sub_parts = parts[1].split(' ', 1)
                if len(sub_parts) < 2:
                    print("请提供客户端ID和消息")
                    continue
                client_id = sub_parts[0]
                message = sub_parts[1]
                
                try:
                    # 尝试解析为JSON
                    msg_obj = json.loads(message)
                except json.JSONDecodeError:
                    # 如果不是JSON，创建一个简单消息
                    msg_obj = {"type": "user_message", "content": message}
                
                print(f"向客户端 {client_id} 发送消息: {msg_obj}")
                success = await server.send_to_client(client_id, msg_obj)
                if success:
                    print("消息发送成功")
                else:
                    print("消息发送失败，客户端可能不存在")
                    
            elif command == "joystick":
                if server.joystick_handler:
                    stats = server.joystick_handler.get_stats()
                    print(f"操纵杆处理器状态: {stats}")
                else:
                    print("操纵杆处理器未初始化")
                    
            elif command == "help":
                print("可用命令:")
                print("  start - 启动服务器")
                print("  stop - 停止服务器")
                print("  clients - 查看当前客户端数量")
                print("  broadcast <message> - 向所有客户端广播消息")
                print("  send <client_id> <message> - 向指定客户端发送消息")
                print("  joystick - 查看操纵杆状态")
                print("  help - 显示帮助信息")
                print("  exit - 退出程序")
                
            elif command == "exit":
                print("退出程序...")
                if server.running:
                    await server.stop()
                break
                
            else:
                print(f"未知命令: {command}")
                print("输入 'help' 查看可用命令")
                
        except KeyboardInterrupt:
            print("\n退出程序...")
            if server.running:
                await server.stop()
            break
            
        except Exception as e:
            print(f"错误: {e}")

async def main():
    """主函数"""
    print("=== 等待用户操作脚本 ===")
    print("初始化服务器...")
    
    # 创建服务器实例
    server = WebSocketServer()
    
    # 创建并设置操纵杆处理器
    joystick_handler = JoystickEventHandler()
    server.set_joystick_handler(joystick_handler)
    
    print("服务器初始化完成")
    print()
    
    # 处理用户输入
    await handle_user_input(server)
    
    print("程序已退出")

if __name__ == "__main__":
    asyncio.run(main())
