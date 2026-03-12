"""
测试外部配置更新接口
向 ws://localhost:8765 发送 config_update 消息，验证配置文件是否被正确更新。

用法:
  python test_config_update.py '{"current_difficulty": "high", "audio_enabled": false}'
  python test_config_update.py '{"userId": "pilot_01", "includeAI": true, "isPractice": false}'
  python test_config_update.py                # 不带参数则使用默认测试值
"""

import asyncio
import json
import sys
import websockets

WS_URL = "ws://localhost:8080/ws"

# DEFAULT_PAYLOAD = {
#     "userId": "test_pilot_101",
#     "includeAI": True,
#     "isPractice": False,
#     "current_difficulty": "high",
#     "audio_enabled": False
# }
DEFAULT_PAYLOAD = {
    "userId": "test_pilot_101",
    "includeAI": False,
    "isPractice": True,
    "current_difficulty": "high",
    "audio_enabled": True
}

async def send_config_update(payload: dict):
    print(f"连接 {WS_URL} ...")
    async with websockets.connect(WS_URL) as ws:
        init_data = await ws.recv()
        print(f"收到初始数据 ({len(init_data)} bytes)，跳过")

        msg = {"type": "config_update", **payload}
        print(f"发送:\n{json.dumps(msg, ensure_ascii=False, indent=2)}")
        await ws.send(json.dumps(msg))

        resp = await asyncio.wait_for(ws.recv(), timeout=5)
        result = json.loads(resp)
        print(f"响应:\n{json.dumps(result, ensure_ascii=False, indent=2)}")

        if result.get("status") == "ok":
            print("✅ 配置更新成功")
        else:
            print("❌ 配置更新失败")


def main():
    if len(sys.argv) > 1:
        try:
            payload = json.loads(sys.argv[1])
        except json.JSONDecodeError as e:
            print(f"JSON 解析失败: {e}")
            print('用法: python test_config_update.py \'{"current_difficulty": "high", "audio_enabled": false}\'')
            sys.exit(1)
    else:
        payload = DEFAULT_PAYLOAD
        print("未指定参数，使用默认测试值")

    asyncio.run(send_config_update(payload))


if __name__ == "__main__":
    main()
