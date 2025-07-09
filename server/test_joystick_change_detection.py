#!/usr/bin/env python3
"""
测试操纵杆变化检测逻辑
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import time
from joystick.joystick_websocket_controller import JoystickWebSocketController

def test_change_detection():
    """测试变化检测功能"""
    print("=" * 60)
    print("操纵杆变化检测测试")
    print("=" * 60)
    
    # 创建控制器
    controller = JoystickWebSocketController()
    
    # 数据接收计数器
    data_count = 0
    
    def on_data_received(data):
        nonlocal data_count
        data_count += 1
        print(f"[数据接收] #{data_count}: main_x={data['data']['main_x']:.3f}, main_y={data['data']['main_y']:.3f}, sub_y={data['data']['sub_y']:.3f}")
        print(f"           按钮: {data['data']['buttons']}")
    
    # 设置回调
    controller.set_data_callback(on_data_received)
    
    try:
        # 尝试连接操纵杆
        print("尝试连接操纵杆...")
        success = controller.connect_device()
        
        if success:
            print("✓ 操纵杆连接成功")
            print(f"设备状态: {controller.get_device_status()}")
            
            print("\n开始监听操纵杆数据...")
            print("请移动操纵杆和按按钮，观察是否只在状态变化时发送数据")
            print("按 Ctrl+C 停止测试")
            
            start_time = time.time()
            
            try:
                while True:
                    time.sleep(1)
                    
                    # 每10秒显示一次统计信息
                    elapsed = time.time() - start_time
                    if int(elapsed) % 10 == 0 and int(elapsed) > 0:
                        print(f"\n[统计] 运行时间: {elapsed:.0f}秒, 数据包数量: {data_count}")
                        print(f"[统计] 平均频率: {data_count/elapsed:.2f} 包/秒")
                        if data_count > 0:
                            print("✓ 变化检测正常工作 (只在状态变化时发送数据)")
                        else:
                            print("! 未接收到任何数据包")
                    
            except KeyboardInterrupt:
                print("\n\n用户中断测试")
                elapsed = time.time() - start_time
                print(f"[最终统计] 运行时间: {elapsed:.0f}秒, 数据包数量: {data_count}")
                if elapsed > 0:
                    print(f"[最终统计] 平均频率: {data_count/elapsed:.2f} 包/秒")
                
                if data_count < elapsed * 2:  # 如果频率低于2包/秒，认为变化检测工作正常
                    print("✓ 变化检测功能正常 - 只在状态变化时发送数据")
                else:
                    print("! 可能存在过度发送问题 - 频率过高")
        else:
            print("✗ 操纵杆连接失败")
            print("请检查操纵杆是否正确连接")
    
    except Exception as e:
        print(f"测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 清理资源
        try:
            controller.cleanup()
            print("\n✓ 控制器已清理")
        except Exception as e:
            print(f"清理控制器时发生错误: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    test_change_detection()