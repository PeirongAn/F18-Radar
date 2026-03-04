"""
摇杆 HID 数据诊断脚本
自动连接所有匹配的 HID 接口，分阶段采集数据，输出分析结果。
"""
import pywinusb.hid as hid
import time
import threading
import sys
import os

LOG_FILE = os.path.join(os.path.dirname(__file__), "joystick_diagnose_log.txt")
PHASE_DURATION = 4  # 每个阶段采集秒数

PHASES = [
    ("REST",    "请不要动摇杆，保持静止"),
    ("FORWARD", "请把摇杆向 前 推到底，保持住"),
    ("BACK",    "请把摇杆向 后 拉到底，保持住"),
    ("LEFT",    "请把摇杆向 左 推到底，保持住"),
    ("RIGHT",   "请把摇杆向 右 推到底，保持住"),
    ("TWIST_L", "请把摇杆 逆时针旋转 到底，保持住（如果支持旋转）"),
    ("TWIST_R", "请把摇杆 顺时针旋转 到底，保持住（如果支持旋转）"),
    ("REST2",   "请松开摇杆，回到中心静止"),
]


class HIDDiagnostics:
    def __init__(self):
        self.samples = {}  # {interface_idx: {phase: [raw_bytes_list]}}
        self.current_phase = None
        self.collecting = False
        self.devices = []
        self.lock = threading.Lock()

    def find_devices(self):
        all_devs = hid.HidDeviceFilter().get_devices()
        if not all_devs:
            print("未找到任何 HID 设备")
            return []
        self.devices = all_devs
        return all_devs

    def _make_handler(self, idx):
        def handler(data):
            if not self.collecting or self.current_phase is None:
                return
            with self.lock:
                raw = bytes(data)
                self.samples.setdefault(idx, {}).setdefault(self.current_phase, []).append(raw)
        return handler

    def run_diagnosis(self, device_indices):
        opened = []
        for idx in device_indices:
            dev = self.devices[idx]
            try:
                dev.open()
                dev.set_raw_data_handler(self._make_handler(idx))
                opened.append((idx, dev))
                print(f"  已打开接口 #{idx}: {dev.product_name} [{dev.vendor_id:04X}:{dev.product_id:04X}]")
            except Exception as e:
                print(f"  打开接口 #{idx} 失败: {e}")

        if not opened:
            print("没有成功打开任何接口，退出。")
            return

        print(f"\n共打开 {len(opened)} 个接口，即将开始诊断（共 {len(PHASES)} 个阶段，每阶段 {PHASE_DURATION} 秒）\n")
        time.sleep(1)

        for phase_name, instruction in PHASES:
            print("=" * 60)
            print(f">>> 阶段: {phase_name}")
            print(f">>> {instruction}")
            print(f">>> 采集 {PHASE_DURATION} 秒...")
            print("=" * 60)
            time.sleep(1)  # 给用户一秒反应时间

            self.current_phase = phase_name
            self.collecting = True
            time.sleep(PHASE_DURATION)
            self.collecting = False
            self.current_phase = None

            total = sum(len(self.samples.get(idx, {}).get(phase_name, [])) for idx, _ in opened)
            print(f"    采集完毕，共 {total} 个样本\n")

        # 关闭设备
        for idx, dev in opened:
            try:
                dev.close()
            except:
                pass

        self._analyze_and_write()

    def _analyze_and_write(self):
        lines = []
        lines.append("=" * 80)
        lines.append("摇杆 HID 诊断报告")
        lines.append("=" * 80)

        for iface_idx in sorted(self.samples.keys()):
            dev = self.devices[iface_idx]
            lines.append(f"\n{'='*60}")
            lines.append(f"接口 #{iface_idx}: {dev.product_name} "
                         f"[{dev.vendor_id:04X}:{dev.product_id:04X}]")
            lines.append(f"{'='*60}")

            phase_data = self.samples[iface_idx]
            if not phase_data:
                lines.append("  无数据")
                continue

            # 每个阶段统计每个字节位置的 min/max
            phase_stats = {}  # {phase: {byte_idx: (min, max)}}
            packet_len = 0
            for phase_name in [p[0] for p in PHASES]:
                samples = phase_data.get(phase_name, [])
                if not samples:
                    continue
                plen = len(samples[0])
                packet_len = max(packet_len, plen)
                stats = {}
                for bi in range(plen):
                    vals = [s[bi] for s in samples if bi < len(s)]
                    if vals:
                        stats[bi] = (min(vals), max(vals))
                phase_stats[phase_name] = stats

            lines.append(f"  数据包长度: {packet_len} 字节")

            # 输出每个阶段的首个样本（十六进制）
            for phase_name in [p[0] for p in PHASES]:
                samples = phase_data.get(phase_name, [])
                if samples:
                    first = samples[0]
                    last = samples[-1]
                    hex_first = ' '.join(f'{b:02X}' for b in first)
                    hex_last = ' '.join(f'{b:02X}' for b in last)
                    lines.append(f"\n  [{phase_name}] 样本数={len(samples)}")
                    lines.append(f"    首: {hex_first}")
                    lines.append(f"    末: {hex_last}")
                    st = phase_stats.get(phase_name, {})
                    # 找出变化范围 > 2 的字节
                    varying = []
                    for bi in range(len(first)):
                        if bi in st:
                            mn, mx = st[bi]
                            if mx - mn > 2:
                                varying.append(f"[{bi}]={mn:02X}~{mx:02X}(幅{mx-mn})")
                    if varying:
                        lines.append(f"    内部波动字节: {', '.join(varying)}")
                    else:
                        lines.append(f"    内部波动字节: 无明显波动")

            # 关键对比：REST vs 每个运动阶段
            rest_stats = phase_stats.get("REST", {})
            rest_samples = phase_data.get("REST", [])
            if rest_samples:
                rest_median = []
                for bi in range(len(rest_samples[0])):
                    vals = sorted([s[bi] for s in rest_samples if bi < len(s)])
                    rest_median.append(vals[len(vals)//2] if vals else 0)

                lines.append(f"\n  --- 运动对比（相对 REST 中位值的变化）---")
                for phase_name in [p[0] for p in PHASES if p[0] not in ("REST", "REST2")]:
                    move_samples = phase_data.get(phase_name, [])
                    if not move_samples:
                        lines.append(f"  [{phase_name}] 无数据")
                        continue
                    move_median = []
                    for bi in range(min(len(rest_median), len(move_samples[0]))):
                        vals = sorted([s[bi] for s in move_samples if bi < len(s)])
                        move_median.append(vals[len(vals)//2] if vals else 0)

                    diffs = []
                    for bi in range(min(len(rest_median), len(move_median))):
                        delta = move_median[bi] - rest_median[bi]
                        if abs(delta) > 3:
                            diffs.append(f"[{bi}] {rest_median[bi]:02X}->{move_median[bi]:02X} (Δ{delta:+d})")
                    if diffs:
                        lines.append(f"  [{phase_name}] 显著变化: {', '.join(diffs)}")
                    else:
                        lines.append(f"  [{phase_name}] 无显著变化")

        report = '\n'.join(lines)
        print("\n" + report)
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n诊断报告已保存到: {LOG_FILE}")


def main():
    target_vid = 0x044F
    target_pid = 0x0402

    diag = HIDDiagnostics()
    all_devs = diag.find_devices()
    if not all_devs:
        return

    indices = []
    for i, d in enumerate(all_devs):
        if d.vendor_id == target_vid and d.product_id == target_pid:
            indices.append(i)
            print(f"  找到匹配设备 [{i}]: {d.product_name}")

    if not indices:
        print(f"未找到 VID={target_vid:04X} PID={target_pid:04X} 的设备")
        print("所有设备列表:")
        for i, d in enumerate(all_devs):
            print(f"  [{i:2d}] VID={d.vendor_id:04X} PID={d.product_id:04X}  "
                  f"{d.vendor_name or '?'} / {d.product_name or '?'}")
        return

    print(f"\n将诊断 {len(indices)} 个接口，3秒后开始...")
    print("请准备好摇杆，跟随屏幕提示操作！\n")
    time.sleep(3)
    diag.run_diagnosis(indices)


if __name__ == "__main__":
    main()
