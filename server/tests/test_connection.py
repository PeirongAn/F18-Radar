import asyncio
import websockets
import json

async def test_connection():
    uri = "ws://localhost:8765"
    try:
        async with websockets.connect(uri) as websocket:
            print("连接到雷达服务器成功!")
            
            # 接收第一条消息
            message = await websocket.recv()
            data = json.loads(message)
            
            # 显示部分数据
            print(f"接收到雷达数据:")
            print(f"  雷达方位角: {data['radar_azimuth']}")
            print(f"  自机航向: {data['own_heading']}")
            print(f"  目标数量: {len(data['targets'])}")
            
            # 如果有目标，显示第一个目标的信息
            if data['targets']:
                target = data['targets'][0]
                print(f"\n第一个目标信息:")
                print(f"  ID: {target['id']}")
                print(f"  位置: ({target['x']:.2f}, {target['y']:.2f}) 海里")
                print(f"  距离: {target['distance']:.2f} 海里")
                print(f"  方位角: {target['bearing']:.2f}°")
                print(f"  航向: {target['heading']:.2f}°")
                print(f"  速度: {target['speed']:.2f} 节")
                print(f"  威胁等级: {target['threat_level']}")
                
            print("\n连接测试成功!")
            
    except websockets.exceptions.ConnectionClosedError:
        print("连接关闭: 服务器关闭了连接")
    except websockets.exceptions.InvalidStatusCode:
        print("连接失败: 无效的状态码")
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection()) 