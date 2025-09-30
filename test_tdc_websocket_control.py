#!/usr/bin/env python3
"""
TDC WebSocket坐标控制测试脚本

用法：
1. 确保雷达服务器运行在 localhost:8080
2. 运行此脚本
3. 输入坐标值测试TDC位置控制

坐标范围：x,y 都在 -1.0 到 1.0 之间
- (-1, -1) 表示左下角
- (1, 1) 表示右上角
- (0, 0) 表示中心位置
"""

import asyncio
import websockets
import json
import time

async def test_tdc_control():
    uri = "ws://localhost:8080/ws"
    
    try:
        async with websockets.connect(uri) as websocket:
            print("已连接到雷达服务器")
            print("输入坐标来控制TDC位置 (格式: x,y 其中 x,y 在 -1.0 到 1.0 之间)")
            print("输入 'q' 退出")
            print("输入 'test' 运行自动测试")
            print("\n示例:")
            print("  0,0     -> 中心位置")
            print("  -1,-1   -> 左下角")
            print("  1,1     -> 右上角")
            print("  0.5,0   -> 右侧中间")
            
            while True:
                try:
                    user_input = input("\n请输入坐标 (x,y): ").strip()
                    
                    if user_input.lower() == 'q':
                        break
                    elif user_input.lower() == 'test':
                        await run_auto_test(websocket)
                        continue
                    
                    # 解析输入
                    if ',' in user_input:
                        x_str, y_str = user_input.split(',', 1)
                        x = float(x_str.strip())
                        y = float(y_str.strip())
                        
                        # 验证范围
                        if not (-1 <= x <= 1 and -1 <= y <= 1):
                            print("❌ 错误: 坐标必须在 -1.0 到 1.0 范围内")
                            continue
                        
                        # 发送TDC坐标消息
                        message = {
                            "type": "tdc_coordinate",
                            "x": x,
                            "y": y,
                            "timestamp": time.time()
                        }
                        
                        await websocket.send(json.dumps(message))
                        print(f"✅ 已发送TDC坐标: ({x:.3f}, {y:.3f})")
                        
                    else:
                        print("❌ 错误: 请使用 x,y 格式输入坐标")
                        
                except ValueError:
                    print("❌ 错误: 请输入有效的数字坐标")
                except KeyboardInterrupt:
                    break
                    
    except ConnectionRefusedError:
        print("❌ 无法连接到雷达服务器，请确保服务器运行在 localhost:8080")
    except Exception as e:
        print(f"❌ 连接错误: {e}")

async def run_auto_test(websocket):
    """运行自动测试序列"""
    print("\n🔄 开始自动测试...")
    
    test_positions = [
        (0, 0, "中心"),
        (-1, -1, "左下角"),
        (1, -1, "右下角"),
        (1, 1, "右上角"),
        (-1, 1, "左上角"),
        (0, 0, "回到中心"),
        (0.5, 0, "右侧中间"),
        (-0.5, 0, "左侧中间"),
        (0, 0.5, "上方中间"),
        (0, -0.5, "下方中间"),
        (0, 0, "最终回到中心")
    ]
    
    for x, y, description in test_positions:
        message = {
            "type": "tdc_coordinate",
            "x": x,
            "y": y,
            "timestamp": time.time()
        }
        
        await websocket.send(json.dumps(message))
        print(f"🎯 TDC移动到: {description} ({x:.1f}, {y:.1f})")
        
        # 等待一段时间让用户看到变化
        await asyncio.sleep(1.5)
    
    print("✅ 自动测试完成！")

if __name__ == "__main__":
    print("TDC WebSocket坐标控制测试")
    print("=" * 40)
    asyncio.run(test_tdc_control())
