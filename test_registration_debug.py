#!/usr/bin/env python3
"""
调试雷达客户端注册问题
"""

import asyncio
import websockets
import json
import time

async def test_radar_client_registration():
    """测试雷达客户端是否正确注册到外部设备服务器"""
    
    print("🔍 测试雷达客户端注册")
    print("=" * 40)
    
    try:
        # 连接到雷达服务器的WebSocket
        uri = "ws://localhost:8080/ws"
        print(f"⏳ 连接到雷达服务器: {uri}")
        
        async with websockets.connect(uri) as websocket:
            print("✅ 成功连接到雷达服务器")
            
            # 等待一段时间让注册完成
            await asyncio.sleep(2)
            
            # 发送一个简单的消息来保持连接
            test_message = {
                "type": "test",
                "message": "保持连接测试"
            }
            
            await websocket.send(json.dumps(test_message))
            print("📤 已发送测试消息")
            
            # 监听消息
            print("👂 开始监听消息...")
            try:
                while True:
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    print(f"📨 收到消息: {message}")
                    
                    # 解析消息
                    try:
                        data = json.loads(message)
                        if data.get('type') == 'tdc_coordinate':
                            print(f"🎯 收到TDC坐标: x={data.get('x')}, y={data.get('y')}")
                    except json.JSONDecodeError:
                        pass
                        
            except asyncio.TimeoutError:
                print("⏰ 5秒内没有收到消息")
                
    except ConnectionRefusedError:
        print("❌ 无法连接到雷达服务器")
        print("请确保雷达服务器正在运行: cd server && python main.py")
    except Exception as e:
        print(f"❌ 连接错误: {e}")

async def check_external_device_connection():
    """检查外部设备服务连接状态"""
    print("\n🔍 检查外部设备服务连接")
    print("=" * 40)
    
    try:
        uri = "ws://localhost:8765"
        print(f"⏳ 尝试连接外部设备服务: {uri}")
        
        async with websockets.connect(uri, timeout=3) as websocket:
            print("✅ 外部设备服务正在运行")
            
            # 发送测试数据
            test_data = {
                "RawInput": 0.0,
                "YawInput": 0.0,
                "PitchInput": 0.0,
                "Fire": False,
                "Throttle": 0.0,
                "PawnControl": False,
                "ForcePress": False,
                "ForceSwitch": [0.5, -0.3],
                "timestamp": time.time()
            }
            
            await websocket.send(json.dumps(test_data))
            print("📤 已发送测试ForceSwitch数据")
            
    except ConnectionRefusedError:
        print("❌ 外部设备服务未运行")
        print("请启动外部设备模拟器: python test_8765_server_simulator.py")
    except asyncio.TimeoutError:
        print("❌ 连接外部设备服务超时")
    except Exception as e:
        print(f"❌ 连接错误: {e}")

async def main():
    print("雷达客户端注册调试工具")
    print("用于诊断TDC消息转发问题")
    
    # 检查外部设备服务
    await check_external_device_connection()
    
    # 测试雷达客户端注册
    await test_radar_client_registration()

if __name__ == "__main__":
    asyncio.run(main())
