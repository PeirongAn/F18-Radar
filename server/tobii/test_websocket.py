import asyncio
import websockets
import json
import time

WS_URL = "ws://127.0.0.1:8082"

async def test_websocket():
    print("正在连接到WebSocket服务器...")
    async with websockets.connect(WS_URL) as websocket:
        print("连接成功！")
        
        # 1. 测试消息
        print("\n=== 测试消息 ===")
        test_message = {
            "type": "test",
            "message": "Hello WebSocket!"
        }
        await websocket.send(json.dumps(test_message))
        response = await websocket.recv()
        print("收到响应:", json.loads(response))
        
        # 2. 发送窗口出现请求
        print("\n=== 窗口出现请求 ===")
        start_message = {
            "type": "hand",
            "bbox": [[0.0, 0.0, 960, 540], [0.0, 0.0, 960, 540], [0.0, 0.0, 960, 540]],
            "coordinate_space": "physical_pixel",
            "screen_data": [1920, 1080],
            "system_time": int(time.time() * 1000 * 1000),  # 微秒
            "box_visible": True,
            "user_id": 1,
            "task_source": "web",
            "task_name": "demo_task"
        }
        await websocket.send(json.dumps(start_message))
        response = await websocket.recv()
        start_result = json.loads(response)
        print("收到响应:", start_result)
        
        if not start_result.get("ok"):
            print("窗口出现请求失败")
            return
        
        task_id = start_result.get("task_id")
        print("获取到 task_id:", task_id)
        
        # 3. 等待并接收实时注视数据
        print("\n=== 接收实时注视数据 (5秒) ===")
        start_time = time.time()
        gaze_update_count = 0
        
        while time.time() - start_time < 5:
            try:
                # 等待接收消息，设置超时
                response = await asyncio.wait_for(websocket.recv(), timeout=0.5)
                data = json.loads(response)
                if data.get("type") == "gaze_update":
                    gaze_update_count += 1
                    # 每10个更新打印一次
                    if gaze_update_count % 10 == 0:
                        print(f"收到注视数据更新 #{gaze_update_count}: {data['gaze_point']}")
            except asyncio.TimeoutError:
                # 超时，继续循环
                pass
        
        print(f"共收到 {gaze_update_count} 次注视数据更新")
        
        # 4. 发送窗口消失请求
        print("\n=== 窗口消失请求 ===")
        end_message = {
            "type": "hand",
            "task_id": task_id,
            "bbox": [[0.0, 0.0, 960, 540], [0.0, 0.0, 960, 540], [0.0, 0.0, 960, 540]],
            "coordinate_space": "physical_pixel",
            "screen_data": [1920, 1080],
            "system_time": int(time.time() * 1000 * 1000),  # 微秒
            "box_visible": False,
            "user_id": 1,
            "task_source": "web",
            "task_name": "demo_task"
        }
        await websocket.send(json.dumps(end_message))
        response = await websocket.recv()
        end_result = json.loads(response)
        print("收到响应:", end_result)
        
        if not end_result.get("ok"):
            print("窗口消失请求失败")
            return
        
        # 5. 测试获取注视点
        print("\n=== 获取注视点 ===")
        gaze_message = {
            "type": "gaze_point"
        }
        await websocket.send(json.dumps(gaze_message))
        response = await websocket.recv()
        gaze_result = json.loads(response)
        print("收到响应:", gaze_result)
        
        print("\n测试完成！")

if __name__ == "__main__":
    asyncio.run(test_websocket())
