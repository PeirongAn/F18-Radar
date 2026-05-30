"""
Tobii 眼动仪连接测试

用法: python test_tobii.py
在 server/tobii/ 目录下运行，依次验证 SDK 安装、设备发现、数据流通。
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import time
import math


def test_sdk():
    """测试 tobii_research SDK 是否安装"""
    try:
        import tobii_research as tr
        print(f"✅ tobii_research 已安装, 版本: {tr.__version__}")
        return tr
    except ImportError:
        print("❌ tobii_research 未安装, 请运行: pip install tobii-research")
        return None


def test_device(tr):
    """测试是否能发现眼动仪设备"""
    trackers = tr.find_all_eyetrackers()
    if not trackers:
        print("❌ 未找到眼动仪，请检查 USB 连接")
        return None

    et = trackers[0]
    print(f"✅ 找到设备: {et.device_name}")
    print(f"   型号: {et.model}")
    print(f"   序列号: {et.serial_number}")
    print(f"   地址: {et.address}")
    return et


def test_data_stream(tr, et, duration_sec=2):
    """测试能否收到眼动数据流"""
    frames = []

    def on_gaze(data):
        frames.append(data)

    et.subscribe_to(tr.EYETRACKER_GAZE_DATA, on_gaze, as_dictionary=True)
    print(f"\n⏳ 采集 {duration_sec} 秒数据...")
    time.sleep(duration_sec)
    et.unsubscribe_from(tr.EYETRACKER_GAZE_DATA, on_gaze)

    hz = len(frames) / duration_sec if duration_sec > 0 else 0
    print(f"✅ 收到 {len(frames)} 帧 (~{hz:.0f} Hz)")

    if frames:
        last = frames[-1]
        lp = last.get("left_gaze_point_on_display_area", (0, 0))
        rp = last.get("right_gaze_point_on_display_area", (0, 0))
        lv = last.get("left_gaze_point_validity", 0)
        rv = last.get("right_gaze_point_validity", 0)
        print(f"   最后一帧: 左眼={lp} (valid={lv}), 右眼={rp} (valid={rv})")

        valid_count = sum(
            1 for f in frames
            if f.get("left_gaze_point_validity") == 1
            or f.get("right_gaze_point_validity") == 1
        )
        print(f"   有效帧占比: {valid_count}/{len(frames)} ({valid_count/len(frames)*100:.1f}%)")

    return frames


def test_gaze_service():
    """测试 GazeService 集成（可选）"""
    import os
    import sys
    sys.path.insert(0, os.path.dirname(__file__))

    try:
        from gaze_service import GazeService
    except ImportError:
        print("⚠️ 无法导入 GazeService，跳过集成测试")
        return

    import tempfile
    test_dir = os.path.join(tempfile.gettempdir(), "gaze_service_test")
    svc = GazeService(data_dir=test_dir)

    try:
        device_name = svc.connect()
        print(f"\n✅ GazeService.connect() 成功: {device_name}")
    except Exception as e:
        print(f"\n❌ GazeService.connect() 失败: {e}")
        svc.shutdown()
        return

    task_id = svc.start_task(
        bbox=[[100, 100, 500, 400]],
        screen_size=(1920, 1080),
        task_id="test_task",
        user_id="test_user",
        task_name="tobii_test",
    )
    print(f"✅ start_task: task_id={task_id}")
    task_dir = svc._current_task["task_dir"]
    print(f"   数据目录: {task_dir}")

    print("⏳ 采集 3 秒...")
    time.sleep(3)

    point, ts = svc.get_latest_gaze_point()
    print(f"   最新注视点: {point}, 时间戳: {ts}")

    result = svc.stop_task(task_id=task_id)
    task_info = result["task_info"]
    print(
        "✅ stop_task: "
        f"frames={task_info['frame_count']}, "
        f"valid_frames={task_info.get('valid_frames', 0)}, "
        f"in_region_frames={task_info.get('in_region_frames', 0)}"
    )

    svc.disconnect()
    svc.shutdown()

    # 检查生成的逐帧 raw 文件；任务摘要和 marker 从 gaze_records.db 查询。
    raw_path = os.path.join(task_dir, "raw_gaze.jsonl")
    if os.path.exists(raw_path):
        size = os.path.getsize(raw_path)
        lines = sum(1 for _ in open(raw_path, encoding="utf-8")) if size > 0 else 0
        print(f"   📄 raw_gaze.jsonl: {size} bytes, {lines} lines")
    else:
        print("   ⚠️ raw_gaze.jsonl: 未生成")
    db_path = os.path.join(test_dir, "gaze_records.db")
    print(f"   🗄️ gaze_records.db: {'已生成' if os.path.exists(db_path) else '未生成'}")

    print(f"\n测试数据目录: {test_dir}")
    print("测试完毕后可手动删除。")


if __name__ == "__main__":
    print("=" * 50)
    print("Tobii 眼动仪连接测试")
    print("=" * 50)

    # Step 1: SDK
    print("\n[1/3] 检查 SDK...")
    tr = test_sdk()
    if tr is None:
        exit(1)

    # Step 2: Device
    print("\n[2/3] 查找设备...")
    et = test_device(tr)
    if et is None:
        exit(1)

    # Step 3: Data stream
    print("\n[3/3] 测试数据流...")
    frames = test_data_stream(tr, et)
    if not frames:
        print("⚠️ 未收到任何帧，请确认眼动仪已校准且有人在注视")

    # Step 4 (optional): GazeService integration
    print("\n[附加] GazeService 集成测试...")
    test_gaze_service()

    print("\n" + "=" * 50)
    print("全部测试完成")
    print("=" * 50)
