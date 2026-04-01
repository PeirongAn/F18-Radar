#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试ForceSwitch + ForcePress + ButtonK3 TDC控制功能
模拟发送包含ForceSwitch、ForcePress和ButtonK3数据的消息到8765端口
"""

import json
import time
import websocket

def send_test_message():
    """发送测试消息"""
    try:
        # 连接到WebSocket服务器
        ws = websocket.create_connection("ws://localhost:8765")
        print("✅ 已连接到WebSocket服务器")
        
        # 测试1: 移动TDC（ForcePress=False）
        print("\n--- 测试1: 移动TDC ---")
        test_data = {
            "RawInput": 0.0,
            "YawInput": 0.0,
            "PitchInput": 0.0,
            "Fire": False,
            "Throttle": 0.0,
            "PawnControl": False,
            "ForcePress": False,  # 未按下
            "ForceSwitch": [0.5, -0.3],  # TDC坐标
            "PitchPos": 0.0,
            "RollPos": 0.0,
            "RudderPos": 0.0,
            "LeftBrake": 0.0,
            "RightBrake": 0.0,
            "ButtonK1": False,
            "ButtonK2": False,
            "ButtonK3": False,  # ButtonK3是布尔值
            "ButtonK5": False,
            "ButtonK6": False,
            "ButtonK7": False,
            "ButtonK9": False,
            "TriggerEasy": False,
            "TriggerHard": False,
            "timestamp": int(time.time() * 1000)
        }
        
        ws.send(json.dumps(test_data))
        print(f"📤 ForcePress=False, ForceSwitch=[{test_data['ForceSwitch'][0]}, {test_data['ForceSwitch'][1]}]")
        print("   → TDC应该移动到新位置")
        time.sleep(1)
        
        # 测试2: 按下ForcePress（锁定位置）
        print("\n--- 测试2: 按下ForcePress（锁定） ---")
        test_data["ForcePress"] = True  # 按下
        test_data["ForceSwitch"] = [0.5, -0.3]  # 保持位置
        test_data["timestamp"] = int(time.time() * 1000)
        ws.send(json.dumps(test_data))
        print(f"📤 ForcePress=True（按下），ForceSwitch=[{test_data['ForceSwitch'][0]}, {test_data['ForceSwitch'][1]}]")
        print("   → 应该触发ForcePress回调")
        time.sleep(0.5)
        
        # 测试3: ForcePress按下时，ForceSwitch抖动（应该被忽略）
        print("\n--- 测试3: ForcePress按下时ForceSwitch抖动 ---")
        test_data["ForcePress"] = True  # 保持按下
        test_data["ForceSwitch"] = [0.51, -0.29]  # 微小抖动
        test_data["timestamp"] = int(time.time() * 1000)
        ws.send(json.dumps(test_data))
        print(f"📤 ForcePress=True（保持），ForceSwitch=[{test_data['ForceSwitch'][0]}, {test_data['ForceSwitch'][1]}]（抖动）")
        print("   → TDC位置应该保持不变（抖动被忽略）")
        time.sleep(0.5)
        
        # 测试4: 按下ButtonK3（目标锁定）
        print("\n--- 测试4: 按下ButtonK3（目标锁定） ---")
        test_data["ButtonK3"] = True  # 按下ButtonK3
        test_data["timestamp"] = int(time.time() * 1000)
        ws.send(json.dumps(test_data))
        print(f"📤 ButtonK3=True（按下）")
        print("   → 应该触发目标锁定（模拟Enter键）")
        time.sleep(0.5)
        
        # 测试5: 松开ButtonK3
        test_data["ButtonK3"] = False
        test_data["timestamp"] = int(time.time() * 1000)
        ws.send(json.dumps(test_data))
        print(f"📤 ButtonK3=False（松开）")
        time.sleep(0.5)
        
        # 测试6: 松开ForcePress（解锁）
        print("\n--- 测试5: 再次按下ForcePress（解锁） ---")
        test_data["ForcePress"] = True  # 再次按下
        test_data["timestamp"] = int(time.time() * 1000)
        ws.send(json.dumps(test_data))
        print(f"📤 ForcePress=True（再次按下）")
        print("   → 应该解锁ForceSwitch")
        time.sleep(0.5)
        
        # 测试7: 松开ForcePress
        test_data["ForcePress"] = False
        test_data["timestamp"] = int(time.time() * 1000)
        ws.send(json.dumps(test_data))
        time.sleep(0.5)
        
        # 测试8: 移动TDC（解锁后）
        print("\n--- 测试6: 解锁后移动TDC ---")
        test_data["ForceSwitch"] = [-0.2, 0.8]  # 新位置
        test_data["timestamp"] = int(time.time() * 1000)
        ws.send(json.dumps(test_data))
        print(f"📤 ForcePress=False, ForceSwitch=[{test_data['ForceSwitch'][0]}, {test_data['ForceSwitch'][1]}]")
        print("   → TDC应该移动到新位置")
        time.sleep(1)
        
        ws.close()
        print("\n✅ 测试完成，连接已关闭")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    print("🚀 开始测试ForceSwitch + ForcePress TDC控制功能...")
    send_test_message()
