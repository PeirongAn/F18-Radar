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
        
        # 记录实际的中心值（连接时的初始值）
        self.center_values = {
            'x': 0x0800,  # 默认值，连接时会更新
            'y': 0x0800,  # 默认值，连接时会更新
            'ry': 0x0800  # 默认值，连接时会更新
        }
        
        # 轴范围边界值（通过测试获得的实际硬件范围）
        # 这些值应该通过实际测试确定，而不是假设
        self.axis_boundaries = {
            'x_min': 0x0000,    # 需要实际测试确定
            'x_max': 0x0FFF,    # 需要实际测试确定
            'y_min': 0x0000,    # 需要实际测试确定
            'y_max': 0x0FFF,    # 需要实际测试确定
            'ry_min': 0x0000,   # 需要实际测试确定
            'ry_max': 0x0FFF,   # 需要实际测试确定
        }
        
        # 边界检测配置文件路径
        self.boundary_config_file = "joystick_calibration.json"
        
        # 设备连接
        self.device = None
        
        # 数据回调函数
        self.data_callback = None
        
        # 保存最新的原始数据
        self.last_raw_data = None
        
        # 初始化标志
        self.first_data_received = False
        
        # 边界检测模式
        self.boundary_detection_mode = False
        self.boundary_sample_count = 0
        
        # 启动时加载校准配置
        self.load_calibration_config()
        
    def connect_joystick(self):
        """连接操纵杆设备"""
        try:
            # 尝试连接已知的摇杆设备
            known_devices = [(1356, 98)]  # China Longcctv 摇杆
            
            all_devices = hid.HidDeviceFilter().get_devices()
            
            for vendor_id, product_id in known_devices:
                for device in all_devices:
                    if device.vendor_id == vendor_id and device.product_id == product_id:
                        try:
                            device.open()
                            self.device = device
                            device.set_raw_data_handler(self._process_raw_data)
                            print(f"已连接到操纵杆：{device.product_name}")
                            return True
                        except Exception as e:
                            print(f"连接失败: {e}")
                            continue
            
            # 如果找不到已知设备，尝试自动检测
            joystick_keywords = ['joystick', 'gamepad', 'controller', 'stick', '摇杆', 'longcctv']
            
            for device in all_devices:
                device_name = (device.product_name or "").lower()
                manufacturer = (device.vendor_name or "").lower()
                
                if any(keyword in device_name or keyword in manufacturer for keyword in joystick_keywords):
                    try:
                        device.open()
                        self.device = device
                        device.set_raw_data_handler(self._process_raw_data)
                        print(f"已连接到操纵杆：{device.product_name}")
                        return True
                    except Exception as e:
                        print(f"连接失败: {e}")
                        continue
            
            print("未找到操纵杆设备")
            return False
            
        except Exception as e:
            print(f"连接操纵杆失败: {e}")
            return False
    
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
                # 保存最新的原始数据
                self.last_raw_data = parsed_data.copy()
                
                # 边界检测模式
                if self.boundary_detection_mode:
                    self._update_boundaries(parsed_data)
                    self.boundary_sample_count += 1
                    return  # 边界检测模式下不进行正常处理
                
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
                
                # 转换为标准化坐标
                self._convert_to_normalized(parsed_data)
                
                # 调用回调函数
                if self.data_callback:
                    self.data_callback(self.current_data)
                    
        except Exception as e:
            print(f"数据处理错误: {e}")
    
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
        
        # 主轴X坐标 - 使用双向映射
        self.current_data['main_x'] = self._normalize_axis_value(adjusted_x, self.center_values['x'], 'x')
        
        # 主轴Y坐标 - 使用双向映射（反转方向）
        self.current_data['main_y'] = -self._normalize_axis_value(adjusted_y, self.center_values['y'], 'y')
        
        # 副轴Y坐标 - 使用双向映射
        self.current_data['sub_y'] = self._normalize_axis_value(adjusted_ry, self.center_values['ry'], 'ry')
        
        # 按钮状态
        self.current_data['button1'] = parsed_data['buttons']['button1']
        self.current_data['button2'] = parsed_data['buttons']['button2']
        self.current_data['button7'] = parsed_data['buttons']['button7']
    
    def _normalize_axis_value(self, value, center, axis_name):
        """使用双向映射方法归一化轴值，类似原始代码的逻辑"""
        min_val = self.axis_boundaries[f'{axis_name}_min']
        max_val = self.axis_boundaries[f'{axis_name}_max']
        
        # 如果边界值无效（未检测或检测失败），使用默认范围
        if min_val == 0xFFFF or max_val == 0x0000 or max_val <= min_val:
            # 使用默认范围进行简单线性映射，以实际中心值为基准
            return (value - center) / 0x0800
        
        # 确保中心值正确映射到0
        if abs(value - center) < 1:
            return 0.0
        
        # 以中心值为基准进行双向映射到-1到1
        if value < center:
            # 从min到center映射到-1到0
            if center > min_val:
                normalized = -1.0 * (center - value) / (center - min_val)
            else:
                normalized = 0.0
        else:
            # 从center到max映射到0到1
            if max_val > center:
                normalized = (value - center) / (max_val - center)
            else:
                normalized = 0.0
        
        # 严格限制在-1到1范围内
        return max(-1.0, min(1.0, normalized))
    
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
    """简化的操纵杆GUI界面"""
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("简化操纵杆控制器")
        self.root.geometry("600x400")
        
        # 创建控制器
        self.controller = SimpleJoystickController()
        self.controller.set_data_callback(self._update_display)
        
        # 创建界面
        self._create_widgets()
        
        # 自动连接
        self.controller.connect_joystick()
    
    def _create_widgets(self):
        """创建界面组件"""
        # 主框架
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 数据显示区域
        data_frame = ttk.LabelFrame(main_frame, text="操纵杆数据")
        data_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 主轴坐标显示
        main_axis_frame = ttk.LabelFrame(data_frame, text="主轴坐标 (X, Y)")
        main_axis_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.main_x_label = ttk.Label(main_axis_frame, text="X: +0.000", font=('Arial', 14))
        self.main_x_label.pack(side=tk.LEFT, padx=10)
        
        self.main_y_label = ttk.Label(main_axis_frame, text="Y: +0.000", font=('Arial', 14))
        self.main_y_label.pack(side=tk.LEFT, padx=10)
        
        # 副轴坐标显示
        sub_axis_frame = ttk.LabelFrame(data_frame, text="副轴坐标 (Y)")
        sub_axis_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.sub_y_label = ttk.Label(sub_axis_frame, text="Y: +0.000", font=('Arial', 14))
        self.sub_y_label.pack(padx=10)
        
        # 按钮状态显示
        button_frame = ttk.LabelFrame(data_frame, text="按钮状态")
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.button1_label = tk.Label(button_frame, text="按钮1", width=10, height=2, 
                                     bg='lightgray', relief='raised', font=('Arial', 10))
        self.button1_label.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.button2_label = tk.Label(button_frame, text="按钮2", width=10, height=2, 
                                     bg='lightgray', relief='raised', font=('Arial', 10))
        self.button2_label.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.button7_label = tk.Label(button_frame, text="按钮7", width=10, height=2, 
                                     bg='lightgray', relief='raised', font=('Arial', 10))
        self.button7_label.pack(side=tk.LEFT, padx=5, pady=5)
        
        # 控制按钮
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=5)
        
        self.connect_btn = ttk.Button(control_frame, text="连接操纵杆", command=self._connect_joystick)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        
        self.reset_center_btn = ttk.Button(control_frame, text="重置中心", command=self._reset_center)
        self.reset_center_btn.pack(side=tk.LEFT, padx=5)
        
        self.boundary_detect_btn = ttk.Button(control_frame, text="检测边界", command=self._toggle_boundary_detection)
        self.boundary_detect_btn.pack(side=tk.LEFT, padx=5)
        
        self.disconnect_btn = ttk.Button(control_frame, text="断开连接", command=self._disconnect_joystick)
        self.disconnect_btn.pack(side=tk.LEFT, padx=5)
        
        self.status_label = ttk.Label(control_frame, text="状态: 未连接")
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # 原始数据显示
        raw_data_frame = ttk.LabelFrame(main_frame, text="原始数据（调试）")
        raw_data_frame.pack(fill=tk.X, pady=5)
        
        self.raw_data_label = ttk.Label(raw_data_frame, text="原始数据: 未连接", font=('Courier', 10))
        self.raw_data_label.pack(padx=5, pady=5)
        
        # 设置初始按钮状态
        self.reset_center_btn.config(state='disabled')
        self.boundary_detect_btn.config(state='disabled')
    
    def _connect_joystick(self):
        """连接操纵杆"""
        if self.controller.connect_joystick():
            self.status_label.config(text="状态: 已连接")
            self.connect_btn.config(state='disabled')
            self.disconnect_btn.config(state='normal')
            self.reset_center_btn.config(state='normal')
            self.boundary_detect_btn.config(state='normal')
        else:
            self.status_label.config(text="状态: 连接失败")
    
    def _disconnect_joystick(self):
        """断开操纵杆连接"""
        self.controller.disconnect_joystick()
        self.status_label.config(text="状态: 已断开")
        self.connect_btn.config(state='normal')
        self.disconnect_btn.config(state='disabled')
        self.reset_center_btn.config(state='disabled')
        self.boundary_detect_btn.config(state='disabled')
    
    def _reset_center(self):
        """重置中心位置"""
        if self.controller.reset_center():
            self.status_label.config(text="状态: 中心已重置")
        else:
            self.status_label.config(text="状态: 重置失败")
    
    def _toggle_boundary_detection(self):
        """切换边界检测模式"""
        if not self.controller.boundary_detection_mode:
            # 开始边界检测
            if self.controller.start_boundary_detection():
                self.boundary_detect_btn.config(text="停止检测")
                self.status_label.config(text="状态: 边界检测中，请移动操纵杆到各个极限位置")
        else:
            # 停止边界检测
            if self.controller.stop_boundary_detection():
                self.boundary_detect_btn.config(text="检测边界")
                self.status_label.config(text="状态: 边界检测完成")
    
    def _update_display(self, data):
        """更新显示数据"""
        # 更新主轴坐标
        self.main_x_label.config(text=f"X: {data['main_x']:+.3f}")
        self.main_y_label.config(text=f"Y: {data['main_y']:+.3f}")
        
        # 更新副轴坐标
        self.sub_y_label.config(text=f"Y: {data['sub_y']:+.3f}")
        
        # 更新按钮状态
        self.button1_label.config(
            bg='green' if data['button1'] else 'lightgray',
            relief='sunken' if data['button1'] else 'raised'
        )
        
        self.button2_label.config(
            bg='green' if data['button2'] else 'lightgray',
            relief='sunken' if data['button2'] else 'raised'
        )
        
        self.button7_label.config(
            bg='green' if data['button7'] else 'lightgray',
            relief='sunken' if data['button7'] else 'raised'
        )
        
        # 更新原始数据显示
        if hasattr(self.controller, 'last_raw_data') and self.controller.last_raw_data:
            raw_data = self.controller.last_raw_data
            raw_text = f"原始数据: X={raw_data['x_axis']:04X} Y={raw_data['y_axis']:04X} RY={raw_data['ry_axis']:04X}"
            raw_text += f" | 偏移量: X={self.controller.offset['x']:+d} Y={self.controller.offset['y']:+d} RY={self.controller.offset['ry']:+d}"
            self.raw_data_label.config(text=raw_text)
    
    def run(self):
        """运行GUI"""
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.root.mainloop()
    
    def _on_closing(self):
        """关闭程序"""
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