#!/usr/bin/env python3
"""
第一步测试用例：测试 JoystickWebSocketController 基本功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from joystick import JoystickWebSocketController
import time
import json

def test_joystick_controller():
    """测试操纵杆控制器基本功能"""
    print("=== 第一步测试：JoystickWebSocketController 基本功能 ===")
    
    # 数据回调测试
    received_data = []
    received_status = []
    
    def data_callback(data):
        """数据回调函数"""
        print(f"接收到数据: {json.dumps(data, indent=2)}")
        received_data.append(data)
    
    def status_callback(event, data):
        """状态回调函数"""
        print(f"状态变化 [{event}]: {json.dumps(data, indent=2)}")
        received_status.append((event, data))
    
    # 1. 测试控制器初始化
    print("\n1. 测试控制器初始化...")
    controller = JoystickWebSocketController()
    controller.set_data_callback(data_callback)
    controller.set_status_callback(status_callback)
    
    # 2. 测试设备状态查询
    print("\n2. 测试设备状态查询...")
    status = controller.get_device_status()
    print(f"初始状态: {json.dumps(status, indent=2)}")
    assert status['device_status'] == 'disconnected'
    assert status['connected'] == False
    
    # 3. 测试设备连接
    print("\n3. 测试设备连接...")
    connection_result = controller.connect_device()
    print(f"连接结果: {connection_result}")
    
    if connection_result:
        print("✓ 设备连接成功")
        
        # 4. 测试连接后的状态
        print("\n4. 测试连接后的状态...")
        status = controller.get_device_status()
        print(f"连接后状态: {json.dumps(status, indent=2)}")
        assert status['device_status'] == 'connected'
        assert status['connected'] == True
        
        # 5. 测试数据接收（等待5秒）
        print("\n5. 测试数据接收（等待5秒）...")
        start_time = time.time()
        while time.time() - start_time < 5:
            latest_data = controller.get_latest_data()
            if latest_data:
                print(f"最新数据: {json.dumps(latest_data, indent=2)}")
                break
            time.sleep(0.1)
        
        # 6. 测试中心重置
        print("\n6. 测试中心重置...")
        reset_result = controller.reset_center()
        print(f"中心重置结果: {reset_result}")
        
        # 7. 测试边界检测
        print("\n7. 测试边界检测...")
        boundary_start_result = controller.start_boundary_detection()
        print(f"边界检测启动结果: {boundary_start_result}")
        
        if boundary_start_result:
            print("请移动操纵杆到各个极限位置，5秒后自动停止...")
            time.sleep(5)
            
            boundary_stop_result = controller.stop_boundary_detection()
            print(f"边界检测停止结果: {boundary_stop_result}")
        
        # 8. 测试最终状态
        print("\n8. 测试最终状态...")
        final_status = controller.get_device_status()
        print(f"最终状态: {json.dumps(final_status, indent=2)}")
        
        # 9. 测试断开连接
        print("\n9. 测试断开连接...")
        controller.disconnect_device()
        
    else:
        print("✗ 设备连接失败，跳过实时数据测试")
        print("这可能是因为：")
        print("1. 操纵杆设备未连接")
        print("2. 设备驱动未正确安装")
        print("3. 设备ID不匹配")
    
    # 10. 测试清理
    print("\n10. 测试清理...")
    controller.cleanup()
    
    # 11. 显示测试结果
    print("\n=== 测试结果汇总 ===")
    print(f"接收到的数据消息数量: {len(received_data)}")
    print(f"接收到的状态消息数量: {len(received_status)}")
    
    if received_data:
        print("最后一条数据消息:")
        print(json.dumps(received_data[-1], indent=2))
    
    if received_status:
        print("状态消息事件列表:")
        for event, data in received_status:
            print(f"  - {event}: {data.get('data', {}).get('message', 'N/A')}")
    
    print("\n=== 第一步测试完成 ===")

if __name__ == "__main__":
    test_joystick_controller()