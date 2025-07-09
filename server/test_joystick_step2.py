#!/usr/bin/env python3
"""
第二步测试用例：测试 JoystickEventHandler 桥接功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from joystick import JoystickEventHandler
import asyncio
import json
import time
from unittest.mock import Mock, AsyncMock

def test_joystick_event_handler():
    """测试操纵杆事件处理器基本功能"""
    print("=== 第二步测试：JoystickEventHandler 桥接功能 ===")
    
    # 创建模拟的WebSocket服务器
    mock_websocket_server = Mock()
    mock_websocket_server.send_to_client = AsyncMock()
    
    # 1. 测试事件处理器初始化
    print("\n1. 测试事件处理器初始化...")
    handler = JoystickEventHandler(mock_websocket_server)
    
    # 验证初始化状态
    assert handler.websocket_server == mock_websocket_server
    assert handler.is_active == False
    assert len(handler.joystick_clients) == 0
    print("✓ 事件处理器初始化成功")
    
    # 2. 测试启动和停止
    print("\n2. 测试启动和停止...")
    handler.start()
    assert handler.is_active == True
    print("✓ 事件处理器启动成功")
    
    handler.stop()
    assert handler.is_active == False
    print("✓ 事件处理器停止成功")
    
    # 重新启动以继续测试
    handler.start()
    
    # 3. 测试消息处理器映射
    print("\n3. 测试消息处理器映射...")
    expected_handlers = [
        'joystick_connect',
        'joystick_disconnect', 
        'joystick_reset_center',
        'joystick_start_boundary',
        'joystick_stop_boundary',
        'joystick_get_status',
        'joystick_subscribe',
        'joystick_unsubscribe'
    ]
    
    for handler_name in expected_handlers:
        assert handler_name in handler.message_handlers
        print(f"✓ 消息处理器 {handler_name} 存在")
    
    # 4. 测试客户端订阅功能
    print("\n4. 测试客户端订阅功能...")
    
    async def test_subscription():
        # 测试订阅
        subscribe_message = {'type': 'joystick_subscribe'}
        result = await handler.handle_message('client1', subscribe_message)
        
        assert result['type'] == 'joystick_subscribe_response'
        assert result['success'] == True
        assert 'client1' in handler.joystick_clients
        print("✓ 客户端订阅成功")
        
        # 测试取消订阅
        unsubscribe_message = {'type': 'joystick_unsubscribe'}
        result = await handler.handle_message('client1', unsubscribe_message)
        
        assert result['type'] == 'joystick_unsubscribe_response'
        assert result['success'] == True
        assert 'client1' not in handler.joystick_clients
        print("✓ 客户端取消订阅成功")
    
    asyncio.run(test_subscription())
    
    # 5. 测试获取状态功能
    print("\n5. 测试获取状态功能...")
    
    async def test_status():
        status_message = {'type': 'joystick_get_status'}
        result = await handler.handle_message('client1', status_message)
        
        assert result['type'] == 'joystick_status_response'
        assert 'status' in result
        print("✓ 获取状态功能正常")
    
    asyncio.run(test_status())
    
    # 6. 测试连接操纵杆功能
    print("\n6. 测试连接操纵杆功能...")
    
    async def test_connect():
        connect_message = {'type': 'joystick_connect'}
        result = await handler.handle_message('client1', connect_message)
        
        assert result['type'] == 'joystick_connect_response'
        assert 'success' in result
        assert 'status' in result
        
        if result['success']:
            print("✓ 操纵杆连接成功")
        else:
            print("! 操纵杆连接失败（可能是设备未连接）")
    
    asyncio.run(test_connect())
    
    # 7. 测试重置中心位置功能
    print("\n7. 测试重置中心位置功能...")
    
    async def test_reset_center():
        reset_message = {'type': 'joystick_reset_center'}
        result = await handler.handle_message('client1', reset_message)
        
        assert result['type'] == 'joystick_reset_center_response'
        assert 'success' in result
        print("✓ 重置中心位置功能正常")
    
    asyncio.run(test_reset_center())
    
    # 8. 测试边界检测功能
    print("\n8. 测试边界检测功能...")
    
    async def test_boundary_detection():
        # 开始边界检测
        start_message = {'type': 'joystick_start_boundary'}
        result = await handler.handle_message('client1', start_message)
        
        assert result['type'] == 'joystick_start_boundary_response'
        assert 'success' in result
        print("✓ 开始边界检测功能正常")
        
        # 停止边界检测
        stop_message = {'type': 'joystick_stop_boundary'}
        result = await handler.handle_message('client1', stop_message)
        
        assert result['type'] == 'joystick_stop_boundary_response'
        assert 'success' in result
        print("✓ 停止边界检测功能正常")
    
    asyncio.run(test_boundary_detection())
    
    # 9. 测试未知消息处理
    print("\n9. 测试未知消息处理...")
    
    async def test_unknown_message():
        unknown_message = {'type': 'unknown_type'}
        result = await handler.handle_message('client1', unknown_message)
        
        assert result['type'] == 'error'
        assert 'unknown_type' in result['message']
        print("✓ 未知消息处理正常")
    
    asyncio.run(test_unknown_message())
    
    # 10. 测试客户端移除功能
    print("\n10. 测试客户端移除功能...")
    
    async def test_client_removal():
        # 先订阅
        subscribe_message = {'type': 'joystick_subscribe'}
        await handler.handle_message('client1', subscribe_message)
        assert 'client1' in handler.joystick_clients
        
        # 移除客户端
        handler.remove_client('client1')
        assert 'client1' not in handler.joystick_clients
        print("✓ 客户端移除功能正常")
    
    asyncio.run(test_client_removal())
    
    # 11. 测试统计信息
    print("\n11. 测试统计信息...")
    stats = handler.get_stats()
    
    assert 'active' in stats
    assert 'connected' in stats
    assert 'subscribed_clients' in stats
    assert 'device_status' in stats
    assert 'last_broadcast_time' in stats
    print("✓ 统计信息功能正常")
    
    # 12. 测试数据广播（模拟）
    print("\n12. 测试数据广播功能...")
    
    async def test_broadcast():
        # 添加两个客户端
        subscribe_message = {'type': 'joystick_subscribe'}
        await handler.handle_message('client1', subscribe_message)
        await handler.handle_message('client2', subscribe_message)
        
        # 模拟操纵杆数据
        test_data = {
            'type': 'joystick_data',
            'timestamp': time.time(),
            'data': {
                'main_x': 0.5,
                'main_y': -0.3,
                'sub_y': 0.1,
                'buttons': {
                    'button1': True,
                    'button2': False,
                    'button7': False
                }
            }
        }
        
        # 触发数据处理
        handler._handle_joystick_data(test_data)
        
        # 等待异步任务完成
        await asyncio.sleep(0.1)
        
        # 验证模拟服务器被调用
        assert mock_websocket_server.send_to_client.call_count >= 2
        print("✓ 数据广播功能正常")
    
    asyncio.run(test_broadcast())
    
    # 13. 清理测试
    print("\n13. 清理测试...")
    handler.stop()
    
    # 14. 显示测试结果
    print("\n=== 测试结果汇总 ===")
    print(f"事件处理器状态: {'活跃' if handler.is_active else '停止'}")
    print(f"订阅客户端数量: {len(handler.joystick_clients)}")
    print(f"支持的消息类型: {list(handler.message_handlers.keys())}")
    print(f"模拟服务器调用次数: {mock_websocket_server.send_to_client.call_count}")
    
    print("\n=== 第二步测试完成 ===")

if __name__ == "__main__":
    test_joystick_event_handler()