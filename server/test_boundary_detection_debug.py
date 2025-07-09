#!/usr/bin/env python3
"""
测试边界检测调试日志
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import time
from joystick import JoystickEventHandler

def test_boundary_detection_debug():
    """测试边界检测调试功能"""
    print("=" * 60)
    print("边界检测调试日志测试")
    print("=" * 60)
    
    # 创建操纵杆事件处理器
    joystick_handler = JoystickEventHandler()
    
    try:
        # 启动处理器
        joystick_handler.start()
        print("✓ 操纵杆事件处理器已启动")
        
        # 检查操纵杆连接状态
        is_connected = joystick_handler.joystick_controller.is_connected()
        print(f"操纵杆连接状态: {is_connected}")
        
        if not is_connected:
            print("尝试连接操纵杆...")
            success = joystick_handler.joystick_controller.connect_device()
            if success:
                print("✓ 操纵杆连接成功")
            else:
                print("✗ 操纵杆连接失败")
                print("请检查操纵杆是否正确连接")
                return
        
        # 获取设备状态
        status = joystick_handler.joystick_controller.get_device_status()
        print(f"设备状态: {status}")
        
        # 开始边界检测
        print("\n开始边界检测...")
        success = joystick_handler.joystick_controller.start_boundary_detection()
        
        if success:
            print("✓ 边界检测已启动")
            print("请移动操纵杆到各个极限位置...")
            print("观察调试日志输出...")
            print("按 Ctrl+C 停止测试")
            
            # 等待用户操作
            try:
                while True:
                    time.sleep(1)
                    
                    # 检查是否还在边界检测模式
                    if hasattr(joystick_handler.joystick_controller, 'joystick'):
                        if not joystick_handler.joystick_controller.joystick.boundary_detection_mode:
                            print("边界检测已停止")
                            break
                    
            except KeyboardInterrupt:
                print("\n用户中断测试")
                
                # 停止边界检测
                print("停止边界检测...")
                success = joystick_handler.joystick_controller.stop_boundary_detection()
                if success:
                    print("✓ 边界检测已停止")
                else:
                    print("✗ 停止边界检测失败")
        else:
            print("✗ 边界检测启动失败")
        
    except Exception as e:
        print(f"测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 清理资源
        try:
            joystick_handler.stop()
            print("✓ 操纵杆事件处理器已停止")
        except Exception as e:
            print(f"停止处理器时发生错误: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    test_boundary_detection_debug()