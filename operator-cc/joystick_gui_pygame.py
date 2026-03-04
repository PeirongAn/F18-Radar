"""
基于 pygame (DirectInput) 的摇杆实时图形化调试工具
实时显示所有轴值、按钮状态、帽子开关，带可视化条形图。
"""
import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

import tkinter as tk
from tkinter import ttk
import pygame
import threading
import time


class JoystickMonitorGUI:
    POLL_INTERVAL = 16  # ms, ~60fps

    def __init__(self):
        pygame.init()
        pygame.joystick.init()

        self.root = tk.Tk()
        self.root.title("摇杆实时监控 (pygame/DirectInput)")
        self.root.geometry("820x700")
        self.root.resizable(True, True)

        self.joystick = None
        self.axis_widgets = []
        self.button_widgets = []
        self.hat_widgets = []
        self.axis_min = {}
        self.axis_max = {}

        self._build_ui()
        self._refresh_devices()

    # ─── UI 构建 ────────────────────────────────────────────

    def _build_ui(self):
        top = ttk.Frame(self.root)
        top.pack(fill=tk.X, padx=8, pady=4)

        ttk.Label(top, text="设备:").pack(side=tk.LEFT)
        self.device_combo = ttk.Combobox(top, state='readonly', width=45)
        self.device_combo.pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="刷新", command=self._refresh_devices, width=6).pack(side=tk.LEFT, padx=2)
        self.connect_btn = ttk.Button(top, text="连接", command=self._connect, width=6)
        self.connect_btn.pack(side=tk.LEFT, padx=2)
        self.disconnect_btn = ttk.Button(top, text="断开", command=self._disconnect, width=6, state='disabled')
        self.disconnect_btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="重置范围", command=self._reset_ranges, width=8).pack(side=tk.LEFT, padx=2)

        self.status_var = tk.StringVar(value="未连接")
        ttk.Label(top, textvariable=self.status_var, foreground='gray').pack(side=tk.RIGHT)

        # 滚动区域
        container = ttk.Frame(self.root)
        container.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        self.scroll_frame = ttk.Frame(canvas)
        self.scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scroll_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        # 轴区域
        self.axes_frame = ttk.LabelFrame(self.scroll_frame, text="轴 (Axes)")
        self.axes_frame.pack(fill=tk.X, pady=4, padx=4)

        # 按钮区域
        self.buttons_frame = ttk.LabelFrame(self.scroll_frame, text="按钮 (Buttons)")
        self.buttons_frame.pack(fill=tk.X, pady=4, padx=4)

        # 帽子区域
        self.hats_frame = ttk.LabelFrame(self.scroll_frame, text="帽子开关 (Hats)")
        self.hats_frame.pack(fill=tk.X, pady=4, padx=4)

        # 日志区域
        log_frame = ttk.LabelFrame(self.scroll_frame, text="轴值日志（最近变化）")
        log_frame.pack(fill=tk.X, pady=4, padx=4)
        self.log_text = tk.Text(log_frame, height=6, font=('Courier', 9), state='disabled', wrap='none')
        self.log_text.pack(fill=tk.X, padx=4, pady=2)

    # ─── 设备管理 ────────────────────────────────────────────

    def _refresh_devices(self):
        pygame.joystick.quit()
        pygame.joystick.init()
        count = pygame.joystick.get_count()
        devices = []
        for i in range(count):
            js = pygame.joystick.Joystick(i)
            js.init()
            devices.append(f"[{i}] {js.get_name()} (轴:{js.get_numaxes()} 键:{js.get_numbuttons()} 帽:{js.get_numhats()})")
        self.device_combo['values'] = devices
        if devices:
            self.device_combo.current(0)
        self.status_var.set(f"检测到 {count} 个控制器")

    def _connect(self):
        sel = self.device_combo.current()
        if sel < 0:
            return
        self.joystick = pygame.joystick.Joystick(sel)
        self.joystick.init()
        self._build_controls()
        self._reset_ranges()
        self.connect_btn.config(state='disabled')
        self.disconnect_btn.config(state='normal')
        name = self.joystick.get_name()
        self.status_var.set(f"已连接: {name}")
        self._poll()

    def _disconnect(self):
        self.joystick = None
        self.connect_btn.config(state='normal')
        self.disconnect_btn.config(state='disabled')
        self.status_var.set("已断开")

    def _reset_ranges(self):
        self.axis_min.clear()
        self.axis_max.clear()

    # ─── 动态构建控件 ────────────────────────────────────────

    def _build_controls(self):
        js = self.joystick

        # 清理旧控件
        for w in self.axes_frame.winfo_children():
            w.destroy()
        for w in self.buttons_frame.winfo_children():
            w.destroy()
        for w in self.hats_frame.winfo_children():
            w.destroy()
        self.axis_widgets.clear()
        self.button_widgets.clear()
        self.hat_widgets.clear()

        # 轴
        num_axes = js.get_numaxes()
        for i in range(num_axes):
            row = ttk.Frame(self.axes_frame)
            row.pack(fill=tk.X, padx=4, pady=1)

            lbl = ttk.Label(row, text=f"A{i}", width=3, font=('Courier', 10, 'bold'))
            lbl.pack(side=tk.LEFT)

            canvas = tk.Canvas(row, height=22, bg='#222', highlightthickness=0)
            canvas.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

            val_lbl = ttk.Label(row, text="+0.0000", width=8, font=('Courier', 10))
            val_lbl.pack(side=tk.LEFT)
            range_lbl = ttk.Label(row, text="[+0.0000 ~ +0.0000]", width=24, font=('Courier', 9), foreground='gray')
            range_lbl.pack(side=tk.LEFT)

            self.axis_widgets.append({
                'canvas': canvas,
                'val_lbl': val_lbl,
                'range_lbl': range_lbl,
            })

        # 按钮
        num_buttons = js.get_numbuttons()
        cols = 10
        for i in range(num_buttons):
            r, c = divmod(i, cols)
            if c == 0:
                btn_row = ttk.Frame(self.buttons_frame)
                btn_row.pack(fill=tk.X, padx=4, pady=1)
            bl = tk.Label(btn_row, text=f"B{i}", width=5, height=1,
                          bg='#ddd', relief='raised', font=('Courier', 9))
            bl.pack(side=tk.LEFT, padx=2, pady=1)
            self.button_widgets.append(bl)

        # 帽子
        num_hats = js.get_numhats()
        for i in range(num_hats):
            row = ttk.Frame(self.hats_frame)
            row.pack(fill=tk.X, padx=4, pady=2)
            ttk.Label(row, text=f"Hat{i}", width=5, font=('Courier', 10, 'bold')).pack(side=tk.LEFT)

            hat_canvas = tk.Canvas(row, width=60, height=60, bg='#222', highlightthickness=1, highlightbackground='#555')
            hat_canvas.pack(side=tk.LEFT, padx=8)
            hat_lbl = ttk.Label(row, text="(0, 0)", font=('Courier', 10))
            hat_lbl.pack(side=tk.LEFT)

            self.hat_widgets.append({'canvas': hat_canvas, 'lbl': hat_lbl})

    # ─── 实时轮询 ────────────────────────────────────────────

    def _poll(self):
        if self.joystick is None:
            return

        pygame.event.pump()
        js = self.joystick
        num_axes = js.get_numaxes()
        log_parts = []

        for i in range(num_axes):
            val = js.get_axis(i)
            # 更新范围
            if i not in self.axis_min or val < self.axis_min[i]:
                self.axis_min[i] = val
            if i not in self.axis_max or val > self.axis_max[i]:
                self.axis_max[i] = val

            w = self.axis_widgets[i]
            w['val_lbl'].config(text=f"{val:+.4f}")
            w['range_lbl'].config(text=f"[{self.axis_min[i]:+.4f} ~ {self.axis_max[i]:+.4f}]")

            # 画条形图：中心在中间，值用彩色条
            c = w['canvas']
            c.delete('all')
            cw = c.winfo_width()
            ch = c.winfo_height()
            if cw < 10:
                cw = 400
            mid = cw / 2
            # 背景中线
            c.create_line(mid, 0, mid, ch, fill='#555', width=1)
            # 范围指示（灰色）
            mn_x = mid + self.axis_min[i] * mid
            mx_x = mid + self.axis_max[i] * mid
            c.create_rectangle(mn_x, 2, mx_x, ch - 2, fill='#333', outline='')
            # 当前值（彩色条）
            bar_x = mid + val * mid
            color = '#00cc66' if abs(val) < 0.05 else ('#ff9933' if abs(val) < 0.5 else '#ff3333')
            if bar_x >= mid:
                c.create_rectangle(mid, 4, bar_x, ch - 4, fill=color, outline='')
            else:
                c.create_rectangle(bar_x, 4, mid, ch - 4, fill=color, outline='')
            # 数字刻度
            for tick in [-1, -0.5, 0, 0.5, 1]:
                tx = mid + tick * mid
                c.create_text(tx, ch - 2, text=f"{tick:.1f}", fill='#666', font=('Arial', 7), anchor='s')

            log_parts.append(f"A{i}={val:+.4f}")

        # 按钮
        for i in range(js.get_numbuttons()):
            pressed = js.get_button(i)
            bl = self.button_widgets[i]
            if pressed:
                bl.config(bg='#44cc44', relief='sunken')
            else:
                bl.config(bg='#ddd', relief='raised')

        # 帽子
        for i in range(js.get_numhats()):
            hx, hy = js.get_hat(i)
            w = self.hat_widgets[i]
            w['lbl'].config(text=f"({hx:+d}, {hy:+d})")
            hc = w['canvas']
            hc.delete('all')
            cx, cy = 30, 30
            hc.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill='#555')
            # 十字线
            hc.create_line(10, 30, 50, 30, fill='#444')
            hc.create_line(30, 10, 30, 50, fill='#444')
            dot_x = cx + hx * 18
            dot_y = cy - hy * 18
            hc.create_oval(dot_x - 5, dot_y - 5, dot_x + 5, dot_y + 5, fill='#ff5555', outline='white')

        # 日志
        log_line = '  '.join(log_parts)
        self.log_text.config(state='normal')
        self.log_text.insert('end', log_line + '\n')
        self.log_text.see('end')
        # 最多保留 200 行
        line_count = int(self.log_text.index('end-1c').split('.')[0])
        if line_count > 200:
            self.log_text.delete('1.0', f'{line_count - 200}.0')
        self.log_text.config(state='disabled')

        self.root.after(self.POLL_INTERVAL, self._poll)

    # ─── 运行 ────────────────────────────────────────────────

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        self.joystick = None
        pygame.quit()
        self.root.destroy()


if __name__ == '__main__':
    app = JoystickMonitorGUI()
    app.run()
