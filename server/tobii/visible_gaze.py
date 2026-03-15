import requests
import tkinter as tk
from tkinter import ttk
import threading
import time
import json
import math
from collections import deque
from pynput import keyboard

class GazeOverlay:
    def __init__(self, server_url="http://localhost:8081"):
        self.server_url = server_url
        self.current_gaze = None
        self.gaze_history = deque(maxlen=50)  # 保存历史轨迹
        self.running = True
        self.last_update = 0
        
        # 创建透明窗口
        self.root = tk.Tk()
        self.root.title("Gaze Overlay")
        
        # 设置窗口为全屏透明
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)  # 始终在最前
        self.root.attributes('-transparentcolor', 'black')  # 设置黑色为透明色
        self.root.overrideredirect(True)  # 无边框
        
        # 获取屏幕尺寸
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        
        # 创建画布
        self.canvas = tk.Canvas(
            self.root,
            width=self.screen_width,
            height=self.screen_height,
            bg='black',  # 黑色作为透明色
            highlightthickness=0
        )
        self.canvas.pack()
        
        # 绑定键盘事件用于退出
        self.root.bind('<Escape>', self.quit)
        self.root.bind('q', self.quit)
        
        # 确保窗口能够接收键盘事件
        self.root.focus_force()
        
        # 监听所有键盘事件，确保即使窗口在后台也能响应
        self.root.bind_all('<Escape>', self.quit)
        self.root.bind_all('q', self.quit)
        
        # 可视化元素
        self.gaze_dot = None
        self.gaze_ring = None
        self.gaze_cross_h = None
        self.gaze_cross_v = None
        self.history_lines = []
        self.info_text = None
        
        # 配置
        self.dot_radius = 4  # 最小中心点半径
        self.ring_radius = 10  # 最小外圈半径
        self.cross_size = 7  # 最小十字准星大小
        self.history_opacity = 0.3
        self.show_history = True
        self.show_info = True
        self.show_gaze = True  # 控制注视点显示/隐藏
        self.smooth_factor = 0.9  # 平滑因子
        self.smooth_x = None
        self.smooth_y = None
        
        # 颜色配置 (RGB格式)
        self.colors = {
            'dot': '#FF4444',      # 红色
            'ring': '#FF8888',     # 浅红
            'cross': '#44FF44',    # 绿色
            'history': '#FFFF44',  # 黄色
            'info': '#FFFFFF'      # 白色
        }
        
        # 预计算历史轨迹颜色表
        self.history_colors = [f'#{i:02x}{i:02x}00' for i in range(0, 256, 10)]
        
        # 预计算正弦值表用于呼吸效果
        self.sin_table = [math.sin(i * 0.1) for i in range(63)]  # 预计算63个值
        self.sin_index = 0
        
        # 启动更新线程
        self.update_thread = threading.Thread(target=self.update_loop)
        self.update_thread.daemon = True
        self.update_thread.start()
        
        # 启动定时刷新
        self.refresh_display()
        
        # 启动全局键盘监听器
        self.keyboard_listener = keyboard.Listener(on_press=self.on_key_press)
        self.keyboard_listener.daemon = True
        self.keyboard_listener.start()
        
    def fetch_gaze(self):
        """从服务器获取注视点"""
        try:
            response = requests.get(f"{self.server_url}/tobii/gaze_point", timeout=1)
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    # Tobii坐标是0-1的归一化坐标
                    norm_x, norm_y = data["gaze_point"]
                    
                    # 转换为屏幕坐标
                    screen_x = int(norm_x * self.screen_width)
                    screen_y = int(norm_y * self.screen_height)
                    
                    # 平滑处理
                    if self.smooth_x is None:
                        self.smooth_x = screen_x
                        self.smooth_y = screen_y
                    else:
                        self.smooth_x = self.smooth_x * (1 - self.smooth_factor) + screen_x * self.smooth_factor
                        self.smooth_y = self.smooth_y * (1 - self.smooth_factor) + screen_y * self.smooth_factor
                    
                    current_time = time.time()
                    self.current_gaze = {
                        'x': int(self.smooth_x),
                        'y': int(self.smooth_y),
                        'raw_x': screen_x,
                        'raw_y': screen_y,
                        'timestamp': current_time
                    }
                    
                    # 添加到历史
                    self.gaze_history.append((self.smooth_x, self.smooth_y, current_time))
                    
                    self.last_update = current_time
                    
        except requests.exceptions.RequestException as e:
            # 静默失败，不打印错误
            pass
        except Exception as e:
            print(f"处理数据出错: {e}")
    
    def update_loop(self):
        """后台更新循环"""
        while self.running:
            self.fetch_gaze()
            time.sleep(0.01)  # 100fps轮询
    
    def draw_gaze(self):
        """在画布上绘制注视点"""
        # 清除旧的绘制
        self.canvas.delete("gaze")
        
        if not self.show_gaze:
            return
            
        if not self.current_gaze:
            # 显示等待信息
            if self.show_info:
                self.canvas.create_text(
                    self.screen_width // 2,
                    self.screen_height // 2,
                    text="等待注视点数据...",
                    fill='#888888',
                    font=('Arial', 24),
                    tags="gaze"
                )
            return
        
        x = self.current_gaze['x']
        y = self.current_gaze['y']
        
        # 检查数据是否过期（超过1秒）
        if time.time() - self.current_gaze['timestamp'] > 1.0:
            # 显示过期警告
            if self.show_info:
                self.canvas.create_text(
                    x, y - 40,
                    text="数据过期",
                    fill='#888888',
                    font=('Arial', 12),
                    tags="gaze"
                )
        
        # 绘制历史轨迹
        if self.show_history and len(self.gaze_history) > 1:
            # 只绘制最近的20个点，减少计算和绘制
            recent_points = list(self.gaze_history)[-20:]
            for i in range(len(recent_points) - 1):
                x1, y1, t1 = recent_points[i]
                x2, y2, t2 = recent_points[i + 1]
                
                # 根据时间计算透明度
                age = time.time() - t2
                alpha = max(0, min(0.5, 0.5 - age * 0.5))
                
                # 使用预计算的颜色值
                alpha_index = min(int(alpha * 25), 24)  # 0-24
                color = self.history_colors[alpha_index]
                
                self.canvas.create_line(
                    x1, y1, x2, y2,
                    fill=color,
                    width=2,
                    tags="gaze"
                )
        
        # 绘制外圈（呼吸效果）
        ring_radius = self.ring_radius + self.sin_table[self.sin_index] * 3
        self.sin_index = (self.sin_index + 1) % len(self.sin_table)
        self.canvas.create_oval(
            x - ring_radius, y - ring_radius,
            x + ring_radius, y + ring_radius,
            outline=self.colors['ring'],
            width=2,
            tags="gaze"
        )
        
        # 绘制十字准星
        self.canvas.create_line(
            x - self.cross_size, y,
            x + self.cross_size, y,
            fill=self.colors['cross'],
            width=2,
            tags="gaze"
        )
        self.canvas.create_line(
            x, y - self.cross_size,
            x, y + self.cross_size,
            fill=self.colors['cross'],
            width=2,
            tags="gaze"
        )
        
        # 绘制中心点
        self.canvas.create_oval(
            x - self.dot_radius, y - self.dot_radius,
            x + self.dot_radius, y + self.dot_radius,
            fill=self.colors['dot'],
            outline='',
            tags="gaze"
        )
        
        # 绘制内圈亮点
        self.canvas.create_oval(
            x - 3, y - 3,
            x + 3, y + 3,
            fill='white',
            outline='',
            tags="gaze"
        )
        
        # 显示信息
        if self.show_info:
            info_y = y - 40
            self.canvas.create_text(
                x + 30, info_y,
                text=f"({x}, {y})",
                fill=self.colors['info'],
                font=('Arial', 12),
                anchor='w',
                tags="gaze"
            )
            
            # 显示状态指示器
            status = "●" if time.time() - self.last_update < 0.1 else "○"
            status_color = '#00FF00' if time.time() - self.last_update < 0.1 else '#FF0000'
            self.canvas.create_text(
                x + 30, info_y + 20,
                text=f"数据流 {status}",
                fill=status_color,
                font=('Arial', 12),
                anchor='w',
                tags="gaze"
            )
    
    def refresh_display(self):
        """定时刷新显示"""
        if self.running:
            self.draw_gaze()
            self.root.after(10, self.refresh_display)  # 100fps，与数据获取频率匹配
    
    def quit(self, event=None):
        """退出程序"""
        self.running = False
        self.root.quit()
    
    def on_key_press(self, key):
        """全局键盘事件处理"""
        try:
            # 处理字符按键
            if hasattr(key, 'char') and key.char:
                if key.char == 'q':
                    self.quit()
                elif key.char == 'h':
                    self.toggle_history()
                elif key.char == 'i':
                    self.toggle_info()
                elif key.char == 'g':
                    self.toggle_gaze()
                elif key.char == '+':
                    self.increase_size()
                elif key.char == '-':
                    self.decrease_size()
            # 处理特殊按键
            elif key == keyboard.Key.esc:
                self.quit()
        except Exception as e:
            pass
    
    def toggle_gaze(self, event=None):
        """切换注视点显示/隐藏"""
        self.show_gaze = not self.show_gaze
    
    def run(self):
        """运行主循环"""
        print(f"注视点Overlay已启动")
        print(f"服务器地址: {self.server_url}")
        print(f"屏幕尺寸: {self.screen_width}x{self.screen_height}")
        print("按 ESC 或 'q' 退出")
        print("Overlay将显示在所有窗口之上")
        
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.quit()

class GazeOverlayWithControls(GazeOverlay):
    """带控制面板的Overlay"""
    
    def __init__(self, server_url="http://localhost:8081"):
        super().__init__(server_url)
        
        # 添加控制面板
        self.create_control_panel()
        
        # 绑定快捷键（全局）
        self.root.bind_all('h', self.toggle_history)
        self.root.bind_all('i', self.toggle_info)
        self.root.bind_all('+', self.increase_size)
        self.root.bind_all('-', self.decrease_size)
        
    def create_control_panel(self):
        """创建控制面板"""
        # 创建半透明控制窗口
        self.control_win = tk.Toplevel(self.root)
        self.control_win.title("Gaze Overlay 控制")
        self.control_win.attributes('-topmost', True)
        self.control_win.geometry("300x250+10+10")
        
        # 控制面板内容
        frame = ttk.Frame(self.control_win, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="注视点Overlay控制", font=('Arial', 12, 'bold')).pack(pady=5)
        
        # 显示历史轨迹
        self.history_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frame,
            text="显示历史轨迹",
            variable=self.history_var,
            command=self.toggle_history_cb
        ).pack(anchor=tk.W, pady=2)
        
        # 显示坐标信息
        self.info_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frame,
            text="显示坐标信息",
            variable=self.info_var,
            command=self.toggle_info_cb
        ).pack(anchor=tk.W, pady=2)
        
        # 显示注视点
        self.gaze_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frame,
            text="显示注视点",
            variable=self.gaze_var,
            command=self.toggle_gaze_cb
        ).pack(anchor=tk.W, pady=2)
        
        # 大小控制
        ttk.Label(frame, text="注视点大小:").pack(anchor=tk.W, pady=(10,0))
        self.size_var = tk.IntVar(value=10)  # 初始值设为最小值
        size_scale = ttk.Scale(
            frame,
            from_=10,
            to=50,
            variable=self.size_var,
            command=self.change_size
        )
        size_scale.pack(fill=tk.X, pady=2)
        
        # 平滑因子
        ttk.Label(frame, text="平滑因子:").pack(anchor=tk.W, pady=(10,0))
        self.smooth_var = tk.DoubleVar(value=0.3)
        smooth_scale = ttk.Scale(
            frame,
            from_=0.0,
            to=0.9,
            variable=self.smooth_var,
            command=self.change_smooth
        )
        smooth_scale.pack(fill=tk.X, pady=2)
        
        # 状态显示
        self.status_label = ttk.Label(frame, text="状态: 运行中")
        self.status_label.pack(pady=10)
        
        # 快捷键说明
        shortcuts = [
            "快捷键:",
            "H - 切换历史轨迹",
            "I - 切换信息显示",
            "G - 切换注视点显示/隐藏",
            "+/- - 调整大小",
            "ESC - 退出"
        ]
        for text in shortcuts:
            ttk.Label(frame, text=text, font=('Arial', 9)).pack(anchor=tk.W)
    
    def toggle_history(self, event=None):
        """切换历史轨迹显示"""
        self.show_history = not self.show_history
        self.history_var.set(self.show_history)
        print(f"历史轨迹显示: {'开启' if self.show_history else '关闭'}")
    
    def toggle_history_cb(self):
        """历史轨迹复选框回调"""
        self.show_history = self.history_var.get()
    
    def toggle_info(self, event=None):
        """切换信息显示"""
        self.show_info = not self.show_info
        self.info_var.set(self.show_info)
        print(f"信息显示: {'开启' if self.show_info else '关闭'}")
    
    def toggle_info_cb(self):
        """切换信息显示（回调）"""
        self.show_info = self.info_var.get()
    
    def toggle_gaze_cb(self):
        """切换注视点显示（回调）"""
        self.show_gaze = self.gaze_var.get()
    
    def increase_size(self, event=None):
        """增加大小"""
        self.size_var.set(min(50, self.size_var.get() + 2))
        self.change_size()
    
    def decrease_size(self, event=None):
        """减小大小"""
        self.size_var.set(max(10, self.size_var.get() - 2))
        self.change_size()
    
    def change_size(self, value=None):
        """改变注视点大小"""
        size = self.size_var.get()
        self.dot_radius = size // 2
        self.ring_radius = size
        self.cross_size = size * 3 // 4
    
    def change_smooth(self, value=None):
        """改变平滑因子"""
        self.smooth_factor = self.smooth_var.get()

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='桌面Overlay注视点可视化')
    parser.add_argument('--server', type=str, default='http://localhost:8081',
                       help='Tobii服务器地址')
    parser.add_argument('--no-controls', action='store_true',
                       help='不显示控制面板')
    parser.add_argument('--no-history', action='store_true',
                       help='默认不显示历史轨迹')
    
    args = parser.parse_args()
    
    # 创建Overlay
    if args.no_controls:
        overlay = GazeOverlay(server_url=args.server)
    else:
        overlay = GazeOverlayWithControls(server_url=args.server)
    
    if args.no_history:
        overlay.show_history = False
        if hasattr(overlay, 'history_var'):
            overlay.history_var.set(False)
    
    # 运行
    try:
        overlay.run()
    except KeyboardInterrupt:
        print("\n程序已退出")

if __name__ == "__main__":
    main()