#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试ForceSwitch锁定功能
验证ForcePress切换锁定状态的正确性
"""

import json
import time
import websocket

def send_test_message():
    """发送测试消息"""
    try:
        # 连接到WebSocket服务器
        ws = websocket.create_connection("ws://localhost:8765")
        print("✅ 已连接到WebSocket服务器\n")
        
        # 测试1: 正常移动TDC
        print("=" * 60)
        print("测试1: 正常移动TDC（ForcePress=False）")
        print("=" * 60)
        test_data = {
            "RawInput": 0.0,
            "YawInput": 0.0,
            "PitchInput": 0.0,
            "Fire": False,
            "Throttle": 0.0,
            "PawnControl": False,
            "ForcePress": False,
            "ForceSwitch": [0.3, 0.4],
            "PitchPos": 0.0,
            "RollPos": 0.0,
            "RudderPos": 0.0,
            "LeftBrake": 0.0,
            "RightBrake": 0.0,
            "ButtonK1": False,
            "ButtonK2": False,
            "ButtonK3": [0.0, 0.0],
            "ButtonK5": False,
            "ButtonK6": False,
            "ButtonK7": False,
            "ButtonK9": False,
            "TriggerEasy": False,
            "TriggerHard": False,
            "timestamp": int(time.time() * 1000)
        }
        
        ws.send(json.dumps(test_data))
        print(f"📤 发送: ForcePress=False, ForceSwitch=[0.3, 0.4]")
        print("✅ 预期: TDC应该移动到新位置\n")
        time.sleep(1)
        
        # 测试2: 第一次按下ForcePress（锁定）
        print("=" * 60)
        print("测试2: 第一次按下ForcePress（锁定）")
        print("=" * 60)
        test_data["ForcePress"] = True
        test_data["timestamp"] = int(time.time() * 1000)
        ws.send(json.dumps(test_data))
        print(f"📤 发送: ForcePress=True（按下）")
        print("✅ 预期: 应该看到 '🔒 锁定ForceSwitch' 日志\n")
        time.sleep(0.5)
        
        # 测试3: 松开ForcePress
        test_data["ForcePress"] = False
        test_data["timestamp"] = int(time.time() * 1000)
        ws.send(json.dumps(test_data))
        print(f"📤 发送: ForcePress=False（松开）")
        time.sleep(0.5)
        
        # 测试4: ForceSwitch变化（应该被忽略）
        print("=" * 60)
        print("测试3: 锁定状态下ForceSwitch变化（应该被忽略）")
        print("=" * 60)
        test_data["ForceSwitch"] = [0.8, -0.5]
        test_data["timestamp"] = int(time.time() * 1000)
        ws.send(json.dumps(test_data))
        print(f"📤 发送: ForcePress=False, ForceSwitch=[0.8, -0.5]（大幅变化）")
        print("❌ 预期: TDC位置应该保持不变（数据被忽略）\n")
        time.sleep(1)
        
        # 测试5: 再次按下ForcePress（解锁）
        print("=" * 60)
        print("测试4: 第二次按下ForcePress（解锁）")
        print("=" * 60)
        test_data["ForcePress"] = True
        test_data["timestamp"] = int(time.time() * 1000)
        ws.send(json.dumps(test_data))
        print(f"📤 发送: ForcePress=True（再次按下）")
        print("✅ 预期: 应该看到 '🔓 解锁ForceSwitch' 日志\n")
        time.sleep(0.5)
        
        # 测试6: 松开ForcePress
        test_data["ForcePress"] = False
        test_data["timestamp"] = int(time.time() * 1000)
        ws.send(json.dumps(test_data))
        print(f"📤 发送: ForcePress=False（松开）")
        time.sleep(0.5)
        
        # 测试7: ForceSwitch变化（应该生效）
        print("=" * 60)
        print("测试5: 解锁后ForceSwitch变化（应该生效）")
        print("=" * 60)
        test_data["ForceSwitch"] = [-0.6, 0.7]
        test_data["timestamp"] = int(time.time() * 1000)
        ws.send(json.dumps(test_data))
        print(f"📤 发送: ForcePress=False, ForceSwitch=[-0.6, 0.7]")
        print("✅ 预期: TDC应该移动到新位置\n")
        time.sleep(1)
        
        ws.close()
        print("=" * 60)
        print("✅ 测试完成，连接已关闭")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    print("\n🚀 开始测试ForceSwitch锁定功能...\n")
    send_test_message()

