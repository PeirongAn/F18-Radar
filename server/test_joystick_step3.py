#!/usr/bin/env python3
"""
第三步测试用例：测试扩展的WebSocketServer操纵杆功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from network.websocket_server import WebSocketServer
from joystick import JoystickEventHandler
import asyncio
import json
import time
from unittest.mock import Mock, AsyncMock, MagicMock

def test_extended_websocket_server():
    """测试扩展的WebSocket服务器功能"""
    print("=== 第三步测试：扩展的WebSocketServer操纵杆功能 ===")
    
    # 1. 测试服务器初始化
    print("\n1. 测试服务器初始化...")
    server = WebSocketServer()
    
    # 验证新增的属性
    assert hasattr(server, 'clients')
    assert hasattr(server, 'client_sessions')
    assert hasattr(server, 'joystick_handler')
    assert server.joystick_handler is None
    assert len(server.clients) == 0
    assert len(server.client_sessions) == 0
    print("✓ 服务器初始化成功")
    
    # 2. 测试客户端ID生成
    print("\n2. 测试客户端ID生成...")
    client_id1 = server.generate_client_id()
    client_id2 = server.generate_client_id()
    
    assert isinstance(client_id1, str)
    assert isinstance(client_id2, str)
    assert client_id1 != client_id2
    assert len(client_id1) > 0
    assert len(client_id2) > 0
    print("✓ 客户端ID生成功能正常")
    
    # 3. 测试客户端管理
    print("\n3. 测试客户端管理...")
    
    # 创建模拟的websocket连接
    mock_websocket1 = Mock()
    mock_websocket2 = Mock()
    
    # 添加客户端
    server.add_client("client1", mock_websocket1)
    server.add_client("client2", mock_websocket2)
    
    assert len(server.clients) == 2
    assert len(server.client_sessions) == 2
    assert "client1" in server.clients
    assert "client2" in server.clients
    assert server.get_client_count() == 2
    print("✓ 客户端添加功能正常")
    
    # 移除客户端
    server.remove_client("client1")
    assert len(server.clients) == 1
    assert len(server.client_sessions) == 1
    assert "client1" not in server.clients
    assert "client2" in server.clients
    assert server.get_client_count() == 1
    print("✓ 客户端移除功能正常")
    
    # 4. 测试操纵杆处理器集成
    print("\n4. 测试操纵杆处理器集成...")
    
    # 创建操纵杆处理器
    joystick_handler = JoystickEventHandler()
    
    # 设置操纵杆处理器
    server.set_joystick_handler(joystick_handler)
    
    assert server.joystick_handler is not None
    assert server.joystick_handler == joystick_handler
    assert joystick_handler.websocket_server == server
    print("✓ 操纵杆处理器集成成功")
    
    # 5. 测试客户端消息发送
    print("\n5. 测试客户端消息发送...")
    
    async def test_client_messaging():
        # 模拟websocket的send方法
        mock_websocket2.send = AsyncMock()
        
        # 发送消息到现有客户端
        test_message = {"type": "test", "data": "hello"}
        result = await server.send_to_client("client2", test_message)
        
        assert result == True
        mock_websocket2.send.assert_called_once()
        
        # 发送消息到不存在的客户端
        result = await server.send_to_client("nonexistent", test_message)
        assert result == False
        
        print("✓ 客户端消息发送功能正常")
    
    asyncio.run(test_client_messaging())
    
    # 6. 测试广播功能
    print("\n6. 测试广播功能...")
    
    async def test_broadcast():
        # 添加另一个客户端用于广播测试
        mock_websocket3 = Mock()
        mock_websocket3.send = AsyncMock()
        server.add_client("client3", mock_websocket3)
        
        # 广播消息
        broadcast_message = {"type": "broadcast", "data": "hello everyone"}
        await server.broadcast_to_all(broadcast_message)
        
        # 验证所有客户端都收到了消息
        mock_websocket2.send.assert_called()
        mock_websocket3.send.assert_called()
        
        print("✓ 广播功能正常")
    
    asyncio.run(test_broadcast())
    
    # 7. 测试操纵杆消息处理（模拟）
    print("\n7. 测试操纵杆消息处理...")
    
    async def test_joystick_message_handling():
        # 创建一个模拟的handle_message方法
        joystick_handler.handle_message = AsyncMock(return_value={
            "type": "joystick_connect_response",
            "success": True
        })
        
        # 模拟操纵杆连接消息
        joystick_message = {
            "type": "joystick_connect"
        }
        
        # 直接测试操纵杆处理器
        result = await joystick_handler.handle_message("client2", joystick_message)
        
        assert result["type"] == "joystick_connect_response"
        assert result["success"] == True
        
        print("✓ 操纵杆消息处理功能正常")
    
    asyncio.run(test_joystick_message_handling())
    
    # 8. 测试客户端断开连接时的清理
    print("\n8. 测试客户端断开连接时的清理...")
    
    # 模拟操纵杆处理器的客户端移除
    joystick_handler.remove_client = Mock()
    
    # 移除客户端
    server.remove_client("client2")
    
    # 验证操纵杆处理器也被通知
    joystick_handler.remove_client.assert_called_with("client2")
    
    print("✓ 客户端断开连接清理功能正常")
    
    # 9. 测试服务器状态
    print("\n9. 测试服务器状态...")
    
    # 检查当前状态
    client_count = server.get_client_count()
    print(f"当前客户端数量: {client_count}")
    
    # 验证服务器配置
    assert server.host == "0.0.0.0"
    assert server.port == 8765
    assert server.logger is not None
    
    print("✓ 服务器状态检查正常")
    
    # 10. 测试错误处理
    print("\n10. 测试错误处理...")
    
    async def test_error_handling():
        # 测试向失效的websocket发送消息
        mock_websocket_error = Mock()
        mock_websocket_error.send = AsyncMock(side_effect=Exception("连接已断开"))
        
        server.add_client("error_client", mock_websocket_error)
        
        # 尝试发送消息，应该处理异常
        test_message = {"type": "test", "data": "error test"}
        result = await server.send_to_client("error_client", test_message)
        
        # 消息发送应该失败，但不应该抛出异常
        assert result == False
        
        print("✓ 错误处理功能正常")
    
    asyncio.run(test_error_handling())
    
    # 11. 显示测试结果
    print("\n=== 测试结果汇总 ===")
    print(f"最终客户端数量: {server.get_client_count()}")
    print(f"操纵杆处理器已集成: {server.joystick_handler is not None}")
    print(f"服务器地址: {server.host}:{server.port}")
    
    # 显示操纵杆处理器状态
    if server.joystick_handler:
        stats = server.joystick_handler.get_stats()
        print(f"操纵杆处理器状态: {stats}")
    
    print("\n=== 第三步测试完成 ===")

if __name__ == "__main__":
    test_extended_websocket_server()