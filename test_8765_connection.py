#!/usr/bin/env python3
"""
8765端口连接测试工具
快速验证外部设备WebSocket服务器是否正常工作
"""

import asyncio
import websockets
import json
import time

async def test_8765_connection():
    """测试8765端口连接和消息发送"""
    uri = "ws://localhost:8765"
    
    print("🔍 测试8765端口WebSocket服务器")
    print("=" * 40)
    
    try:
        print("⏳ 尝试连接到 ws://localhost:8765...")
        
        async with websockets.connect(uri, timeout=5) as websocket:
            print("✅ 连接成功! 8765端口服务器正常运行")
            print("📡 开始发送测试消息...")
            
            # 发送测试消息1
            test_msg_1 = {
                "RawInput": 0.0,
                "YawInput": 0.0,
                "PitchInput": 0.0,
                "Fire": False,
                "Throttle": 0.0,
                "PawnControl": False,
                "ForcePress": False,
                "ForceSwitch": [0.0, 0.0],
                "timestamp": time.time()
            }
            
            print(f"\n📤 发送测试消息1: 中心位置 (0.0, 0.0)")
            await websocket.send(json.dumps(test_msg_1))
            print("✅ 消息1发送成功")
            
            await asyncio.sleep(1)
            
            # 发送测试消息2
            test_msg_2 = {
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
            
            print(f"\n📤 发送测试消息2: 偏移位置 (0.5, -0.3)")
            await websocket.send(json.dumps(test_msg_2))
            print("✅ 消息2发送成功")
            
            await asyncio.sleep(1)
            
            # 发送测试消息3
            test_msg_3 = {
                "RawInput": 0.0,
                "YawInput": 0.0,
                "PitchInput": 0.0,
                "Fire": False,
                "Throttle": 0.0,
                "PawnControl": False,
                "ForcePress": False,
                "ForceSwitch": [-1.0, 1.0],
                "timestamp": time.time()
            }
            
            print(f"\n📤 发送测试消息3: 边界位置 (-1.0, 1.0)")
            await websocket.send(json.dumps(test_msg_3))
            print("✅ 消息3发送成功")
            
            print(f"\n🎉 测试完成! 所有消息已发送")
            print(f"📋 请检查服务器控制台输出，确认:")
            print(f"   ✓ 显示了连接成功信息")
            print(f"   ✓ 显示了3条消息的详细内容")
            print(f"   ✓ 显示了ForceSwitch数据提取")
            print(f"   ✓ 显示了TDC坐标转换")
            print(f"   ✓ 显示了广播给雷达客户端的信息")
            
    except ConnectionRefusedError:
        print("❌ 连接被拒绝!")
        print("   可能的原因:")
        print("   1. 雷达服务器未启动")
        print("   2. 8765端口服务器未启动")
        print("   3. 端口被其他程序占用")
        print("\n💡 解决方案:")
        print("   启动雷达服务器: cd server && python main.py")
        
    except asyncio.TimeoutError:
        print("❌ 连接超时!")
        print("   8765端口可能没有WebSocket服务器在监听")
        
    except Exception as e:
        print(f"❌ 连接错误: {e}")

async def check_port_status():
    """检查端口状态"""
    import socket
    
    print("\n🔍 检查端口状态...")
    
    # 检查8765端口
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    
    try:
        result = sock.connect_ex(('localhost', 8765))
        if result == 0:
            print("✅ 8765端口有服务在监听")
        else:
            print("❌ 8765端口没有服务监听")
    except Exception as e:
        print(f"❌ 端口检查失败: {e}")
    finally:
        sock.close()
    
    # 检查8080端口（雷达主服务器）
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    
    try:
        result = sock.connect_ex(('localhost', 8080))
        if result == 0:
            print("✅ 8080端口有服务在监听（雷达主服务器）")
        else:
            print("❌ 8080端口没有服务监听（雷达主服务器可能未启动）")
    except Exception as e:
        print(f"❌ 端口检查失败: {e}")
    finally:
        sock.close()

if __name__ == "__main__":
    print("8765端口WebSocket服务器测试工具")
    print("用于验证外部设备服务器是否正常工作")
    
    # 先检查端口状态
    asyncio.run(check_port_status())
    
    # 然后测试WebSocket连接
    asyncio.run(test_8765_connection())
