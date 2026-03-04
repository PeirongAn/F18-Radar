"""
使用 pygame (DirectInput) 诊断摇杆轴数据
"""
import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame
import time

LOG_FILE = os.path.join(os.path.dirname(__file__), "joystick_diagnose_log.txt")
PHASE_DURATION = 4

PHASES = [
    ("REST",    "请不要动摇杆，保持静止"),
    ("FORWARD", "请把摇杆向 前 推到底，保持住"),
    ("BACK",    "请把摇杆向 后 拉到底，保持住"),
    ("LEFT",    "请把摇杆向 左 推到底，保持住"),
    ("RIGHT",   "请把摇杆向 右 推到底，保持住"),
    ("TWIST_L", "请把摇杆 逆时针旋转 到底（如果支持）"),
    ("TWIST_R", "请把摇杆 顺时针旋转 到底（如果支持）"),
    ("REST2",   "请松开摇杆，回到中心静止"),
]


def main():
    pygame.init()
    pygame.joystick.init()

    count = pygame.joystick.get_count()
    print(f"找到 {count} 个游戏控制器:")
    if count == 0:
        print("未检测到控制器，退出。")
        return

    joysticks = []
    for i in range(count):
        js = pygame.joystick.Joystick(i)
        js.init()
        print(f"  [{i}] {js.get_name()}")
        print(f"      轴数={js.get_numaxes()}  按钮数={js.get_numbuttons()}  "
              f"帽子数={js.get_numhats()}")
        joysticks.append(js)

    print(f"\n3 秒后开始诊断，共 {len(PHASES)} 个阶段，每阶段 {PHASE_DURATION} 秒...")
    print("请跟随提示操作摇杆！\n")
    time.sleep(3)

    all_results = {}  # {js_idx: {phase: [snapshots]}}

    for phase_name, instruction in PHASES:
        print("=" * 60)
        print(f">>> 阶段: {phase_name}")
        print(f">>> {instruction}")
        print(f">>> 采集 {PHASE_DURATION} 秒...")
        print("=" * 60)
        time.sleep(0.5)

        start = time.time()
        while time.time() - start < PHASE_DURATION:
            pygame.event.pump()
            for ji, js in enumerate(joysticks):
                snap = {
                    'axes': [round(js.get_axis(a), 4) for a in range(js.get_numaxes())],
                    'buttons': [js.get_button(b) for b in range(js.get_numbuttons())],
                    'hats': [js.get_hat(h) for h in range(js.get_numhats())],
                }
                all_results.setdefault(ji, {}).setdefault(phase_name, []).append(snap)
            time.sleep(0.01)

        for ji, js in enumerate(joysticks):
            samples = all_results[ji][phase_name]
            axes = samples[-1]['axes']
            axes_str = '  '.join(f'A{i}={v:+.4f}' for i, v in enumerate(axes))
            print(f"  [{js.get_name()}] 最新轴值: {axes_str}")
        print()

    # 分析
    lines = []
    lines.append("=" * 80)
    lines.append("摇杆 pygame/DirectInput 诊断报告")
    lines.append("=" * 80)

    for ji, js in enumerate(joysticks):
        lines.append(f"\n{'='*60}")
        lines.append(f"控制器 [{ji}]: {js.get_name()}")
        lines.append(f"  轴数={js.get_numaxes()}  按钮数={js.get_numbuttons()}  帽子数={js.get_numhats()}")
        lines.append(f"{'='*60}")

        phases_data = all_results.get(ji, {})

        # 每个阶段每个轴的 min/max/median
        for phase_name, _ in PHASES:
            samples = phases_data.get(phase_name, [])
            if not samples:
                lines.append(f"\n  [{phase_name}] 无数据")
                continue
            num_axes = len(samples[0]['axes'])
            lines.append(f"\n  [{phase_name}] 样本数={len(samples)}")
            axis_info = []
            for ai in range(num_axes):
                vals = [s['axes'][ai] for s in samples]
                mn, mx = min(vals), max(vals)
                med = sorted(vals)[len(vals)//2]
                axis_info.append(f"A{ai}: med={med:+.4f} [{mn:+.4f} ~ {mx:+.4f}]")
            lines.append("    " + "  |  ".join(axis_info))

            # 按钮
            num_buttons = len(samples[0]['buttons'])
            pressed = []
            for bi in range(num_buttons):
                if any(s['buttons'][bi] for s in samples):
                    pressed.append(f"B{bi}")
            if pressed:
                lines.append(f"    按钮按下: {', '.join(pressed)}")

        # REST vs 运动对比
        rest_samples = phases_data.get("REST", [])
        if rest_samples:
            num_axes = len(rest_samples[0]['axes'])
            rest_medians = []
            for ai in range(num_axes):
                vals = sorted([s['axes'][ai] for s in rest_samples])
                rest_medians.append(vals[len(vals)//2])

            lines.append(f"\n  --- 运动对比（相对 REST 中位值的变化）---")
            for phase_name, _ in PHASES:
                if phase_name in ("REST", "REST2"):
                    continue
                samples = phases_data.get(phase_name, [])
                if not samples:
                    continue
                move_medians = []
                for ai in range(num_axes):
                    vals = sorted([s['axes'][ai] for s in samples])
                    move_medians.append(vals[len(vals)//2])

                diffs = []
                for ai in range(num_axes):
                    delta = move_medians[ai] - rest_medians[ai]
                    if abs(delta) > 0.05:
                        diffs.append(f"A{ai}: {rest_medians[ai]:+.4f} -> {move_medians[ai]:+.4f} (Δ{delta:+.4f})")
                if diffs:
                    lines.append(f"  [{phase_name}] {', '.join(diffs)}")
                else:
                    lines.append(f"  [{phase_name}] 无显著变化")

    report = '\n'.join(lines)
    print("\n" + report)
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n诊断报告已保存到: {LOG_FILE}")

    pygame.quit()


if __name__ == "__main__":
    main()
