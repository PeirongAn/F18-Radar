#!/usr/bin/env python3
"""
摇杆实时监控工具（主线程直驱版）
- pygame.event.pump() 在主线程调用，彻底解决 Win10 子线程无响应问题
- 键盘输入用 msvcrt.kbhit() 非阻塞检测（Windows），Linux/Mac 降级为 select
- 第一次输出完整快照，后续只打印变化字段
- 按 Enter 显示当前完整快照，按 q 退出
"""

import sys
import os
import time

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame

# ─── 颜色输出 ──────────────────────────────────────────────
try:
    import colorama
    colorama.init()
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    RED    = "\033[91m"
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
except ImportError:
    GREEN = YELLOW = CYAN = RED = RESET = BOLD = ""

# ─── 非阻塞键盘输入 ────────────────────────────────────────
if sys.platform == "win32":
    import msvcrt

    def kb_hit() -> bool:
        return msvcrt.kbhit()

    def kb_read() -> str:
        ch = msvcrt.getwche()
        if ch in ("\r", "\n"):
            print()          # 换行对齐输出
            return "enter"
        return ch.lower()
else:
    import select, tty, termios

    def kb_hit() -> bool:
        return select.select([sys.stdin], [], [], 0)[0] != []

    def kb_read() -> str:
        ch = sys.stdin.read(1)
        return "enter" if ch == "\n" else ch.lower()

# ─── 格式化工具 ────────────────────────────────────────────
AXIS_THRESHOLD = 0.005

def fmt_axis(val: float) -> str:
    bar_len = 20
    filled = int((val + 1) / 2 * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)
    return f"[{bar}] {val:+.4f}"

def fmt_buttons(buttons: dict) -> str:
    active = [k for k, v in buttons.items() if v]
    return f"{YELLOW}{', '.join(active)}{RESET}" if active else "(无)"

def print_full(d: dict, label: str):
    t = time.strftime("%H:%M:%S") + f".{int((time.time() % 1) * 1000):03d}"
    print(f"\n{BOLD}{CYAN}[{t}] {label}{RESET}")
    print(f"  主轴 X : {fmt_axis(d.get('main_x', 0))}")
    print(f"  主轴 Y : {fmt_axis(d.get('main_y', 0))}")
    print(f"  Sub  X : {d.get('sub_x', 0):+d}   Sub Y : {d.get('sub_y', 0):+d}")
    print(f"  按键   : {fmt_buttons(d.get('buttons', {}))}")

def print_diff(prev: dict, curr: dict, count: int):
    t = time.strftime("%H:%M:%S") + f".{int((time.time() % 1) * 1000):03d}"
    lines = []

    if abs(curr.get("main_x", 0) - prev.get("main_x", 0)) > AXIS_THRESHOLD:
        lines.append(f"  主轴 X : {fmt_axis(curr['main_x'])}")
    if abs(curr.get("main_y", 0) - prev.get("main_y", 0)) > AXIS_THRESHOLD:
        lines.append(f"  主轴 Y : {fmt_axis(curr['main_y'])}")
    if curr.get("sub_x") != prev.get("sub_x") or curr.get("sub_y") != prev.get("sub_y"):
        lines.append(f"  Sub  X : {curr.get('sub_x', 0):+d}   Sub Y : {curr.get('sub_y', 0):+d}")

    prev_btn = prev.get("buttons", {})
    curr_btn = curr.get("buttons", {})
    changed = {k for k in curr_btn if curr_btn.get(k) != prev_btn.get(k)}
    if changed:
        detail = "  ".join(
            f"{YELLOW}{k}↓{RESET}" if curr_btn[k] else f"{k}↑"
            for k in sorted(changed)
        )
        lines.append(f"  按键   : {detail}")

    if lines:
        print(f"\n{BOLD}{CYAN}[{t}] #{count}{RESET}")
        print("\n".join(lines))

# ─── 读取摇杆原始数据 ──────────────────────────────────────
def read_joystick(js: pygame.joystick.JoystickType) -> dict:
    num_axes    = js.get_numaxes()
    num_buttons = js.get_numbuttons()
    num_hats    = js.get_numhats()

    axis_x = js.get_axis(0) if num_axes > 0 else 0.0
    axis_y = js.get_axis(1) if num_axes > 1 else 0.0

    hat_x, hat_y = (js.get_hat(0) if num_hats > 0 else (0, 0))

    buttons = {f"button{i}": bool(js.get_button(i)) for i in range(min(num_buttons, 19))}

    return {
        "main_x": round(axis_x, 4),
        "main_y": round(axis_y, 4),
        "sub_x":  hat_x,
        "sub_y":  hat_y,
        "buttons": buttons,
    }

def has_change(prev: dict, curr: dict) -> bool:
    if not prev:
        return True
    for k in curr["buttons"]:
        if curr["buttons"].get(k) != prev.get("buttons", {}).get(k):
            return True
    if curr["sub_x"] != prev.get("sub_x") or curr["sub_y"] != prev.get("sub_y"):
        return True
    if (abs(curr["main_x"] - prev.get("main_x", 0)) > AXIS_THRESHOLD or
            abs(curr["main_y"] - prev.get("main_y", 0)) > AXIS_THRESHOLD):
        return True
    return False

# ─── 主程序 ────────────────────────────────────────────────
def main():
    print(f"{BOLD}摇杆实时监控{RESET}  |  Enter = 完整快照  |  q = 退出\n")

    # pygame 在主线程初始化
    pygame.init()
    # 部分 Win10 驱动要求有 display surface 才能正常 pump 事件
    pygame.display.set_mode((1, 1), pygame.NOFRAME)
    pygame.joystick.init()

    count = pygame.joystick.get_count()
    if count == 0:
        print(f"{RED}未检测到摇杆设备，请检查 USB 连接后重试。{RESET}")
        pygame.quit()
        sys.exit(1)

    # 列出所有设备，优先选名称含 "joystick" 的（避免误选 throttle 油门台）
    candidates = []
    for i in range(count):
        j = pygame.joystick.Joystick(i)
        j.init()
        name = j.get_name().lower()
        if "throttle" in name:
            priority = 2
        elif "joystick" in name:
            priority = 0
        elif "warthog" in name or "thrustmaster" in name:
            priority = 1
        else:
            priority = 3
        candidates.append((priority, i, j))
        print(f"  [{i}] {j.get_name()}  轴:{j.get_numaxes()}  按键:{j.get_numbuttons()}")

    candidates.sort(key=lambda x: x[0])
    js = candidates[0][2]

    print(f"\n{GREEN}使用设备: {js.get_name()}{RESET}")
    print(f"  轴数: {js.get_numaxes()}   按键数: {js.get_numbuttons()}   Hat 数: {js.get_numhats()}")
    print(f"\n摇动摇杆或按下按键，变化将实时显示。\n")

    prev_d: dict = {}
    change_count = 0
    POLL_MS = 20  # 50 Hz

    try:
        while True:
            # ── 主线程 pump，Win10 必须在此调用 ──
            pygame.event.pump()
            pygame.display.flip()   # 配合 display surface 刷新事件队列

            curr_d = read_joystick(js)

            if has_change(prev_d, curr_d):
                if change_count == 0:
                    print_full(curr_d, label="初始状态")
                else:
                    print_diff(prev_d, curr_d, change_count + 1)
                prev_d = curr_d.copy()
                change_count += 1

            # ── 非阻塞键盘检测 ──
            if kb_hit():
                ch = kb_read()
                if ch in ("q",):
                    print("退出中...")
                    break
                else:  # Enter 或其他键 → 显示快照
                    if prev_d:
                        print_full(prev_d, label=f"当前快照  (已捕获 {change_count} 次变化)")
                    else:
                        print(f"{YELLOW}尚未收到任何数据，请移动摇杆。{RESET}")

            time.sleep(POLL_MS / 1000)

    except KeyboardInterrupt:
        print("\n收到中断信号，退出。")
    finally:
        pygame.quit()
        print("已退出。")


if __name__ == "__main__":
    main()
