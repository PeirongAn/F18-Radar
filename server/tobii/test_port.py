# import requests
# import time

# url = "http://127.0.0.1:8081/tobii/test"

# data = {
#     "bbox": [100, 100, 400, 300],
#     "system_time": int(time.time() * 1000),
#     "box_visible": True,
#     "user_id": 1,
#     "task_source": "web",
#     "task_name": "demo_task"
# }

# response = requests.post(url, json=data)

# print("状态码:", response.status_code)
# print("返回结果:", response.json())


import requests
import time
import json

BASE_URL = "http://127.0.0.1:8081/tobii/hand"


def send_box_start():
    payload = {
        "bbox":  [[0.0, 0.0, 960, 540],[0.0, 0.0, 960, 540],[0.0, 0.0, 960, 540]],
        "scream_data": [1920, 1080],
        "system_time": int(time.time() * 1000 * 1000),  # 微秒，和 Tobii system_time_stamp 对齐
        "box_visible": True,
        "user_id": 1,
        "task_source": "web",
        "task_name": "demo_task"
    }

    response = requests.post(BASE_URL, json=payload)

    print("=== 窗口出现请求 ===")
    print("状态码:", response.status_code)
    print("返回文本:", response.text)

    try:
        data = response.json()
    except Exception:
        print("返回不是 JSON")
        return None

    return data


def send_box_end(task_id):
    payload = {
        "task_id": task_id,
        "bbox":  [[0.0, 0.0, 960, 540],[0.0, 0.0, 960, 540],[0.0, 0.0, 960, 540]],
        "scream_data": [1920, 1080],
        "system_time": int(time.time() * 1000 *1000 ),  # 微秒
        "box_visible": False,
        "user_id": 1,
        "task_source": "web",
        "task_name": "demo_task"
    }

    response = requests.post(BASE_URL, json=payload)

    print("=== 窗口消失请求 ===")
    print("状态码:", response.status_code)
    print("返回文本:", response.text)

    try:
        data = response.json()
    except Exception:
        print("返回不是 JSON")
        return None

    return data


if __name__ == "__main__":
    # 1. 发送窗口出现
    start_result = send_box_start()
    if not start_result or not start_result.get("ok"):
        print("窗口出现请求失败")
        exit()

    task_id = start_result.get("task_id")
    print("获取到 task_id:", task_id)

    # 2. 等待几秒，模拟窗口显示期间
    print("等待 8 秒，模拟任务进行中...")
    time.sleep(8)

    # 3. 发送窗口消失
    end_result = send_box_end(task_id)
    if not end_result or not end_result.get("ok"):
        print("窗口消失请求失败")
        exit()

    print("测试完成")