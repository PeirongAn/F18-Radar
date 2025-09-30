#!/usr/bin/env python3
"""
测试外部设备消息打印功能
发送几个测试消息来验证服务器是否正确打印收到的数据包
"""

import asyncio
import websockets
import json
import time

async def test_message_printing():
    """测试消息打印功能"""
    uri = "ws://localhost:8765"
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ 已连接到外部设备WebSocket服务器")
            print("发送测试消息来验证服务器打印功能...\n")
            
            # 测试消息1：标准格式
            test_message_1 = {
                "RawInput": 0.0,
                "YawInput": 0.04,
                "PitchInput": 0.0,
                "Fire": False,
                "Throttle": 0.0,
                "PawnControl": False,
                "ForcePress": False,
                "ForceSwitch": [0.5, -0.3],
                "timestamp": time.time()
            }
            
            print("📤 发送测试消息1（标准格式）...")
            await websocket.send(json.dumps(test_message_1))
            await asyncio.sleep(1)
            
            # 测试消息2：边界值
            test_message_2 = {
                "RawInput": 1.0,
                "YawInput": -0.5,
                "PitchInput": 0.8,
                "Fire": True,
                "Throttle": 0.75,
                "PawnControl": True,
                "ForcePress": True,
                "ForceSwitch": [-1.0, 1.0],  # 边界值
                "timestamp": time.time()
            }
            
            print("📤 发送测试消息2（边界值）...")
            await websocket.send(json.dumps(test_message_2))
            await asyncio.sleep(1)
            
            # 测试消息3：超出范围的值
            test_message_3 = {
                "RawInput": 0.0,
                "YawInput": 0.0,
                "PitchInput": 0.0,
                "Fire": False,
                "Throttle": 0.0,
                "PawnControl": False,
                "ForcePress": False,
                "ForceSwitch": [2.5, -1.8],  # 超出范围的值
                "timestamp": time.time()
            }
            
            print("📤 发送测试消息3（超出范围值）...")
            await websocket.send(json.dumps(test_message_3))
            await asyncio.sleep(1)
            
            # 测试消息4：缺少ForceSwitch
            test_message_4 = {
                "RawInput": 0.0,
                "YawInput": 0.0,
                "PitchInput": 0.0,
                "Fire": False,
                "Throttle": 0.0,
                "PawnControl": False,
                "ForcePress": False,
                # 故意不包含ForceSwitch
                "timestamp": time.time()
            }
            
            print("📤 发送测试消息4（缺少ForceSwitch）...")
            await websocket.send(json.dumps(test_message_4))
            await asyncio.sleep(1)
            
            # 测试消息5：无效JSON（这个会在发送前就失败）
            print("📤 发送测试消息5（中文字符）...")
            test_message_5 = {
                "RawInput": 0.0,
                "YawInput": 0.0,
                "PitchInput": 0.0,
                "Fire": False,
                "Throttle": 0.0,
                "PawnControl": False,
                "ForcePress": False,
                "ForceSwitch": [0.0, 0.0],
                "timestamp": time.time(),
                "note": "测试中文字符"
            }
            await websocket.send(json.dumps(test_message_5, ensure_ascii=False))
            await asyncio.sleep(1)
            
            print("\n✅ 所有测试消息已发送完毕")
            print("请检查服务器控制台输出，确认消息打印功能正常工作")
            
    except ConnectionRefusedError:
        print("❌ 无法连接到外部设备WebSocket服务器")
        print("请确保雷达服务器已启动并且外部设备服务器正在运行")
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")

if __name__ == "__main__":
    print("外部设备消息打印测试")
    print("=" * 40)
    asyncio.run(test_message_printing())
