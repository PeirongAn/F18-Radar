#!/usr/bin/env python3
"""
测试ForcePress功能的脚本
模拟外部设备发送ForcePress=true的消息
"""

import asyncio
import websockets
import json
import time

async def test_force_press():
    uri = "ws://localhost:8765"
    
    try:
        async with websockets.connect(uri) as websocket:
            print(f"✅ 已连接到 {uri}")
            
            # 发送一系列测试消息
            test_messages = [
                {
                    "RawInput": 0.0,
                    "YawInput": 0.0,
                    "PitchInput": 0.0,
                    "Fire": False,
                    "Throttle": 0.0,
                    "PawnControl": False,
                    "ForcePress": False,  # 正常状态
                    "ForceSwitch": [0.0, 0.0],
                    "timestamp": int(time.time() * 1000)
                },
                {
                    "RawInput": 0.0,
                    "YawInput": 0.0,
                    "PitchInput": 0.0,
                    "Fire": False,
                    "Throttle": 0.0,
                    "PawnControl": False,
                    "ForcePress": True,  # 激活ForcePress
                    "ForceSwitch": [0.5, -0.3],
                    "timestamp": int(time.time() * 1000)
                },
                {
                    "RawInput": 0.0,
                    "YawInput": 0.0,
                    "PitchInput": 0.0,
                    "Fire": False,
                    "Throttle": 0.0,
                    "PawnControl": False,
                    "ForcePress": False,  # 释放ForcePress
                    "ForceSwitch": [0.5, -0.3],
                    "timestamp": int(time.time() * 1000)
                }
            ]
            
            for i, message in enumerate(test_messages):
                print(f"\n📤 发送测试消息 {i+1}:")
                print(f"   ForcePress: {message['ForcePress']}")
                print(f"   ForceSwitch: {message['ForceSwitch']}")
                
                await websocket.send(json.dumps(message))
                print(f"✅ 消息已发送")
                
                # 等待2秒再发送下一条消息
                await asyncio.sleep(2)
            
            print("\n🎉 所有测试消息已发送完成")
            
            # 保持连接一段时间以观察效果
            print("⏳ 保持连接30秒以观察效果...")
            await asyncio.sleep(30)
            
    except ConnectionRefusedError:
        print(f"❌ 无法连接到 {uri}")
        print("请确保8765端口的WebSocket服务正在运行")
    except Exception as e:
        print(f"❌ 发生错误: {e}")

if __name__ == "__main__":
    print("🚀 开始测试ForcePress功能")
    print("=" * 50)
    asyncio.run(test_force_press())
