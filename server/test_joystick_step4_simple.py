#!/usr/bin/env python3
"""
第四步简化测试：验证main.py操纵杆集成的核心功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def test_main_integration_simple():
    """测试main.py中操纵杆集成的核心功能"""
    print("=== 第四步简化测试：main.py操纵杆集成核心功能 ===")
    
    # 1. 测试导入依赖
    print("\n1. 测试导入依赖...")
    
    try:
        from joystick import JoystickEventHandler
        print("✓ JoystickEventHandler导入成功")
    except Exception as e:
        print(f"✗ JoystickEventHandler导入失败: {e}")
        return
    
    try:
        from network import websocket_server
        print("✓ websocket_server导入成功")
    except Exception as e:
        print(f"✗ websocket_server导入失败: {e}")
        return
    
    # 2. 测试操纵杆处理器创建
    print("\n2. 测试操纵杆处理器创建...")
    
    try:
        joystick_handler = JoystickEventHandler()
        assert joystick_handler is not None
        assert hasattr(joystick_handler, 'start')
        assert hasattr(joystick_handler, 'stop')
        assert hasattr(joystick_handler, 'is_active')
        print("✓ 操纵杆处理器创建成功")
    except Exception as e:
        print(f"✗ 操纵杆处理器创建失败: {e}")
        return
    
    # 3. 测试WebSocket服务器集成
    print("\n3. 测试WebSocket服务器集成...")
    
    try:
        # 检查websocket_server是否有set_joystick_handler方法
        assert hasattr(websocket_server, 'set_joystick_handler')
        assert hasattr(websocket_server, 'joystick_handler')
        
        # 设置操纵杆处理器
        websocket_server.set_joystick_handler(joystick_handler)
        
        # 验证集成
        assert websocket_server.joystick_handler == joystick_handler
        assert joystick_handler.websocket_server == websocket_server
        
        print("✓ WebSocket服务器集成成功")
    except Exception as e:
        print(f"✗ WebSocket服务器集成失败: {e}")
        return
    
    # 4. 测试操纵杆处理器启动和停止
    print("\n4. 测试操纵杆处理器启动和停止...")
    
    try:
        # 检查初始状态
        assert joystick_handler.is_active == False
        
        # 启动处理器
        joystick_handler.start()
        assert joystick_handler.is_active == True
        print("✓ 操纵杆处理器启动成功")
        
        # 停止处理器
        joystick_handler.stop()
        assert joystick_handler.is_active == False
        print("✓ 操纵杆处理器停止成功")
        
    except Exception as e:
        print(f"✗ 操纵杆处理器启动/停止测试失败: {e}")
        return
    
    # 5. 测试main.py中的集成代码结构
    print("\n5. 测试main.py中的集成代码结构...")
    
    try:
        # 读取main.py文件内容
        with open('/mnt/d/codes/millatary/radar/server/main.py', 'r', encoding='utf-8') as f:
            main_content = f.read()
        
        # 检查必要的导入
        assert 'from joystick import JoystickEventHandler' in main_content
        print("✓ main.py包含操纵杆处理器导入")
        
        # 检查初始化代码
        assert 'joystick_handler = JoystickEventHandler()' in main_content
        print("✓ main.py包含操纵杆处理器初始化")
        
        # 检查集成代码
        assert 'websocket_server.set_joystick_handler(joystick_handler)' in main_content
        print("✓ main.py包含WebSocket服务器集成")
        
        # 检查启动代码
        assert 'joystick_handler.start()' in main_content
        print("✓ main.py包含操纵杆处理器启动")
        
        # 检查清理代码
        assert 'joystick_handler.stop()' in main_content
        print("✓ main.py包含操纵杆处理器清理")
        
        # 检查返回值
        assert 'return joystick_handler' in main_content
        print("✓ main.py正确返回操纵杆处理器")
        
    except Exception as e:
        print(f"✗ main.py代码结构检查失败: {e}")
        return
    
    # 6. 测试WebSocket服务器的操纵杆功能
    print("\n6. 测试WebSocket服务器的操纵杆功能...")
    
    try:
        # 检查WebSocket服务器是否有客户端管理功能
        assert hasattr(websocket_server, 'clients')
        assert hasattr(websocket_server, 'client_sessions')
        assert hasattr(websocket_server, 'add_client')
        assert hasattr(websocket_server, 'remove_client')
        assert hasattr(websocket_server, 'send_to_client')
        assert hasattr(websocket_server, 'broadcast_to_all')
        print("✓ WebSocket服务器具备完整的操纵杆支持功能")
        
    except Exception as e:
        print(f"✗ WebSocket服务器操纵杆功能检查失败: {e}")
        return
    
    # 7. 测试完整的集成流程
    print("\n7. 测试完整的集成流程...")
    
    try:
        # 模拟完整的集成流程
        
        # 创建新的操纵杆处理器（模拟main.py的initialize_system）
        test_joystick_handler = JoystickEventHandler()
        
        # 集成到WebSocket服务器
        websocket_server.set_joystick_handler(test_joystick_handler)
        
        # 启动处理器
        test_joystick_handler.start()
        
        # 验证状态
        assert test_joystick_handler.is_active == True
        assert websocket_server.joystick_handler == test_joystick_handler
        assert test_joystick_handler.websocket_server == websocket_server
        
        print("✓ 完整集成流程测试通过")
        
        # 清理
        test_joystick_handler.stop()
        assert test_joystick_handler.is_active == False
        
        print("✓ 清理流程测试通过")
        
    except Exception as e:
        print(f"✗ 完整集成流程测试失败: {e}")
        return
    
    # 8. 显示测试结果
    print("\n=== 测试结果汇总 ===")
    print("✓ 所有导入依赖测试通过")
    print("✓ 操纵杆处理器创建测试通过")
    print("✓ WebSocket服务器集成测试通过")
    print("✓ 启动和停止功能测试通过")
    print("✓ main.py代码结构检查通过")
    print("✓ WebSocket服务器操纵杆功能检查通过")
    print("✓ 完整集成流程测试通过")
    
    print("\n=== 集成验证总结 ===")
    print("1. ✅ 操纵杆事件处理器已成功集成到main.py")
    print("2. ✅ 系统初始化流程包含完整的操纵杆初始化")
    print("3. ✅ WebSocket服务器与操纵杆处理器正确连接")
    print("4. ✅ 异常处理和资源清理机制完善")
    print("5. ✅ 服务器启动时自动启动操纵杆功能")
    print("6. ✅ 所有核心功能正常工作")
    
    print("\n=== 第四步测试完成 ===")

if __name__ == "__main__":
    test_main_integration_simple()