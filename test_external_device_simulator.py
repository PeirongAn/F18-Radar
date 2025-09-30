#!/usr/bin/env python3
"""
外部设备模拟器
模拟外部设备向8765端口发送控制数据
用于测试TDC外部控制功能
"""

import asyncio
import websockets
import json
import time
import math

async def simulate_external_device():
    """模拟外部设备发送控制数据"""
    uri = "ws://localhost:8765"
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ 已连接到外部设备WebSocket服务器 (8765)")
            print("开始发送模拟控制数据...")
            print("输入 'q' 退出，'test' 运行自动测试，或直接输入 x,y 坐标")
            
            while True:
                try:
                    user_input = input("\n请输入命令 (q/test/x,y): ").strip()
                    
                    if user_input.lower() == 'q':
                        break
                    elif user_input.lower() == 'test':
                        await run_auto_test(websocket)
                        continue
                    elif ',' in user_input:
                        # 手动输入坐标
                        x_str, y_str = user_input.split(',', 1)
                        x = float(x_str.strip())
                        y = float(y_str.strip())
                        await send_control_data(websocket, x, y)
                        continue
                    
                    # 默认发送一个测试消息
                    await send_control_data(websocket, 0.0, 0.0)
                    
                except ValueError:
                    print("❌ 输入格式错误，请使用 x,y 格式")
                except KeyboardInterrupt:
                    break
                    
    except ConnectionRefusedError:
        print("❌ 无法连接到外部设备WebSocket服务器")
        print("请确保雷达服务器已启动并且外部设备服务器正在运行")
    except Exception as e:
        print(f"❌ 连接错误: {e}")

async def send_control_data(websocket, force_x: float, force_y: float):
    """发送控制数据"""
    # 构造外部设备消息格式
    message = {
        "RawInput": 0.0,
        "YawInput": 0.04,
        "PitchInput": 0.0,
        "Fire": False,
        "Throttle": 0.0,
        "PawnControl": False,
        "ForcePress": False,
        "ForceSwitch": [force_x, force_y],  # TDC坐标数据
        "timestamp": time.time()
    }
    
    await websocket.send(json.dumps(message))
    print(f"📤 已发送: ForceSwitch=[{force_x:.3f}, {force_y:.3f}]")

async def run_auto_test(websocket):
    """运行自动测试序列"""
    print("\n🔄 开始自动测试序列...")
    
    # 测试序列：圆形运动
    test_positions = []
    
    # 生成圆形轨迹
    for i in range(16):
        angle = 2 * math.pi * i / 16
        x = 0.8 * math.cos(angle)  # 半径0.8，避免到达边界
        y = 0.8 * math.sin(angle)
        test_positions.append((x, y, f"圆形轨迹点{i+1}"))
    
    # 添加一些特殊位置
    special_positions = [
        (0, 0, "中心位置"),
        (-1, -1, "左下角"),
        (1, -1, "右下角"),
        (1, 1, "右上角"),
        (-1, 1, "左上角"),
        (0, 0, "回到中心")
    ]
    
    test_positions.extend(special_positions)
    
    for x, y, description in test_positions:
        await send_control_data(websocket, x, y)
        print(f"🎯 {description}: ({x:.3f}, {y:.3f})")
        await asyncio.sleep(0.8)  # 稍快一些的测试速度
    
    print("✅ 自动测试完成！")

async def continuous_movement_test(websocket):
    """连续运动测试"""
    print("\n🔄 开始连续运动测试...")
    
    start_time = time.time()
    duration = 10  # 测试10秒
    
    while time.time() - start_time < duration:
        # 生成平滑的圆形运动
        elapsed = time.time() - start_time
        angle = 2 * math.pi * elapsed / 3  # 3秒一圈
        
        x = 0.7 * math.cos(angle)
        y = 0.7 * math.sin(angle)
        
        await send_control_data(websocket, x, y)
        await asyncio.sleep(0.1)  # 100ms更新间隔
    
    # 回到中心
    await send_control_data(websocket, 0, 0)
    print("✅ 连续运动测试完成！")

if __name__ == "__main__":
    print("外部设备模拟器")
    print("=" * 40)
    print("此工具模拟外部设备向雷达系统发送TDC控制数据")
    print("ForceSwitch数组的两个元素将被转换为TDC坐标")
    print()
    
    asyncio.run(simulate_external_device())
