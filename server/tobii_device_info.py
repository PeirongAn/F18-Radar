"""
从本仓库自带的 Tobii SDK（server/tobii/tobii_research）枚举眼动仪并打印基本信息。
用法（在 server 目录或项目根目录均可）:
  python tobii_device_info.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_TOBII_DIR = Path(__file__).resolve().parent / "tobii"
if _TOBII_DIR.is_dir() and str(_TOBII_DIR) not in sys.path:
    sys.path.insert(0, str(_TOBII_DIR))

import tobii_research as tr


def _safe_call(label: str, fn):
    try:
        return fn()
    except Exception as e:
        return f"<不可用: {e}>"


def main() -> None:
    print("Tobii Pro SDK 版本:", getattr(tr, "__version__", "unknown"))
    print()

    eyetrackers = tr.find_all_eyetrackers()
    n = len(eyetrackers)
    print(f"检测到眼动仪数量: {n}")
    if n == 0:
        print("未连接任何眼动仪，请检查 USB / 驱动 / Tobii 服务。")
        return

    for i, et in enumerate(eyetrackers):
        print("-" * 48)
        print(f"设备 #{i + 1}")
        print(f"  地址 (URI):     {et.address}")
        print(f"  名称:           {et.device_name}")
        print(f"  型号:           {et.model}")
        print(f"  序列号:         {et.serial_number}")
        print(f"  固件版本:       {et.firmware_version}")
        print(f"  Runtime 版本:   {et.runtime_version}")
        caps = et.device_capabilities
        print(f"  能力 (共 {len(caps)} 项):")
        for c in caps:
            print(f"    - {c}")

        freq = _safe_call("gaze_output_frequency", et.get_gaze_output_frequency)
        freqs = _safe_call("all_gaze_output_frequencies", et.get_all_gaze_output_frequencies)
        print(f"  当前 gaze 输出频率: {freq}")
        print(f"  可选 gaze 输出频率: {freqs}")

        mode = _safe_call("eye_tracking_mode", et.get_eye_tracking_mode)
        modes = _safe_call("all_eye_tracking_modes", et.get_all_eye_tracking_modes)
        print(f"  当前眼动追踪模式:   {mode}")
        print(f"  可选眼动追踪模式:   {modes}")


if __name__ == "__main__":
    main()
