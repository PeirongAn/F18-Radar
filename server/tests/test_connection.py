import asyncio
import websockets
import json

async def test_connection():
    uri = "ws://localhost:8765"
    try:
        async with websockets.connect(uri) as websocket:
            print("连接到雷达服务器成功!")

            await websocket.send(json.dumps({
                "type": "task_start",
                "user_id": "connection_test_user",
                "include_ai": False,
                "is_practice": True
            }))

            init_message = json.loads(await websocket.recv())
            radar_message = json.loads(await websocket.recv())

            print(f"接收到任务初始化消息: {init_message['type']}")
            print(f"接收到雷达数据消息: {radar_message['type']}")
            print(f"  雷达方位角: {radar_message['radar_azimuth']}")
            print(f"  自机航向: {radar_message['own_heading']}")
            print(f"  是否包含目标: {'externalTargets' in radar_message}")
            
            print("\n连接测试成功!")
            
    except websockets.exceptions.ConnectionClosedError:
        print("连接关闭: 服务器关闭了连接")
    except websockets.exceptions.InvalidStatusCode:
        print("连接失败: 无效的状态码")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())
