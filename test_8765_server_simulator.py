#!/usr/bin/env python3
"""
8765端口WebSocket服务器模拟器
模拟外部设备服务，用于测试雷达系统的客户端连接功能
"""

import asyncio
import websockets
import json
import time
import math

class ExternalDeviceSimulator:
    """外部设备服务模拟器"""
    
    def __init__(self, port=8765):
        self.port = port
        self.connected_clients = set()
        self.running = False
        
    async def handle_client(self, websocket, path):
        """处理客户端连接"""
        client_address = websocket.remote_address
        print(f"✅ 雷达客户端已连接: {client_address}")
        
        self.connected_clients.add(websocket)
        
        try:
            # 发送欢迎消息
            welcome_msg = {
                "RawInput": 0.0,
                "YawInput": 0.0,
                "PitchInput": 0.0,
                "Fire": False,
                "Throttle": 0.0,
                "PawnControl": False,
                "ForcePress": False,
                "ForceSwitch": [0.0, 0.0],
                "timestamp": time.time(),
                "message": "欢迎连接到外部设备服务"
            }
            await websocket.send(json.dumps(welcome_msg))
            print(f"📤 已发送欢迎消息给 {client_address}")
            
            # 保持连接，等待客户端断开
            await websocket.wait_closed()
            
        except websockets.exceptions.ConnectionClosed:
            print(f"🔌 客户端断开连接: {client_address}")
        except Exception as e:
            print(f"❌ 处理客户端时出错: {e}")
        finally:
            self.connected_clients.discard(websocket)
            print(f"🧹 客户端连接已清理: {client_address}")
    
    async def send_test_data(self):
        """定期发送测试数据"""
        message_count = 0
        last_x, last_y = 0.0, 0.0
        
        print("📡 开始发送测试数据 (包含重复数据来测试变化检测)")
        
        while self.running:
            if self.connected_clients:
                message_count += 1
                
                # 生成测试数据：有时变化，有时重复
                if message_count % 5 == 0:
                    # 每5次发送一次新的圆形运动数据
                    angle = (message_count * 0.2) % (2 * math.pi)
                    x = 0.8 * math.cos(angle)
                    y = 0.8 * math.sin(angle)
                    last_x, last_y = x, y
                    data_type = "新数据"
                else:
                    # 其他时候发送重复数据
                    x, y = last_x, last_y
                    data_type = "重复数据"
                
                test_data = {
                    "RawInput": 0.0,
                    "YawInput": 0.04,
                    "PitchInput": 0.0,
                    "Fire": False,
                    "Throttle": 0.0,
                    "PawnControl": False,
                    "ForcePress": False,
                    "ForceSwitch": [x, y],
                    "timestamp": time.time()
                }
                
                # 广播给所有连接的客户端
                disconnected = set()
                for client in self.connected_clients:
                    try:
                        await client.send(json.dumps(test_data))
                    except websockets.exceptions.ConnectionClosed:
                        disconnected.add(client)
                    except Exception as e:
                        print(f"❌ 发送数据失败: {e}")
                        disconnected.add(client)
                
                # 清理断开的连接
                for client in disconnected:
                    self.connected_clients.discard(client)
                
                if len(self.connected_clients) > 0:
                    print(f"📡 消息#{message_count}: {data_type} ForceSwitch=[{x:.3f}, {y:.3f}] -> {len(self.connected_clients)}个客户端")
            
            await asyncio.sleep(0.8)  # 每0.8秒发送一次数据
    
    async def start_server(self):
        """启动模拟服务器"""
        print(f"🚀 启动外部设备服务模拟器")
        print(f"📡 监听端口: {self.port}")
        print(f"🌐 服务地址: ws://localhost:{self.port}")
        print("-" * 50)
        
        self.running = True
        
        # 启动WebSocket服务器
        server = await websockets.serve(
            self.handle_client,
            "localhost",
            self.port
        )
        
        print(f"✅ 外部设备服务模拟器启动成功!")
        print(f"⏳ 等待雷达客户端连接...")
        print(f"💡 提示: 启动雷达服务器来测试连接")
        
        # 启动数据发送任务
        data_task = asyncio.create_task(self.send_test_data())
        
        try:
            # 等待服务器关闭
            await server.wait_closed()
        except KeyboardInterrupt:
            print(f"\n🛑 收到中断信号，正在关闭服务器...")
        finally:
            self.running = False
            data_task.cancel()
            server.close()
            await server.wait_closed()
            print(f"✅ 外部设备服务模拟器已关闭")

async def interactive_mode():
    """交互模式"""
    simulator = ExternalDeviceSimulator()
    
    print("外部设备服务模拟器 - 交互模式")
    print("=" * 40)
    print("选择模式:")
    print("1. 自动模式 - 自动发送圆形运动数据")
    print("2. 手动模式 - 手动输入ForceSwitch数据")
    
    try:
        choice = input("请选择模式 (1/2): ").strip()
        
        if choice == "1":
            print("🔄 启动自动模式...")
            await simulator.start_server()
        elif choice == "2":
            print("✋ 手动模式暂未实现，使用自动模式...")
            await simulator.start_server()
        else:
            print("❌ 无效选择，使用自动模式...")
            await simulator.start_server()
            
    except KeyboardInterrupt:
        print("\n👋 再见!")

if __name__ == "__main__":
    print("8765端口外部设备服务模拟器")
    print("用于测试雷达系统的外部设备客户端连接功能")
    
    asyncio.run(interactive_mode())
