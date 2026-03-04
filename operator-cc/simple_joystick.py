import pywinusb.hid as hid
import time
import tkinter as tk
from tkinter import ttk
import threading
import json
import os
from datetime import datetime

class SimpleJoystickController:
    """简化的操纵杆控制器"""
    def __init__(self):
        # 当前数据
        self.current_data = {
            'main_x': 0.0,      # 主轴X坐标 (-1 到 1)
            'main_y': 0.0,      # 主轴Y坐标 (-1 到 1)
            'sub_y': 0.0,       # 副轴Y坐标 (-1 到 1)
            'button1': False,   # 按钮1状态
            'button2': False,   # 按钮2状态
            'button7': False    # 按钮7状态
        }
        
        # 偏移量（用于将当前位置设为中心）
        self.offset = {
            'x': 0,
            'y': 0,
            'ry': 0
        }
        
        # 记录实际的中心值（连接时会被第一次数据覆盖）
        self.center_values = {
            'x': 0x8000,  # 16位设备默认中心
            'y': 0x8000,
            'ry': 0x8000
        }
        
        # 轴范围边界值（通过边界检测确定实际硬件范围）
        # 默认使用 16 位全范围，连接后应通过边界检测校准
        self.axis_boundaries = {
            'x_min': 0x0000,
            'x_max': 0xFFFF,
            'y_min': 0x0000,
            'y_max': 0xFFFF,
            'ry_min': 0x0000,
            'ry_max': 0xFFFF,
        }
        
        # 边界检测配置文件路径
        self.boundary_config_file = "joystick_calibration.json"
        
        # 设备连接
        self.device = None
        
        # 数据回调函数
        self.data_callback = None
        
        # 保存最新的原始数据
        self.last_raw_data = None
        self.last_raw_bytes = None  # 原始 HID 字节
        
        # 初始化标志
        self.first_data_received = False
        
        # 边界检测模式
        self.boundary_detection_mode = False
        self.boundary_sample_count = 0
        
        # 指数平滑滤波（EMA），用于抑制 ADC 噪声
        self.smoothing_factor = 0.15  # 新值权重，越小越平滑，越大响应越快
        self.smoothed_values = {'x': None, 'y': None, 'ry': None}
        
        # 迟滞死区状态：避免在死区边界来回振荡
        self.in_dead_zone = {'x': True, 'y': True, 'ry': True}
        
        # 启动时加载校准配置
        self.load_calibration_config()
        
    def connect_joystick(self, device_index=0):
        """连接操纵杆设备，device_index 指定连接第几个匹配的接口"""
        try:
            all_devices = hid.HidDeviceFilter().get_devices()
            
            # 收集所有可能的设备接口
            candidates = []
            known_devices = [(1356, 98)]
            for vendor_id, product_id in known_devices:
                for device in all_devices:
                    if device.vendor_id == vendor_id and device.product_id == product_id:
                        candidates.append(device)
            
            if not candidates:
                joystick_keywords = ['joystick', 'gamepad', 'controller', 'stick', '摇杆', 'longcctv']
                for device in all_devices:
                    device_name = (device.product_name or "").lower()
                    manufacturer = (device.vendor_name or "").lower()
                    if any(kw in device_name or kw in manufacturer for kw in joystick_keywords):
                        candidates.append(device)
            
            self.available_devices = candidates
            self.current_device_index = device_index
            
            if not candidates:
                print("未找到操纵杆设备")
                return False
            
            # 连接指定索引的设备
            idx = device_index % len(candidates)
            device = candidates[idx]
            try:
                device.open()
                self.device = device
                self._reset_state()
                device.set_raw_data_handler(self._process_raw_data)
                print(f"已连接到接口 {idx+1}/{len(candidates)}: {device.product_name} (path: ...{str(device.device_path)[-30:]})")
                return True
            except Exception as e:
                print(f"连接失败: {e}")
                return False
            
        except Exception as e:
            print(f"连接操纵杆失败: {e}")
            return False
    
    def _reset_state(self):
        """重置内部状态，切换设备时调用"""
        self.first_data_received = False
        self.last_raw_data = None
        self.last_raw_bytes = None
        self.smoothed_values = {'x': None, 'y': None, 'ry': None}
        self.in_dead_zone = {'x': True, 'y': True, 'ry': True}
        self.boundary_detection_mode = False
        self.boundary_sample_count = 0
    
    def switch_to_next_device(self):
        """切换到下一个可用的 HID 接口"""
        if not hasattr(self, 'available_devices') or not self.available_devices:
            return False
        self.disconnect_joystick()
        next_idx = (self.current_device_index + 1) % len(self.available_devices)
        return self.connect_joystick(device_index=next_idx)
    
    def get_device_info(self):
        """获取当前设备信息"""
        if not hasattr(self, 'available_devices'):
            return "未扫描"
        total = len(self.available_devices)
        idx = getattr(self, 'current_device_index', 0)
        return f"接口 {idx+1}/{total}"
    
    def disconnect_joystick(self):
        """断开操纵杆连接"""
        if self.device:
            self.device.close()
            self.device = None
            print("操纵杆已断开连接")
    
    def reset_center(self):
        """将当前位置设为中心（调整偏移量）"""
        if not self.device:
            print("请先连接操纵杆")
            return False
        
        if self.last_raw_data:
            # 更新中心值为当前位置
            self.center_values['x'] = self.last_raw_data['x_axis']
            self.center_values['y'] = self.last_raw_data['y_axis']
            self.center_values['ry'] = self.last_raw_data['ry_axis']
            
            # 设置偏移量为0（因为当前位置就是新的中心）
            self.offset['x'] = 0
            self.offset['y'] = 0
            self.offset['ry'] = 0
            
            print(f"中心已重置 - 新中心值: X={self.center_values['x']:04X}, Y={self.center_values['y']:04X}, RY={self.center_values['ry']:04X}")
            return True
        
        print("重置失败 - 无法获取当前数据")
        return False
    
    def start_boundary_detection(self):
        """开始边界检测模式，用于确定硬件的真实范围"""
        if not self.device:
            print("请先连接操纵杆")
            return False
        
        # 重置边界值
        self.axis_boundaries = {
            'x_min': 0xFFFF, 'x_max': 0x0000,
            'y_min': 0xFFFF, 'y_max': 0x0000,
            'ry_min': 0xFFFF, 'ry_max': 0x0000,
        }
        
        self.boundary_detection_mode = True
        self.boundary_sample_count = 0
        print("边界检测模式已启动，请移动操纵杆到各个极限位置...")
        return True
    
    def stop_boundary_detection(self):
        """停止边界检测模式并显示结果"""
        if not self.boundary_detection_mode:
            return False
        
        self.boundary_detection_mode = False
        print(f"边界检测完成 ({self.boundary_sample_count} 个样本):")
        print(f"X轴: {self.axis_boundaries['x_min']:04X} ({self.axis_boundaries['x_min']}) - {self.axis_boundaries['x_max']:04X} ({self.axis_boundaries['x_max']})")
        print(f"Y轴: {self.axis_boundaries['y_min']:04X} ({self.axis_boundaries['y_min']}) - {self.axis_boundaries['y_max']:04X} ({self.axis_boundaries['y_max']})")
        print(f"RY轴: {self.axis_boundaries['ry_min']:04X} ({self.axis_boundaries['ry_min']}) - {self.axis_boundaries['ry_max']:04X} ({self.axis_boundaries['ry_max']})")
        
        # 计算并更新中心值为边界范围的中点
        for axis in ['x', 'y', 'ry']:
            min_val = self.axis_boundaries[f'{axis}_min']
            max_val = self.axis_boundaries[f'{axis}_max']
            
            if min_val != 0xFFFF and max_val != 0x0000 and max_val > min_val:
                # 计算中心值为边界范围的中点
                new_center = (min_val + max_val) // 2
                old_center = self.center_values[axis]
                self.center_values[axis] = new_center
                print(f"{axis}轴中心值更新: {old_center:04X} -> {new_center:04X}")
        
        # 显示更新后的中心值
        print(f"更新后的中心值: X={self.center_values['x']:04X}, Y={self.center_values['y']:04X}, RY={self.center_values['ry']:04X}")
        
        # 显示归一化范围
        for axis in ['x', 'y', 'ry']:
            min_val = self.axis_boundaries[f'{axis}_min']
            max_val = self.axis_boundaries[f'{axis}_max']
            center_val = self.center_values[axis]
            
            if min_val != 0xFFFF and max_val != 0x0000 and max_val > min_val:
                center_to_min = center_val - min_val
                center_to_max = max_val - center_val
                print(f"{axis}轴归一化范围: 中心到最小={center_to_min}, 中心到最大={center_to_max}")
                print(f"  范围: {min_val:04X} - {center_val:04X} - {max_val:04X}")
        
        # 保存校准配置到文件
        self.save_calibration_config()
        return True
    
    def _process_raw_data(self, data):
        """处理原始数据"""
        try:
            # 解析原始数据
            parsed_data = self._parse_data(data)
            if parsed_data:
                # 保存完整的原始字节
                self.last_raw_bytes = bytes(data)
                self.last_raw_data = parsed_data.copy()
                
                # 边界检测模式：更新边界但继续处理数据以便GUI实时显示
                if self.boundary_detection_mode:
                    self._update_boundaries(parsed_data)
                    self.boundary_sample_count += 1
                
                # 第一次接收数据时记录中心值并设置偏移量，使显示为0.0
                if not self.first_data_received:
                    # 记录连接时的实际中心值
                    self.center_values['x'] = parsed_data['x_axis']
                    self.center_values['y'] = parsed_data['y_axis']
                    self.center_values['ry'] = parsed_data['ry_axis']
                    
                    # 设置偏移量为0（因为当前位置就是中心）
                    self.offset['x'] = 0
                    self.offset['y'] = 0
                    self.offset['ry'] = 0
                    
                    self.first_data_received = True
                    print(f"记录中心值: X={self.center_values['x']:04X}, Y={self.center_values['y']:04X}, RY={self.center_values['ry']:04X}")
                
                # 对原始数据做平滑处理，抑制 ADC 噪声
                parsed_data['x_axis'] = self._smooth_value('x', parsed_data['x_axis'])
                parsed_data['y_axis'] = self._smooth_value('y', parsed_data['y_axis'])
                parsed_data['ry_axis'] = self._smooth_value('ry', parsed_data['ry_axis'])
                
                # 转换为标准化坐标
                self._convert_to_normalized(parsed_data)
                
                # 调用回调函数
                if self.data_callback:
                    self.data_callback(self.current_data)
                    
        except Exception as e:
            print(f"数据处理错误: {e}")
    
    def _smooth_value(self, axis, raw_value):
        """对原始轴值应用指数移动平均（EMA）平滑"""
        if self.smoothed_values[axis] is None:
            self.smoothed_values[axis] = float(raw_value)
        else:
            self.smoothed_values[axis] = (
                self.smoothing_factor * raw_value
                + (1 - self.smoothing_factor) * self.smoothed_values[axis]
            )
        return round(self.smoothed_values[axis])

    def _update_boundaries(self, parsed_data):
        """更新边界值（在边界检测模式下调用）"""
        # 更新X轴边界
        self.axis_boundaries['x_min'] = min(self.axis_boundaries['x_min'], parsed_data['x_axis'])
        self.axis_boundaries['x_max'] = max(self.axis_boundaries['x_max'], parsed_data['x_axis'])
        
        # 更新Y轴边界
        self.axis_boundaries['y_min'] = min(self.axis_boundaries['y_min'], parsed_data['y_axis'])
        self.axis_boundaries['y_max'] = max(self.axis_boundaries['y_max'], parsed_data['y_axis'])
        
        # 更新RY轴边界
        self.axis_boundaries['ry_min'] = min(self.axis_boundaries['ry_min'], parsed_data['ry_axis'])
        self.axis_boundaries['ry_max'] = max(self.axis_boundaries['ry_max'], parsed_data['ry_axis'])
    
    def _parse_data(self, data):
        """解析操作杆数据"""
        if len(data) < 11:
            return None
        
        # X轴数据，第1字节是低位，第2字节是高位
        x_axis = int.from_bytes(data[1:3], byteorder='little')
        # Y轴数据，第3字节是低位，第4字节是高位
        y_axis = int.from_bytes(data[3:5], byteorder='little')
        # RY轴数据，第7字节是低位，第8字节是高位
        ry_axis = int.from_bytes(data[7:9], byteorder='little')
        
        # 按钮状态，第9字节和第10字节
        bb1 = data[9]
        bb2 = data[10]
        
        # 按钮状态解析
        button_states = {
            'button1': bool(bb1 & 0x01),  # 按钮1
            'button2': bool(bb1 & 0x02),  # 按钮2
            'button7': bool(bb1 & 0x40),  # 按钮7
        }
        
        return {
            'x_axis': x_axis,
            'y_axis': y_axis,
            'ry_axis': ry_axis,
            'buttons': button_states
        }
    
    def _convert_to_normalized(self, parsed_data):
        """将原始数据转换为标准化坐标 (-1 到 1)，使用类似原始代码的双向映射方法"""
        # 应用偏移量
        adjusted_x = parsed_data['x_axis'] - self.offset['x']
        adjusted_y = parsed_data['y_axis'] - self.offset['y']
        adjusted_ry = parsed_data['ry_axis'] - self.offset['ry']
        
        # 主轴X坐标
        self.current_data['main_x'] = self._normalize_axis_value(adjusted_x, self.center_values['x'], 'x')
        
        # 主轴Y坐标（反转方向）
        self.current_data['main_y'] = -self._normalize_axis_value(adjusted_y, self.center_values['y'], 'y')
        
        # 副轴Y坐标
        self.current_data['sub_y'] = self._normalize_axis_value(adjusted_ry, self.center_values['ry'], 'ry')
        
        # 按钮状态
        self.current_data['button1'] = parsed_data['buttons']['button1']
        self.current_data['button2'] = parsed_data['buttons']['button2']
        self.current_data['button7'] = parsed_data['buttons']['button7']
    
    # 迟滞死区（归一化百分比），对任何位宽设备通用
    DEAD_ZONE_ENTER = 0.01    # 归一化值回落到 ±1% 才重新进入死区
    DEAD_ZONE_EXIT = 0.03     # 归一化值超过 ±3% 才离开死区
    DEAD_ZONE_ENTER_RY = 0.02 # 副轴进入死区阈值
    DEAD_ZONE_EXIT_RY = 0.05  # 副轴离开死区阈值

    def _normalize_axis_value(self, value, center, axis_name):
        """使用双向映射方法归一化轴值，带迟滞死区防止边界振荡"""
        min_val = self.axis_boundaries[f'{axis_name}_min']
        max_val = self.axis_boundaries[f'{axis_name}_max']
        
        # 先计算归一化值
        if min_val == 0xFFFF or max_val == 0x0000 or max_val <= min_val:
            half_range = max(center, 1)
            normalized = (value - center) / half_range
        elif value < center:
            normalized = -1.0 * (center - value) / max(center - min_val, 1) if center > min_val else 0.0
        else:
            normalized = (value - center) / max(max_val - center, 1) if max_val > center else 0.0
        
        normalized = max(-1.0, min(1.0, normalized))
        
        # 迟滞死区：基于归一化值判断，对任何位宽设备通用
        enter_th = self.DEAD_ZONE_ENTER_RY if axis_name == 'ry' else self.DEAD_ZONE_ENTER
        exit_th = self.DEAD_ZONE_EXIT_RY if axis_name == 'ry' else self.DEAD_ZONE_EXIT
        
        if self.in_dead_zone[axis_name]:
            if abs(normalized) < exit_th:
                return 0.0
            self.in_dead_zone[axis_name] = False
        else:
            if abs(normalized) < enter_th:
                self.in_dead_zone[axis_name] = True
                return 0.0
        
        return round(normalized, 2)
    
    def load_calibration_config(self):
        """从JSON文件加载校准配置"""
        try:
            if os.path.exists(self.boundary_config_file):
                with open(self.boundary_config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                # 更新边界值
                if 'axis_boundaries' in config:
                    self.axis_boundaries.update(config['axis_boundaries'])
                    print(f"已加载校准配置: {self.boundary_config_file}")
                    print(f"X轴: {self.axis_boundaries['x_min']:04X} - {self.axis_boundaries['x_max']:04X}")
                    print(f"Y轴: {self.axis_boundaries['y_min']:04X} - {self.axis_boundaries['y_max']:04X}")
                    print(f"RY轴: {self.axis_boundaries['ry_min']:04X} - {self.axis_boundaries['ry_max']:04X}")
                
                # 更新中心值（如果有保存的话）
                if 'center_values' in config:
                    self.center_values.update(config['center_values'])
                    print(f"已加载中心值: X={self.center_values['x']:04X}, Y={self.center_values['y']:04X}, RY={self.center_values['ry']:04X}")
                    
        except Exception as e:
            print(f"加载校准配置失败: {e}")
            print("使用默认配置")
    
    def save_calibration_config(self):
        """保存校准配置到JSON文件"""
        try:
            config = {
                'axis_boundaries': self.axis_boundaries.copy(),
                'center_values': self.center_values.copy(),
                'timestamp': datetime.now().isoformat(),
                'description': '操纵杆校准配置 - 边界检测和中心值'
            }
            
            with open(self.boundary_config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
                
            print(f"校准配置已保存: {self.boundary_config_file}")
            
        except Exception as e:
            print(f"保存校准配置失败: {e}")
    
    def get_data(self):
        """获取当前数据"""
        return self.current_data.copy()
    
    def set_data_callback(self, callback):
        """设置数据回调函数"""
        self.data_callback = callback


class SimpleJoystickGUI:
    """操纵杆诊断与校准 GUI"""
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("操纵杆诊断与校准工具")
        self.root.geometry("750x620")
        
        self.controller = SimpleJoystickController()
        self.controller.set_data_callback(self._update_display)
        self.snapshot = None  # 快照数据
        
        self._create_widgets()
        self.root.after(100, self._show_device_selector)
    
    def _create_widgets(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # === 原始 HID 数据包 ===
        raw_bytes_frame = ttk.LabelFrame(main_frame, text="原始 HID 数据包（完整）")
        raw_bytes_frame.pack(fill=tk.X, pady=3)
        self.raw_bytes_label = ttk.Label(raw_bytes_frame, text="等待数据...", font=('Courier', 9), wraplength=720, justify='left')
        self.raw_bytes_label.pack(padx=5, pady=3)
        
        # === 快照对比 ===
        snap_frame = ttk.LabelFrame(main_frame, text="快照对比（不动时捕获一次，推摇杆后再捕获一次，看差异）")
        snap_frame.pack(fill=tk.X, pady=3)
        snap_btn_row = ttk.Frame(snap_frame)
        snap_btn_row.pack(pady=2)
        self.snap_btn = ttk.Button(snap_btn_row, text="捕获快照", command=self._take_snapshot)
        self.snap_btn.pack(side=tk.LEFT, padx=5)
        self.snap_clear_btn = ttk.Button(snap_btn_row, text="清除快照", command=self._clear_snapshot)
        self.snap_clear_btn.pack(side=tk.LEFT, padx=5)
        self.snap_label = ttk.Label(snap_frame, text="未捕获", font=('Courier', 9), wraplength=720, justify='left')
        self.snap_label.pack(padx=5, pady=3)
        
        # === 归一化输出 ===
        output_frame = ttk.LabelFrame(main_frame, text="归一化输出（-1.00 ~ +1.00）")
        output_frame.pack(fill=tk.X, pady=3)
        
        norm_row = ttk.Frame(output_frame)
        norm_row.pack(fill=tk.X, padx=5, pady=3)
        self.main_x_label = ttk.Label(norm_row, text="主X: +0.00", font=('Courier', 16, 'bold'))
        self.main_x_label.pack(side=tk.LEFT, padx=15)
        self.main_y_label = ttk.Label(norm_row, text="主Y: +0.00", font=('Courier', 16, 'bold'))
        self.main_y_label.pack(side=tk.LEFT, padx=15)
        self.sub_y_label = ttk.Label(norm_row, text="副Y: +0.00", font=('Courier', 16, 'bold'))
        self.sub_y_label.pack(side=tk.LEFT, padx=15)
        
        # === 按钮状态 ===
        button_frame = ttk.LabelFrame(main_frame, text="按钮状态")
        button_frame.pack(fill=tk.X, pady=3)
        btn_row = ttk.Frame(button_frame)
        btn_row.pack(pady=3)
        self.button1_label = tk.Label(btn_row, text="按钮1", width=10, height=1,
                                     bg='lightgray', relief='raised', font=('Arial', 10))
        self.button1_label.pack(side=tk.LEFT, padx=5)
        self.button2_label = tk.Label(btn_row, text="按钮2", width=10, height=1,
                                     bg='lightgray', relief='raised', font=('Arial', 10))
        self.button2_label.pack(side=tk.LEFT, padx=5)
        self.button7_label = tk.Label(btn_row, text="按钮7", width=10, height=1,
                                     bg='lightgray', relief='raised', font=('Arial', 10))
        self.button7_label.pack(side=tk.LEFT, padx=5)
        
        # === 控制按钮 ===
        control_frame = ttk.LabelFrame(main_frame, text="操作")
        control_frame.pack(fill=tk.X, pady=3)
        btn_row2 = ttk.Frame(control_frame)
        btn_row2.pack(pady=5)
        
        self.connect_btn = ttk.Button(btn_row2, text="连接操纵杆", command=self._connect_joystick)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        self.switch_btn = ttk.Button(btn_row2, text="切换接口", command=self._switch_device)
        self.switch_btn.pack(side=tk.LEFT, padx=5)
        self.reset_center_btn = ttk.Button(btn_row2, text="重置中心", command=self._reset_center)
        self.reset_center_btn.pack(side=tk.LEFT, padx=5)
        self.boundary_detect_btn = ttk.Button(btn_row2, text="开始边界检测", command=self._toggle_boundary_detection)
        self.boundary_detect_btn.pack(side=tk.LEFT, padx=5)
        self.disconnect_btn = ttk.Button(btn_row2, text="断开连接", command=self._disconnect_joystick)
        self.disconnect_btn.pack(side=tk.LEFT, padx=5)
        
        self.status_label = ttk.Label(control_frame, text="状态: 未连接", font=('Arial', 10))
        self.status_label.pack(pady=3)
        
        self.reset_center_btn.config(state='disabled')
        self.boundary_detect_btn.config(state='disabled')
        self.switch_btn.config(state='disabled')
    
    def _show_device_selector(self):
        """弹出设备选择窗口，列出所有 HID 设备"""
        sel_win = tk.Toplevel(self.root)
        sel_win.title("选择 HID 设备")
        sel_win.geometry("800x450")
        sel_win.transient(self.root)
        sel_win.grab_set()
        
        tk.Label(sel_win, text="请选择你的摇杆设备（注意同一设备可能有多个接口）：",
                 font=('Arial', 11)).pack(pady=8)
        
        list_frame = tk.Frame(sel_win)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, font=('Courier', 9),
                             selectmode=tk.SINGLE)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)
        
        all_devices = hid.HidDeviceFilter().get_devices()
        device_list = []
        for i, dev in enumerate(all_devices):
            path_short = str(dev.device_path)[-40:] if dev.device_path else ""
            info = (f"{i+1:2d}. [{dev.vendor_id:04X}:{dev.product_id:04X}] "
                    f"{dev.product_name or 'Unknown':30s} "
                    f"({dev.vendor_name or '?'}) ...{path_short}")
            listbox.insert(tk.END, info)
            device_list.append(dev)
        
        def on_connect():
            sel = listbox.curselection()
            if sel:
                sel_win.destroy()
                self._connect_specific_device(device_list[sel[0]])
        
        def on_cancel():
            sel_win.destroy()
        
        btn_frame = tk.Frame(sel_win)
        btn_frame.pack(pady=8)
        tk.Button(btn_frame, text="连接选中设备", command=on_connect, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="取消", command=on_cancel, width=10).pack(side=tk.LEFT, padx=5)
    
    def _connect_specific_device(self, device):
        """直接连接指定的 HID 设备"""
        try:
            if self.controller.device:
                self.controller.disconnect_joystick()
            device.open()
            self.controller.device = device
            self.controller._reset_state()
            device.set_raw_data_handler(self.controller._process_raw_data)
            
            self.status_label.config(
                text=f"已连接: [{device.vendor_id:04X}:{device.product_id:04X}] {device.product_name} — 移动摇杆验证")
            self.connect_btn.config(state='disabled')
            self.disconnect_btn.config(state='normal')
            self.reset_center_btn.config(state='normal')
            self.boundary_detect_btn.config(state='normal')
            self.switch_btn.config(state='normal')
        except Exception as e:
            self.status_label.config(text=f"连接失败: {e}")
    
    def _connect_joystick(self):
        self._show_device_selector()
    
    def _take_snapshot(self):
        """捕获当前 HID 数据快照"""
        if self.controller.last_raw_bytes:
            self.snapshot = bytes(self.controller.last_raw_bytes)
            self.snap_label.config(text=f"快照已捕获 ({len(self.snapshot)} 字节) — 现在移动摇杆，再次捕获对比")
    
    def _clear_snapshot(self):
        self.snapshot = None
        self.snap_label.config(text="未捕获")
    
    def _switch_device(self):
        """切换到下一个 HID 接口"""
        if self.controller.switch_to_next_device():
            info = self.controller.get_device_info()
            self.status_label.config(text=f"已切换到 {info} — 移动摇杆看字节是否跟着变化")
        else:
            self.status_label.config(text="没有更多接口可切换")
    
    def _disconnect_joystick(self):
        self.controller.disconnect_joystick()
        self.status_label.config(text="状态: 已断开")
        self.connect_btn.config(state='normal')
        self.disconnect_btn.config(state='disabled')
        self.reset_center_btn.config(state='disabled')
        self.boundary_detect_btn.config(state='disabled')
        self.switch_btn.config(state='disabled')
    
    def _reset_center(self):
        if self.controller.reset_center():
            c = self.controller.center_values
            self.status_label.config(
                text=f"中心已重置: X={c['x']}  Y={c['y']}  RY={c['ry']}")
        else:
            self.status_label.config(text="状态: 重置失败")
    
    def _toggle_boundary_detection(self):
        if not self.controller.boundary_detection_mode:
            if self.controller.start_boundary_detection():
                self.boundary_detect_btn.config(text="停止边界检测")
                self.status_label.config(
                    text="边界检测中 — 请将摇杆推到所有方向的极限位置，然后点击「停止边界检测」")
        else:
            if self.controller.stop_boundary_detection():
                self.boundary_detect_btn.config(text="开始边界检测")
                b = self.controller.axis_boundaries
                self.status_label.config(
                    text=f"边界检测完成并已保存  X:[{b['x_min']}-{b['x_max']}]  "
                         f"Y:[{b['y_min']}-{b['y_max']}]  RY:[{b['ry_min']}-{b['ry_max']}]")
    
    def _update_display(self, data):
        if self.controller.last_raw_bytes:
            b = self.controller.last_raw_bytes
            packet_len = len(b)
            # 每行最多 16 字节，多行显示
            lines = []
            for row_start in range(0, packet_len, 16):
                row_end = min(row_start + 16, packet_len)
                hex_part = ' '.join(f'{b[i]:02X}' for i in range(row_start, row_end))
                idx_part = ' '.join(f'{i:2d}' for i in range(row_start, row_end))
                lines.append(f"[{row_start:2d}] {hex_part}")
                lines.append(f"     {idx_part}")
            self.raw_bytes_label.config(text=f"包长: {packet_len} 字节\n" + '\n'.join(lines))
            
            # 快照对比
            if self.snapshot is not None:
                diff_parts = []
                max_len = max(len(self.snapshot), packet_len)
                changed_indices = []
                for i in range(max_len):
                    old_v = self.snapshot[i] if i < len(self.snapshot) else 0
                    new_v = b[i] if i < packet_len else 0
                    delta = new_v - old_v
                    if delta != 0:
                        changed_indices.append(i)
                        diff_parts.append(f"[{i:2d}] {old_v:02X}->{new_v:02X} ({delta:+d})")
                if changed_indices:
                    self.snap_label.config(
                        text=f"变化的字节位置: {changed_indices}\n" + '  '.join(diff_parts))
                else:
                    self.snap_label.config(text="快照与当前完全一致（无变化）")
        
        # 归一化输出
        self.main_x_label.config(text=f"主X: {data['main_x']:+.2f}")
        self.main_y_label.config(text=f"主Y: {data['main_y']:+.2f}")
        self.sub_y_label.config(text=f"副Y: {data['sub_y']:+.2f}")
        
        # 按钮状态
        for btn_label, key in [(self.button1_label, 'button1'),
                               (self.button2_label, 'button2'),
                               (self.button7_label, 'button7')]:
            btn_label.config(
                bg='green' if data[key] else 'lightgray',
                relief='sunken' if data[key] else 'raised')
    
    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.root.mainloop()
    
    def _on_closing(self):
        self.controller.disconnect_joystick()
        self.root.destroy()


def main():
    """主函数"""
    print("启动简化操纵杆控制器...")
    
    # 创建并运行GUI
    gui = SimpleJoystickGUI()
    gui.run()


if __name__ == "__main__":
    main()