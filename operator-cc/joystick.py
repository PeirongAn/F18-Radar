import pywinusb.hid as hid

def list_devices():
    """列出所有连接的HID设备并显示Vendor ID和Product ID"""
    all_devices = hid.HidDeviceFilter().get_devices()
    for device in all_devices:
        print(f"Device Name: {device.product_name}")
        print(f"  Vendor ID: {device.vendor_id}")
        print(f"  Product ID: {device.product_id}")
        print(f"  Manufacturer: {device.vendor_name}")
        print(f"  Serial Number: {device.serial_number}")
        print(f"  Device Path: {device.device_path}")
        print("")

list_devices()


def connect_device_auto():
    """智能连接摇杆设备"""
    all_devices = hid.HidDeviceFilter().get_devices()
    
    # 第一优先级：尝试连接已知的摇杆设备
    known_joystick_devices = [
        (1356, 98),  # China Longcctv 摇杆
        # 可以在这里添加更多已知的摇杆设备ID
    ]
    
    print("正在扫描已知摇杆设备...")
    for vendor_id, product_id in known_joystick_devices:
        for device in all_devices:
            if device.vendor_id == vendor_id and device.product_id == product_id:
                try:
                    device.open()
                    print(f"已连接到已知摇杆设备：{device.product_name}")
                    print(f"  Vendor ID: {device.vendor_id}")
                    print(f"  Product ID: {device.product_id}")
                    print(f"  Manufacturer: {device.vendor_name}")
                    return device
                except Exception as e:
                    print(f"无法连接到设备 {device.product_name}: {e}")
                    continue
    
    # 第二优先级：查找可能的摇杆设备（通过名称关键词）
    print("正在扫描可能的摇杆设备...")
    joystick_keywords = ['joystick', 'gamepad', 'controller', 'stick', '摇杆', 'longcctv']
    
    for device in all_devices:
        device_name = (device.product_name or "").lower()
        manufacturer = (device.vendor_name or "").lower()
        
        # 检查设备名称或制造商是否包含摇杆相关关键词
        if any(keyword in device_name or keyword in manufacturer for keyword in joystick_keywords):
            try:
                device.open()
                print(f"已连接到疑似摇杆设备：{device.product_name}")
                print(f"  Vendor ID: {device.vendor_id}")
                print(f"  Product ID: {device.product_id}")
                print(f"  Manufacturer: {device.vendor_name}")
                return device
            except Exception as e:
                print(f"无法连接到设备 {device.product_name}: {e}")
                continue
    
    print("未找到摇杆设备")
    return None

def connect_device(vendor_id, product_id):
    """连接并打开指定的HID设备"""
    filter = hid.HidDeviceFilter(vendor_id=vendor_id, product_id=product_id)
    devices = filter.get_devices()
    if devices:
        device = devices[0]
        device.open()
        print(f"已连接到设备：Vendor ID={vendor_id}, Product ID={product_id}")
        return device
    else:
        print("未找到设备")
        return None

# def main():
#     # list_devices()
#     # 替换为实际的Vendor ID和Product ID
#     #       Vendor ID: 1356
#     #   Product ID: 98
#     #   Manufacturer: China Longcctv
#     #   Serial Number:
#     #   Device Path: \\?\hid#vid_054c&pid_0062#6&6303015&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}
#     vendor_id = 1356
#     product_id = 98
#     device = connect_device(vendor_id, product_id)
#     if device:
#         device.close()
#         print("设备已断开连接")


import pywinusb.hid as hid
import time
import tkinter as tk
from tkinter import ttk
import threading

class JoystickVisualizer:
    def __init__(self, root):
        self.root = root
        self.root.title("摇杆可视化面板")
        self.root.geometry("800x600")
        
        # 数据存储
        self.current_data = {
            'x_axis': 0,
            'y_axis': 0,
            'rx_axis': 0,
            'ry_axis': 0,
            'buttons': {}
        }
        
        # 校准数据 - 动态学习系统
        self.calibration = {
            'x_center': 0x0800,
            'y_center': 0x0800,
            'rx_center': 0x0800,
            'ry_center': 0x0800,
            'x_min': 0x0800,  # 初始设为中心值
            'x_max': 0x0800,  # 初始设为中心值
            'y_min': 0x0800,  # 初始设为中心值
            'y_max': 0x0800,  # 初始设为中心值
            'rx_min': 0x0800,  # 初始设为中心值
            'rx_max': 0x0800,  # 初始设为中心值
            'ry_min': 0x0800,  # 初始设为中心值
            'ry_max': 0x0800   # 初始设为中心值
        }
        
        # 反向校准偏移量
        self.offset = {
            'x': 0,
            'y': 0,
            'rx': 0,
            'ry': 0
        }
        
        self.first_data_received = False
        
        # 校准状态管理
        self.calibration_mode = False
        self.calibration_step = 0
        self.calibration_data = {}
        
        self.device = None
        self.create_widgets()
        
    def create_widgets(self):
        # 主框架
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 创建摇杆显示区域
        joystick_frame = ttk.Frame(main_frame)
        joystick_frame.pack(fill=tk.BOTH, expand=True)
        
        # 左侧主轴显示
        left_frame = ttk.LabelFrame(joystick_frame, text="主轴 (X, Y)")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        self.main_canvas = tk.Canvas(left_frame, width=200, height=200, bg='white')
        self.main_canvas.pack(pady=10)
        
        # 绘制主轴边界框
        self.main_canvas.create_rectangle(5, 5, 195, 195, outline='lightgray', width=1)
        # 绘制主轴中心十字线
        self.main_canvas.create_line(100, 5, 100, 195, fill='lightgray', width=1)
        self.main_canvas.create_line(5, 100, 195, 100, fill='lightgray', width=1)
        self.main_canvas.create_oval(95, 95, 105, 105, fill='lightgray', outline='gray')
        
        # 主轴位置点 (初始在中心位置)
        self.main_dot = self.main_canvas.create_oval(95, 95, 105, 105, fill='red', outline='darkred', width=2)
        
        # 主轴数值显示 (显示中心值)
        self.main_label = ttk.Label(left_frame, text="X: 0.000, Y: 0.000")
        self.main_label.pack()
        
        # 右侧副轴显示
        right_frame = ttk.LabelFrame(joystick_frame, text="副轴 (RX, RY)")
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)
        
        self.sub_canvas = tk.Canvas(right_frame, width=200, height=200, bg='white')
        self.sub_canvas.pack(pady=10)
        
        # 绘制副轴边界框
        self.sub_canvas.create_rectangle(5, 5, 195, 195, outline='lightgray', width=1)
        # 绘制副轴中心十字线
        self.sub_canvas.create_line(100, 5, 100, 195, fill='lightgray', width=1)
        self.sub_canvas.create_line(5, 100, 195, 100, fill='lightgray', width=1)
        self.sub_canvas.create_oval(95, 95, 105, 105, fill='lightgray', outline='gray')
        
        # 副轴位置点 (初始在中心位置)
        self.sub_dot = self.sub_canvas.create_oval(95, 95, 105, 105, fill='blue', outline='darkblue', width=2)
        
        # 副轴数值显示 (显示中心值)
        self.sub_label = ttk.Label(right_frame, text="RX: 0.000, RY: 0.000")
        self.sub_label.pack()
        
        # 按钮显示区域
        self.button_frame = ttk.LabelFrame(main_frame, text="按钮状态")
        self.button_frame.pack(fill=tk.X, pady=10)
        
        # 创建按钮显示
        self.button_widgets = {}
        button_names = ['IN1', '按钮7', '按钮6', '按钮5', '按钮4', '按钮3', '按钮2', '按钮1',
                       'IN9', 'IN8', 'IN7', 'IN6', 'IN5', 'IN4', 'IN3', 'IN2']
        
        for i, name in enumerate(button_names):
            row = i // 8
            col = i % 8
            btn = tk.Label(self.button_frame, text=name, width=8, height=2, 
                          bg='lightgray', relief='raised', font=('Arial', 8))
            btn.grid(row=row, column=col, padx=2, pady=2)
            self.button_widgets[name] = btn
        
        # 连接按钮
        connect_frame = ttk.Frame(main_frame)
        connect_frame.pack(fill=tk.X, pady=5)
        
        self.connect_btn = ttk.Button(connect_frame, text="连接摇杆", command=self.connect_joystick)
        self.connect_btn.pack(side=tk.LEFT)
        
        self.select_device_btn = ttk.Button(connect_frame, text="选择设备", command=self.show_device_selector)
        self.select_device_btn.pack(side=tk.LEFT, padx=5)
        
        self.disconnect_btn = ttk.Button(connect_frame, text="断开连接", command=self.disconnect_joystick)
        self.disconnect_btn.pack(side=tk.LEFT, padx=5)
        
        self.status_label = ttk.Label(connect_frame, text="状态: 未连接")
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # 校准和调试按钮
        self.start_calibration_btn = ttk.Button(connect_frame, text="开始校准", command=self.start_calibration)
        self.start_calibration_btn.pack(side=tk.LEFT, padx=5)
        
        self.calibrate_btn = ttk.Button(connect_frame, text="重新校准", command=self.recalibrate_center)
        self.calibrate_btn.pack(side=tk.LEFT, padx=5)
        
        self.debug_btn = ttk.Button(connect_frame, text="调试模式", command=self.toggle_debug)
        self.debug_btn.pack(side=tk.LEFT, padx=5)
        
        self.list_devices_btn = ttk.Button(connect_frame, text="列出设备", command=self.list_all_devices)
        self.list_devices_btn.pack(side=tk.LEFT, padx=5)
        
        # 校准指导区域
        self.calibration_frame = ttk.LabelFrame(main_frame, text="校准指导")
        self.calibration_frame.pack(fill=tk.X, pady=5)
        self.calibration_frame.pack_forget()  # 初始隐藏
        
        self.calibration_instruction = ttk.Label(self.calibration_frame, text="", font=('Arial', 12, 'bold'))
        self.calibration_instruction.pack(pady=10)
        
        self.calibration_progress = ttk.Label(self.calibration_frame, text="", font=('Arial', 10))
        self.calibration_progress.pack(pady=5)
        
        # 校准按钮区域
        calibration_btn_frame = ttk.Frame(self.calibration_frame)
        calibration_btn_frame.pack(pady=10)
        
        self.next_step_btn = ttk.Button(calibration_btn_frame, text="下一步", command=self.next_calibration_step)
        self.next_step_btn.pack(side=tk.LEFT, padx=5)
        
        self.finish_calibration_btn = ttk.Button(calibration_btn_frame, text="完成校准", command=self.finish_calibration)
        self.finish_calibration_btn.pack(side=tk.LEFT, padx=5)
        
        self.cancel_calibration_btn = ttk.Button(calibration_btn_frame, text="取消校准", command=self.cancel_calibration)
        self.cancel_calibration_btn.pack(side=tk.LEFT, padx=5)
        
        # 原始数据显示
        self.debug_frame = ttk.LabelFrame(main_frame, text="原始数据")
        self.debug_frame.pack(fill=tk.X, pady=5)
        
        self.raw_data_label = ttk.Label(self.debug_frame, text="原始数据: 未连接", font=('Courier', 10))
        self.raw_data_label.pack(padx=5, pady=5)
        
        # 偏移量显示
        self.offset_label = ttk.Label(self.debug_frame, text="偏移量: 未校准", font=('Courier', 10))
        self.offset_label.pack(padx=5, pady=2)
        
        # 设备信息显示
        self.device_info_label = ttk.Label(self.debug_frame, text="设备信息: 未连接", font=('Courier', 10))
        self.device_info_label.pack(padx=5, pady=2)
        
        self.debug_mode = False
        
        # 自动连接第一个可用设备
        self.connect_joystick()
        
        # 如果自动连接失败，启用调试模式以便查看设备信息
        if not self.device:
            self.debug_mode = True
            self.debug_frame.pack(fill=tk.X, pady=5, before=self.button_frame)
            self.debug_btn.config(text="关闭调试")
        else:
            # 连接成功后，提示用户进行校准
            self.status_label.config(text="状态: 已连接，请点击'开始校准'进行校准")
    
    def show_device_selector(self):
        """显示设备选择窗口"""
        # 创建设备选择窗口
        device_window = tk.Toplevel(self.root)
        device_window.title("选择摇杆设备")
        device_window.geometry("600x400")
        device_window.transient(self.root)
        device_window.grab_set()
        
        # 获取所有设备
        all_devices = hid.HidDeviceFilter().get_devices()
        
        # 创建设备列表
        tk.Label(device_window, text="请选择正确的摇杆设备：", font=('Arial', 12)).pack(pady=10)
        
        # 创建列表框
        listbox_frame = tk.Frame(device_window)
        listbox_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 创建滚动条
        scrollbar = tk.Scrollbar(listbox_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 创建列表框
        device_listbox = tk.Listbox(listbox_frame, yscrollcommand=scrollbar.set, font=('Courier', 10))
        device_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=device_listbox.yview)
        
        # 填充设备列表
        device_list = []
        for i, device in enumerate(all_devices):
            device_info = f"{i+1:2d}. {device.product_name or 'Unknown'} - VID:{device.vendor_id:04X} PID:{device.product_id:04X}"
            if device.vendor_name:
                device_info += f" ({device.vendor_name})"
            device_listbox.insert(tk.END, device_info)
            device_list.append(device)
        
        # 按钮框架
        button_frame = tk.Frame(device_window)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        def connect_selected():
            selection = device_listbox.curselection()
            if selection:
                selected_device = device_list[selection[0]]
                device_window.destroy()
                self.connect_specific_device(selected_device)
        
        def cancel_selection():
            device_window.destroy()
        
        tk.Button(button_frame, text="连接选中设备", command=connect_selected).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="取消", command=cancel_selection).pack(side=tk.LEFT, padx=5)
        
        # 提示信息
        info_label = tk.Label(device_window, text="提示：摇杆设备通常包含 'joystick'、'gamepad'、'controller' 等关键词", 
                             font=('Arial', 9), fg='gray')
        info_label.pack(pady=5)
    
    def connect_specific_device(self, device):
        """连接指定的设备"""
        try:
            # 先断开现有连接
            if self.device:
                self.disconnect_joystick()
            
            device.open()
            self.device = device
            
            # 重置校准状态
            self.first_data_received = False
            self.offset = {'x': 0, 'y': 0, 'rx': 0, 'ry': 0}
            
            self.device.set_raw_data_handler(self.read_data)
            self.status_label.config(text=f"状态: 已连接到 {device.product_name or 'Unknown'}，请点击'开始校准'进行校准")
            self.connect_btn.config(state='disabled')
            self.select_device_btn.config(state='disabled')
            self.disconnect_btn.config(state='normal')
            
            # 更新设备信息显示
            device_info = f"设备: {device.product_name or 'Unknown'} VID:{device.vendor_id:04X} PID:{device.product_id:04X}"
            self.device_info_label.config(text=device_info)
            
            print(f"已手动连接到设备：{device.product_name}")
            print(f"  Vendor ID: {device.vendor_id}")
            print(f"  Product ID: {device.product_id}")
            print(f"  Manufacturer: {device.vendor_name}")
            
        except Exception as e:
            self.status_label.config(text=f"连接失败: {str(e)}")
            print(f"连接设备失败: {e}")
        
    def normalize_axis_value(self, value, axis_name):
        """
        将轴值归一化到-1到1范围，确保中心值映射到0
        校准后的行为：
        - 中心位置 -> 0
        - 最小值 -> -1
        - 最大值 -> +1
        - 主轴可以移动到任意区域
        - 副轴RX可以水平移动，RY可以垂直移动
        """
        min_val = self.calibration[f'{axis_name}_min']
        max_val = self.calibration[f'{axis_name}_max']
        center_val = self.calibration[f'{axis_name}_center']
        
        # 如果校准数据无效，返回中心值0
        if max_val <= min_val:
            return 0
        
        # 确保中心值正确映射到0
        if abs(value - center_val) < 1:  # 中心位置容差
            return 0
        
        # 以中心值为基准进行双向映射到-1到1
        if value < center_val:
            # 从min到center映射到-1到0
            if center_val > min_val:
                # 线性映射: (value - min_val) / (center_val - min_val) * (-1) + 0
                normalized = -1 * (center_val - value) / (center_val - min_val)
            else:
                normalized = 0
        else:
            # 从center到max映射到0到1
            if max_val > center_val:
                # 线性映射: (value - center_val) / (max_val - center_val) * 1 + 0
                normalized = (value - center_val) / (max_val - center_val)
            else:
                normalized = 0
        
        # 对主轴Y轴进行反转，使得上方为正，下方为负（符合屏幕坐标习惯）
        # 副轴RY轴不进行反转，保持原始方向
        if axis_name == 'y':
            normalized = -normalized
        
        # 严格限制在-1到1范围内，确保完整的移动范围
        return max(-1.0, min(1.0, normalized))
        
    def update_position(self, x, y, rx, ry):
        """
        更新摇杆位置显示
        - 主轴(红点)：可以移动到任意区域，显示完整的X,Y范围
        - 副轴(蓝点)：RX固定在中心，只能在Y轴滑动（硬件限制）
        """
        # 归一化轴值到-1到1范围，确保中心为(0,0)
        norm_x = self.normalize_axis_value(x, 'x')
        norm_y = self.normalize_axis_value(y, 'y')  
        norm_rx = self.normalize_axis_value(rx, 'rx')
        norm_ry = self.normalize_axis_value(ry, 'ry')
        
        # 计算画布位置 (5-195像素范围，使用完整的可用空间)
        canvas_center = 100  # 画布中心位置 (200/2)
        canvas_radius = 95   # 从中心到边界的距离 (100-5)
        
        # 主轴位置计算：可以移动到任意区域
        # 使用完整的-1到1范围映射到整个画布区域
        main_x = canvas_center + norm_x * canvas_radius
        main_y = canvas_center - norm_y * canvas_radius  # Y轴反转以符合屏幕坐标
        
        # 副轴位置计算：考虑硬件限制
        # 硬件限制：副轴无法横向移动，RX轴固定在中心位置
        # 只有RY轴可以垂直滑动
        sub_x = canvas_center  # RX固定在中心，不随norm_rx变化
        sub_y = canvas_center + norm_ry * canvas_radius  # 只有RY可以垂直移动，不取反
        
        # 确保位置在画布边界内
        main_x = max(5, min(195, main_x))
        main_y = max(5, min(195, main_y))
        sub_x = max(5, min(195, sub_x))
        sub_y = max(5, min(195, sub_y))
        
        # 更新主轴位置（红点）
        self.main_canvas.coords(self.main_dot, main_x-5, main_y-5, main_x+5, main_y+5)
        self.main_label.config(text=f"X: {norm_x:.3f}, Y: {norm_y:.3f}")
        
        # 更新副轴位置（蓝点）
        self.sub_canvas.coords(self.sub_dot, sub_x-5, sub_y-5, sub_x+5, sub_y+5)
        # 显示RX固定为0（硬件限制），只显示RY的实际值
        self.sub_label.config(text=f"RX: 0.000 (固定), RY: {norm_ry:.3f}")
        
    def update_buttons(self, button_states):
        """更新按钮状态显示"""
        for name, pressed in button_states.items():
            if name in self.button_widgets:
                if pressed:
                    self.button_widgets[name].config(bg='green', relief='sunken')
                else:
                    self.button_widgets[name].config(bg='lightgray', relief='raised')
                    
    def connect_joystick(self):
        """连接摇杆设备（自动连接第一个可用设备）"""
        try:
            self.device = connect_device_auto()
            if self.device:
                # 重置校准状态
                self.first_data_received = False
                self.offset = {'x': 0, 'y': 0, 'rx': 0, 'ry': 0}
                
                self.device.set_raw_data_handler(self.read_data)
                self.status_label.config(text="状态: 已连接，请点击'开始校准'进行校准")
                self.connect_btn.config(state='disabled')
                self.select_device_btn.config(state='disabled')
                self.disconnect_btn.config(state='normal')
                
                # 更新设备信息显示
                device_info = f"设备: {self.device.product_name or 'Unknown'} VID:{self.device.vendor_id:04X} PID:{self.device.product_id:04X}"
                self.device_info_label.config(text=device_info)
            else:
                self.status_label.config(text="状态: 未找到摇杆设备，请点击'选择设备'手动选择")
        except Exception as e:
            self.status_label.config(text=f"连接失败: {str(e)}")
            
    def disconnect_joystick(self):
        """断开摇杆连接"""
        if self.device:
            self.device.close()
            self.device = None
            
            # 重置校准状态
            self.first_data_received = False
            self.offset = {'x': 0, 'y': 0, 'rx': 0, 'ry': 0}
            
            self.status_label.config(text="状态: 已断开")
            self.offset_label.config(text="偏移量: 未校准")
            self.raw_data_label.config(text="原始数据: 未连接")
            self.device_info_label.config(text="设备信息: 未连接")
            self.connect_btn.config(state='normal')
            self.select_device_btn.config(state='normal')
            self.disconnect_btn.config(state='disabled')
            
    def read_data(self, data):
        """数据读取回调函数"""
        parsed_data = parse_data(data)
        if parsed_data:
            # 在校准模式下，直接更新GUI用于显示当前位置
            if self.calibration_mode:
                self.root.after(0, self.update_gui, parsed_data)
            else:
                # 正常模式：应用偏移量补偿（如果需要）
                if self.first_data_received:
                    corrected_data = self.apply_offset_correction(parsed_data)
                    self.root.after(0, self.update_gui, corrected_data)
                else:
                    # 如果还没有完成校准，直接显示原始数据
                    self.root.after(0, self.update_gui, parsed_data)
    
    def calculate_offset(self, data):
        """计算偏移量，让当前位置成为中心（仅用于重新校准功能）"""
        # 计算偏移量
        self.offset['x'] = data['x_axis'] - self.calibration['x_center']
        self.offset['y'] = data['y_axis'] - self.calibration['y_center']
        self.offset['rx'] = data['rx_axis'] - self.calibration['rx_center']
        self.offset['ry'] = data['ry_axis'] - self.calibration['ry_center']
        
        # 更新偏移量显示
        self.root.after(0, lambda: self.offset_label.config(
            text=f"偏移量: X:{self.offset['x']:+4d} Y:{self.offset['y']:+4d} RX:{self.offset['rx']:+4d} RY:{self.offset['ry']:+4d}"
        ))
    
    def apply_offset_correction(self, data):
        """应用偏移量补偿"""
        corrected_data = data.copy()
        corrected_data['x_axis'] = data['x_axis'] - self.offset['x']
        corrected_data['y_axis'] = data['y_axis'] - self.offset['y']
        corrected_data['rx_axis'] = data['rx_axis'] - self.offset['rx']
        corrected_data['ry_axis'] = data['ry_axis'] - self.offset['ry']
        return corrected_data
            
    def recalibrate_center(self):
        """重新校准中心位置 - 基于当前原始数据重新计算偏移量"""
        if self.device and hasattr(self, 'current_data') and self.current_data:
            # 需要获取当前的原始数据，而不是补偿后的数据
            # 通过reverse计算得到原始数据
            raw_x = self.current_data['x_axis'] + self.offset['x']
            raw_y = self.current_data['y_axis'] + self.offset['y']
            raw_rx = self.current_data['rx_axis'] + self.offset['rx']
            raw_ry = self.current_data['ry_axis'] + self.offset['ry']
            
            # 重新计算偏移量
            self.offset['x'] = raw_x - self.calibration['x_center']
            self.offset['y'] = raw_y - self.calibration['y_center']
            self.offset['rx'] = raw_rx - self.calibration['rx_center']
            self.offset['ry'] = raw_ry - self.calibration['ry_center']
            
            # 更新偏移量显示
            self.offset_label.config(
                text=f"偏移量: X:{self.offset['x']:+4d} Y:{self.offset['y']:+4d} RX:{self.offset['rx']:+4d} RY:{self.offset['ry']:+4d}"
            )
            
            self.status_label.config(text="状态: 已重新校准")
    
    def toggle_debug(self):
        """切换调试模式"""
        self.debug_mode = not self.debug_mode
        if self.debug_mode:
            self.debug_frame.pack(fill=tk.X, pady=5, before=self.button_frame)
            self.debug_btn.config(text="关闭调试")
        else:
            self.debug_frame.pack_forget()
            self.debug_btn.config(text="调试模式")
    
    def list_all_devices(self):
        """列出所有HID设备到控制台"""
        print("\n=== 所有HID设备列表 ===")
        all_devices = hid.HidDeviceFilter().get_devices()
        if not all_devices:
            print("未找到任何HID设备")
            return
        
        for i, device in enumerate(all_devices, 1):
            print(f"{i:2d}. 设备名称: {device.product_name or 'Unknown'}")
            print(f"    制造商: {device.vendor_name or 'Unknown'}")
            print(f"    Vendor ID: {device.vendor_id:04X} ({device.vendor_id})")
            print(f"    Product ID: {device.product_id:04X} ({device.product_id})")
            print(f"    设备路径: {device.device_path}")
            print("")
        
        print(f"总计找到 {len(all_devices)} 个HID设备")
        print("=== 设备列表结束 ===\n")
    
    def start_calibration(self):
        """开始校准流程"""
        if not self.device:
            self.status_label.config(text="请先连接摇杆设备")
            return
        
        self.calibration_mode = True
        self.calibration_step = 0
        self.calibration_data = {
            'x_values': [],
            'y_values': [],
            'rx_values': [],
            'ry_values': []
        }
        
        # 显示校准指导区域
        self.calibration_frame.pack(fill=tk.X, pady=5, after=self.status_label.master)
        
        # 校准模式下自动显示调试信息
        if not self.debug_mode:
            self.debug_frame.pack(fill=tk.X, pady=5, before=self.button_frame)
        
        # 初始化校准范围为中心值
        for axis in ['x', 'y', 'rx', 'ry']:
            self.calibration[f'{axis}_min'] = self.calibration[f'{axis}_center']
            self.calibration[f'{axis}_max'] = self.calibration[f'{axis}_center']
        
        # 显示第一步指导
        self.update_calibration_instruction()
        
        # 禁用其他按钮
        self.start_calibration_btn.config(state='disabled')
        self.calibrate_btn.config(state='disabled')
        self.connect_btn.config(state='disabled')
        self.disconnect_btn.config(state='disabled')
        
        self.status_label.config(text="状态: 校准模式")
    
    def update_calibration_instruction(self):
        """更新校准指导信息"""
        instructions = [
            "请将摇杆置于中心位置，然后点击'下一步'",
            "请将主轴(红点)向左推到极限位置，然后点击'下一步'",
            "请将主轴(红点)向右推到极限位置，然后点击'下一步'",
            "请将主轴(红点)向上推到极限位置，然后点击'下一步'",
            "请将主轴(红点)向下推到极限位置，然后点击'下一步'",
            "请将副轴(蓝点)向左推到极限位置，然后点击'下一步'",
            "请将副轴(蓝点)向右推到极限位置，然后点击'下一步'",
            "请将副轴(蓝点)向上推到极限位置，然后点击'下一步'",
            "请将副轴(蓝点)向下推到极限位置，然后点击'完成校准'"
        ]
        
        if self.calibration_step < len(instructions):
            self.calibration_instruction.config(text=instructions[self.calibration_step])
            self.calibration_progress.config(text=f"校准进度: {self.calibration_step + 1}/{len(instructions)}")
            
            # 在最后一步显示完成按钮
            if self.calibration_step == len(instructions) - 1:
                self.next_step_btn.config(state='disabled')
                self.finish_calibration_btn.config(state='normal')
            else:
                self.next_step_btn.config(state='normal')
                self.finish_calibration_btn.config(state='disabled')
    
    def next_calibration_step(self):
        """进入下一个校准步骤"""
        if not self.calibration_mode or not self.current_data:
            return
        
        # 记录当前位置数据
        data = self.current_data
        step_names = ['center', 'x_left', 'x_right', 'y_up', 'y_down', 'rx_left', 'rx_right', 'ry_up', 'ry_down']
        
        if self.calibration_step < len(step_names):
            step_name = step_names[self.calibration_step]
            
            if step_name == 'center':
                # 记录中心位置
                self.calibration['x_center'] = data['x_axis']
                self.calibration['y_center'] = data['y_axis']
                self.calibration['rx_center'] = data['rx_axis']
                self.calibration['ry_center'] = data['ry_axis']
            elif step_name == 'x_left':
                self.calibration['x_min'] = data['x_axis']
            elif step_name == 'x_right':
                self.calibration['x_max'] = data['x_axis']
            elif step_name == 'y_up':
                self.calibration['y_max'] = data['y_axis']
            elif step_name == 'y_down':
                self.calibration['y_min'] = data['y_axis']
            elif step_name == 'rx_left':
                self.calibration['rx_min'] = data['rx_axis']
            elif step_name == 'rx_right':
                self.calibration['rx_max'] = data['rx_axis']
            elif step_name == 'ry_up':
                self.calibration['ry_max'] = data['ry_axis']
            elif step_name == 'ry_down':
                self.calibration['ry_min'] = data['ry_axis']
        
        self.calibration_step += 1
        self.update_calibration_instruction()
    
    def finish_calibration(self):
        """完成校准"""
        # 验证校准数据
        valid = True
        for axis in ['x', 'y', 'rx', 'ry']:
            if self.calibration[f'{axis}_min'] >= self.calibration[f'{axis}_max']:
                valid = False
                break
        
        if not valid:
            self.status_label.config(text="校准数据无效，请重新校准")
            return
        
        # 完成校准
        self.calibration_mode = False
        self.calibration_step = 0
        self.first_data_received = True
        
        # 校准完成后，确保中心值为(0,0)
        # 偏移量清零，校准数据已经确定了正确的中心、最小值和最大值
        self.offset = {'x': 0, 'y': 0, 'rx': 0, 'ry': 0}
        
        # 验证校准数据确保中心值可以正确映射到(0,0)
        # 确保范围对称，这样中心值在normalize时能正确映射到0
        for axis in ['x', 'y', 'rx', 'ry']:
            center = self.calibration[f'{axis}_center']
            min_val = self.calibration[f'{axis}_min']
            max_val = self.calibration[f'{axis}_max']
            
            # 验证中心值是否在范围内
            if center < min_val or center > max_val:
                print(f"警告: {axis}轴中心值({center})超出范围({min_val}-{max_val})")
        
        # 隐藏校准指导区域
        self.calibration_frame.pack_forget()
        
        # 如果之前没有开启调试模式，现在隐藏调试信息
        if not self.debug_mode:
            self.debug_frame.pack_forget()
        
        # 重新启用按钮
        self.start_calibration_btn.config(state='normal')
        self.calibrate_btn.config(state='normal')
        self.disconnect_btn.config(state='normal')
        
        self.status_label.config(text="状态: 校准完成，摇杆已就绪，中心值为(0,0)")
        
        # 显示校准结果
        print("校准完成！摇杆现在可以正常使用了，中心值为(0,0)。")
        print(f"X轴范围: {self.calibration['x_min']} - {self.calibration['x_max']} (中心: {self.calibration['x_center']})")
        print(f"Y轴范围: {self.calibration['y_min']} - {self.calibration['y_max']} (中心: {self.calibration['y_center']})")
        print(f"RX轴范围: {self.calibration['rx_min']} - {self.calibration['rx_max']} (中心: {self.calibration['rx_center']})")
        print(f"RY轴范围: {self.calibration['ry_min']} - {self.calibration['ry_max']} (中心: {self.calibration['ry_center']})")
        print("现在移动摇杆应该可以看到界面中的红点和蓝点相应移动。")
    
    def cancel_calibration(self):
        """取消校准"""
        self.calibration_mode = False
        self.calibration_step = 0
        
        # 隐藏校准指导区域
        self.calibration_frame.pack_forget()
        
        # 如果之前没有开启调试模式，现在隐藏调试信息
        if not self.debug_mode:
            self.debug_frame.pack_forget()
        
        # 重新启用按钮
        self.start_calibration_btn.config(state='normal')
        self.calibrate_btn.config(state='normal')
        self.disconnect_btn.config(state='normal')
        
        self.status_label.config(text="状态: 校准已取消")
    
    def update_gui(self, data):
        """在主线程中更新GUI"""
        self.current_data = data
        
        # 更新调试信息显示
        if self.debug_mode or self.calibration_mode:
            if self.calibration_mode:
                debug_text = f"校准数据: X:{data['x_axis']:4d} Y:{data['y_axis']:4d} RX:{data['rx_axis']:4d} RY:{data['ry_axis']:4d}"
            elif self.first_data_received:
                debug_text = f"补偿后: X:{data['x_axis']:4d} Y:{data['y_axis']:4d} RX:{data['rx_axis']:4d} RY:{data['ry_axis']:4d}"
            else:
                debug_text = f"原始数据: X:{data['x_axis']:4d} Y:{data['y_axis']:4d} RX:{data['rx_axis']:4d} RY:{data['ry_axis']:4d}"
            self.raw_data_label.config(text=debug_text)
        
        # 校准模式下显示原始位置，正常模式下显示归一化位置
        if self.calibration_mode:
            # 校准模式：显示原始数据，不进行归一化
            canvas_center = 100
            main_x = canvas_center + (data['x_axis'] - self.calibration['x_center']) / 10
            main_y = canvas_center + (data['y_axis'] - self.calibration['y_center']) / 10
            sub_x = canvas_center + (data['rx_axis'] - self.calibration['rx_center']) / 10
            sub_y = canvas_center + (data['ry_axis'] - self.calibration['ry_center']) / 10
            
            # 限制在画布范围内
            main_x = max(5, min(195, main_x))
            main_y = max(5, min(195, main_y))
            sub_x = max(5, min(195, sub_x))
            sub_y = max(5, min(195, sub_y))
            
            self.main_canvas.coords(self.main_dot, main_x-5, main_y-5, main_x+5, main_y+5)
            self.sub_canvas.coords(self.sub_dot, sub_x-5, sub_y-5, sub_x+5, sub_y+5)
            self.main_label.config(text=f"X: {data['x_axis']}, Y: {data['y_axis']}")
            self.sub_label.config(text=f"RX: {data['rx_axis']}, RY: {data['ry_axis']}")
            
        elif self.first_data_received:
            # 正常模式：使用归一化数据
            self.update_position(data['x_axis'], data['y_axis'], data['rx_axis'], data['ry_axis'])
        else:
            # 如果还没有完成校准，显示原始数据但不进行归一化
            canvas_center = 100
            main_x = canvas_center
            main_y = canvas_center
            sub_x = canvas_center
            sub_y = canvas_center
            
            self.main_canvas.coords(self.main_dot, main_x-5, main_y-5, main_x+5, main_y+5)
            self.sub_canvas.coords(self.sub_dot, sub_x-5, sub_y-5, sub_x+5, sub_y+5)
            self.main_label.config(text=f"X: {data['x_axis']}, Y: {data['y_axis']}")
            self.sub_label.config(text=f"RX: {data['rx_axis']}, RY: {data['ry_axis']}")
        
        self.update_buttons(data['buttons'])

def parse_data(data):
    """解析操作杆数据，根据文档的字节分布结构解析"""
    # X轴数据，第1字节是低位，第2字节是高位
    x_axis = int.from_bytes(data[1:3], byteorder='little')
    # Y轴数据，第3字节是低位，第4字节是高位
    y_axis = int.from_bytes(data[3:5], byteorder='little')
    # RX轴数据，第5字节是低位，第6字节是高位
    rx_axis = int.from_bytes(data[5:7], byteorder='little')
    # RY轴数据，第7字节是低位，第8字节是高位
    ry_axis = int.from_bytes(data[7:9], byteorder='little')
    
    # 按钮状态，第9字节和第10字节
    bb1 = data[9]
    bb2 = data[10]
    
    # 按钮状态解析为布尔值（True表示按下，False表示未按下）
    button_states = {
        'IN1': bool(bb1 & 0x80),
        '按钮7': bool(bb1 & 0x40),
        '按钮6': bool(bb1 & 0x20),
        '按钮5': bool(bb1 & 0x10),
        '按钮4': bool(bb1 & 0x08),
        '按钮3': bool(bb1 & 0x04),
        '按钮2': bool(bb1 & 0x02),
        '按钮1': bool(bb1 & 0x01),
        'IN9': bool(bb2 & 0x80),
        'IN8': bool(bb2 & 0x40),
        'IN7': bool(bb2 & 0x20),
        'IN6': bool(bb2 & 0x10),
        'IN5': bool(bb2 & 0x08),
        'IN4': bool(bb2 & 0x04),
        'IN3': bool(bb2 & 0x02),
        'IN2': bool(bb2 & 0x01),
    }

    return {
        'x_axis': x_axis,
        'y_axis': y_axis,
        'rx_axis': rx_axis,
        'ry_axis': ry_axis,
        'buttons': button_states
    }

def read_data(data):
    """数据读取回调函数"""
    parse_data(data)

def main():
    # 使用你的设备的Vendor ID和Product ID
    vendor_id = 1356
    product_id = 98

    # 连接到设备
    device = connect_device(vendor_id, product_id)
    if device:
        # 设置数据读取的回调函数
        device.set_raw_data_handler(read_data)
        
        print("正在读取数据，按Ctrl+C停止...")
        try:
            while True:
                pass  # 保持程序运行，持续读取数据
        except KeyboardInterrupt:
            print("停止读取数据")
        finally:
            device.close()
            print("设备已断开连接")

def start_gui():
    """启动GUI可视化界面"""
    root = tk.Tk()
    app = JoystickVisualizer(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.disconnect_joystick(), root.destroy()))
    root.mainloop()

if __name__ == "__main__":
    # 启动GUI版本
    start_gui()
    
    # 如果需要使用命令行版本，请注释掉上面的代码，取消注释下面的代码
    # main()

