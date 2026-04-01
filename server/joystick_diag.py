#!/usr/bin/env python3
"""
摇杆诊断脚本 - 逐步排查无输出原因
直接运行: python joystick_diag.py
"""
import os, sys, time
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

print("=== 步骤 1: 导入 pygame ===")
try:
    import pygame
    print(f"  OK  pygame {pygame.version.ver}")
except ImportError as e:
    print(f"  失败: {e}")
    sys.exit(1)

print("\n=== 步骤 2: pygame.init() ===")
fails = pygame.init()
print(f"  初始化结果: {fails}")

print("\n=== 步骤 3: 创建最小窗口（部分系统必须有窗口才能 pump 事件）===")
try:
    screen = pygame.display.set_mode((200, 100))
    pygame.display.set_caption("joystick diag")
    print("  OK  窗口已创建")
except Exception as e:
    print(f"  警告: {e}（继续）")
    screen = None

print("\n=== 步骤 4: 初始化 joystick 子系统 ===")
pygame.joystick.init()
count = pygame.joystick.get_count()
print(f"  检测到设备数量: {count}")
if count == 0:
    print("  !! 未检测到任何摇杆，请检查 USB 连接")
    sys.exit(1)

print("\n=== 步骤 5: 列出所有设备 ===")
for i in range(count):
    j = pygame.joystick.Joystick(i)
    j.init()
    print(f"  [{i}] {j.get_name()}  轴:{j.get_numaxes()}  按键:{j.get_numbuttons()}  Hat:{j.get_numhats()}")

candidates = []
for i in range(count):
    j = pygame.joystick.Joystick(i)
    j.init()
    name = j.get_name().lower()
    priority = 0 if "joystick" in name else (2 if "throttle" in name else 1)
    candidates.append((priority, i, j))
candidates.sort(key=lambda x: x[0])
js = candidates[0][2]
print(f"\n使用设备 [{candidates[0][1]}]: {js.get_name()}")

print("\n=== 步骤 6: 连续读取原始值（5 秒，请移动摇杆）===")
print("  格式: axis0  axis1  hat  buttons")
print("-" * 50)

start = time.time()
prev_line = ""
while time.time() - start < 5:
    pygame.event.pump()   # 主线程
    if screen:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                break

    a0 = round(js.get_axis(0), 3) if js.get_numaxes() > 0 else 0
    a1 = round(js.get_axis(1), 3) if js.get_numaxes() > 1 else 0
    hat = js.get_hat(0) if js.get_numhats() > 0 else (0, 0)
    btns = [i for i in range(js.get_numbuttons()) if js.get_button(i)]

    line = f"  ax0={a0:+.3f}  ax1={a1:+.3f}  hat={hat}  btn={btns}"
    if line != prev_line:          # 有任何变化就打印
        print(line)
        prev_line = line

    time.sleep(0.02)

print("-" * 50)
print("\n=== 步骤 7: 使用 JOYAXISMOTION 事件读取（5 秒）===")
print("  此方式依赖事件队列，若上面有值但这里没有，说明事件系统有问题")
print("-" * 50)

pygame.event.clear()
start = time.time()
event_count = 0
while time.time() - start < 5:
    pygame.event.pump()
    if screen:
        pygame.display.flip()

    for ev in pygame.event.get():
        if ev.type == pygame.JOYAXISMOTION:
            print(f"  JOYAXISMOTION axis={ev.axis} value={ev.value:+.4f}")
            event_count += 1
        elif ev.type == pygame.JOYBUTTONDOWN:
            print(f"  JOYBUTTONDOWN  button={ev.button}")
            event_count += 1
        elif ev.type == pygame.JOYHATMOTION:
            print(f"  JOYHATMOTION   value={ev.value}")
            event_count += 1

    time.sleep(0.02)

print("-" * 50)
if event_count == 0:
    print("  !! 5 秒内未收到任何事件，请确认摇杆在此期间有移动")
else:
    print(f"  共收到 {event_count} 个事件")

pygame.quit()
print("\n=== 诊断完成 ===")
print("请将以上输出发给开发者进行分析。")
