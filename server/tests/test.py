import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Wedge, Circle
from matplotlib.animation import FuncAnimation
import time
import random
from matplotlib.transforms import Affine2D

class RadarTarget:
    """表示雷达目标的类"""
    def __init__(self, position, velocity, rcs=5.0):
        self.position = np.array(position)  # [x, y, z] in meters
        self.velocity = np.array(velocity)  # [vx, vy, vz] in m/s
        self.rcs = rcs  # 雷达截面积 (m²)
        self.track_quality = 0.0  # 跟踪质量 (0-1)
        self.track_history = []  # 历史位置记录
        self.track_id = None  # 跟踪ID
        self.threat_level = 0  # 威胁等级 (0-3)

    def update(self, dt):
        """更新目标位置"""
        self.position = self.position + self.velocity * dt
        self.track_history.append(self.position.copy())
        # 保留最近10个历史位置
        if len(self.track_history) > 10:
            self.track_history.pop(0)


class TWS_Radar:
    """表示TWS模式雷达的类"""
    def __init__(self):
        self.max_range = 80 * 1852  # 最大探测范围 (80 NM 转换为米)
        self.scan_rate = 60  # 扫描速率 (度/秒)
        self.scan_direction = 1  # 扫描方向 (1=右, -1=左)
        self.current_azimuth = -60  # 当前扫描方位角
        self.scan_width = 120  # 扫描宽度 (±60度)
        self.noise_level = 0.05  # 噪声水平

# 雷达参数
        self.power = 10000  # 发射功率 (W)
        self.gain = 30  # 天线增益 (dB)
        self.wavelength = 0.03  # 波长 (m)
        self.min_detectable_power = 1e-13  # 最小可检测功率 (W)
        
    def detect_targets(self, targets, own_position):
        """检测在扫描范围内的目标"""
        detected = []
        
        for target in targets:
            # 计算相对位置
            rel_pos = target.position - own_position
            distance = np.linalg.norm(rel_pos[:2])  # 仅考虑水平距离
            
            # 超出最大范围的目标不检测
            if distance > self.max_range:
                continue
                
            # 计算方位角
            azimuth = np.degrees(np.arctan2(rel_pos[0], rel_pos[1]))
            
            # 检查目标是否在当前扫描扇区内 (±5度)
            scan_min = self.current_azimuth - 5
            scan_max = self.current_azimuth + 5
            
            if (scan_min <= azimuth <= scan_max) or \
               (scan_min + 360 <= azimuth + 360 <= scan_max + 360) or \
               (scan_min - 360 <= azimuth - 360 <= scan_max - 360):
                
                # 计算雷达方程
                received_power = self._calculate_received_power(distance, target.rcs)
                
                # 添加随机噪声
                noise = np.random.normal(0, self.noise_level * received_power)
                received_power += noise
                
                # 如果接收功率高于最小可检测功率，则检测到目标
                if received_power > self.min_detectable_power:
                    # 更新目标的跟踪质量
                    signal_quality = min(1.0, received_power / (self.min_detectable_power * 100))
                    target.track_quality = min(1.0, target.track_quality + signal_quality * 0.2)
                    detected.append(target)
                    
        return detected
    
    def _calculate_received_power(self, distance, rcs):
        """使用雷达方程计算接收功率"""
        # 雷达方程: P_r = (P_t * G^2 * λ^2 * σ) / ((4π)^3 * R^4)
        numerator = self.power * (10**(self.gain/10))**2 * self.wavelength**2 * rcs
        denominator = (4 * np.pi)**3 * distance**4
        return numerator / denominator


class RadarSimulation:
    """雷达模拟类"""
    def __init__(self):
        self.radar = TWS_Radar()
        self.targets = []
        self.tracked_targets = []
        self.own_position = np.array([0, 0, 5000])  # [x, y, z] in meters
        self.own_velocity = np.array([0, 200, 0])  # [vx, vy, vz] in m/s
        self.own_heading = 278  # 当前航向 (度)
        
        # 显示相关变量
        self.fig = None
        self.ax = None
        self.target_artists = []
        self.animation = None
        self.last_time = time.time()
        self.dt = 0.1
        
        # 初始化目标
        self._initialize_targets()
        
    def _initialize_targets(self):
        """初始化一些目标用于演示"""
        # 目标1: 接近中的敌机
        t1 = RadarTarget(
            position=[30000, 50000, 7000],
            velocity=[-200, -300, 0]
        )
        t1.threat_level = 3  # 高威胁
        
        # 目标2: 远距离巡航的飞机
        t2 = RadarTarget(
            position=[-40000, 70000, 9000],
            velocity=[50, -100, 0]
        )
        t2.threat_level = 1  # 低威胁
        
        # 目标3: 侧向接近的飞机
        t3 = RadarTarget(
            position=[60000, 20000, 3000],
            velocity=[-150, 50, 0]
        )
        t3.threat_level = 2  # 中等威胁
        
        self.targets = [t1, t2, t3]
        
    def setup_display(self):
        """设置雷达显示界面"""
        # 创建黑色背景的图形
        self.fig = plt.figure(figsize=(10, 10), facecolor='#0a0a12')
        self.ax = self.fig.add_subplot(111)
        
        # 设置坐标轴
        self.ax.set_xlim(-80, 80)  # 单位为海里
        self.ax.set_ylim(-80, 80)
        self.ax.set_aspect('equal')
        self.ax.set_facecolor('black')
        
        # 移除坐标轴
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        
        # 添加网格线 - 垂直线
        for x in [-60, -30, 0, 30, 60]:
            self.ax.axvline(x, color='green', linestyle='--', alpha=0.3)
        
        # 添加网格线 - 水平线
        for y in [-60, -30, 0, 30, 60]:
            self.ax.axhline(y, color='green', linestyle='--', alpha=0.3)
        
        # 添加距离环
        for r in [20, 40, 60]:
            circle = plt.Circle((0, 0), r, fill=False, color='green', 
                               linestyle='-', alpha=0.3)
            self.ax.add_patch(circle)
        
        # 添加自机位置标记
        self.own_position_marker = plt.Circle((0, 0), 1, fill=True, color='green', alpha=0.7)
        self.ax.add_patch(self.own_position_marker)
        
        # 添加状态栏和信息区
        self.add_status_bar()
        
        # 返回空白的artists列表用于动画
        return []
    
    def add_status_bar(self):
        """添加状态栏和信息显示"""
        # 顶部状态栏
        self.fig.text(0.25, 0.95, "TWS", color='#00ff00', fontsize=12)
        self.fig.text(0.35, 0.95, "STBY", color='#00ff00', fontsize=12)
        self.fig.text(0.45, 0.95, "IFF", color='#00ff00', fontsize=12)
        self.fig.text(0.55, 0.95, "CNTL", color='#00ff00', fontsize=12)
        
        # 右侧刻度标记
        self.fig.text(0.95, 0.9, "8", color='#00ff00', fontsize=12)
        self.fig.text(0.95, 0.5, "60", color='#00ff00', fontsize=12)
        
        # 左侧刻度标记
        self.fig.text(0.05, 0.5, "60", color='#00ff00', fontsize=12)
        self.fig.text(0.05, 0.3, "N\nM", color='#00ff00', fontsize=10)
        self.fig.text(0.05, 0.2, "A\nZ\nM", color='#00ff00', fontsize=10)
        
        # 底部信息
        self.heading_text = self.fig.text(0.3, 0.05, f"{self.own_heading}", color='#00ff00', fontsize=12)
        self.fig.text(0.5, 0.05, "GND", color='#00ff00', fontsize=12)
        self.fig.text(0.7, 0.05, "AUTO", color='#00ff00', fontsize=12)
        self.code_text = self.fig.text(0.9, 0.05, "05980", color='#00ff00', fontsize=12)
    
    def update_frame(self, frame):
        """更新动画帧"""
        # 计算时间增量
        current_time = time.time()
        self.dt = current_time - self.last_time
        self.last_time = current_time
        
        # 限制dt，防止时间步长过大
        self.dt = min(self.dt, 0.1)
        
        # 更新自机位置
        self.own_position += self.own_velocity * self.dt
        
        # 更新目标位置
        for target in self.targets:
            target.update(self.dt)
        
        # 更新雷达扫描
        self.update_radar_scan()
        
        # 更新目标显示
        self.update_targets_display()
        
        # 添加屏幕噪点效果
        self.add_noise_effect()
        
        return []
    
    def update_radar_scan(self):
        """更新雷达扫描位置和检测目标"""
        # 更新雷达扫描位置
        self.radar.current_azimuth += self.radar.scan_rate * self.dt * self.radar.scan_direction
        
        # 检查是否需要改变扫描方向
        if self.radar.current_azimuth > 60:
            self.radar.current_azimuth = 60
            self.radar.scan_direction = -1
        elif self.radar.current_azimuth < -60:
            self.radar.current_azimuth = -60
            self.radar.scan_direction = 1
            
        # 更新扫描线
        if hasattr(self, 'scan_line'):
            self.scan_line.remove()
        
        # 计算扫描线的角度（从北方向开始，顺时针）
        scan_angle = (90 - self.radar.current_azimuth) % 360
        
        # 转换为直角坐标系中的线段
        x_end = 80 * np.cos(np.radians(scan_angle))
        y_end = 80 * np.sin(np.radians(scan_angle))
        
        self.scan_line = self.ax.plot([0, x_end], [0, y_end], 
                                     color='#00ff00', alpha=0.6, linewidth=1.5)[0]
        
        # 添加扫描扇区效果
        if hasattr(self, 'scan_sector'):
            self.scan_sector.remove()
        
        # 检测目标
        detected = self.radar.detect_targets(self.targets, self.own_position)
        
        # 更新跟踪目标列表
        for target in detected:
            if target not in self.tracked_targets:
                # 新目标，添加到跟踪列表
                if len(self.tracked_targets) < 8:  # 最多跟踪8个目标
                    self.tracked_targets.append(target)
                    if target.track_id is None:
                        target.track_id = len(self.tracked_targets)
        
        # 降低未被检测到的目标的跟踪质量
        for target in self.tracked_targets:
            if target not in detected:
                target.track_quality = max(0, target.track_quality - 0.05)
                
                # 如果跟踪质量太低，从跟踪列表中移除
                if target.track_quality < 0.1:
                    self.tracked_targets.remove(target)
    
    def update_targets_display(self):
        """更新目标显示"""
        # 移除之前的目标显示
        for artist in self.target_artists:
            artist.remove()
        self.target_artists = []
        
        # 更新跟踪目标显示
        for target in self.tracked_targets:
            # 计算目标的显示坐标（转换为NM）
            dx = (target.position[0] - self.own_position[0]) / 1852
            dy = (target.position[1] - self.own_position[1]) / 1852
            
            # 创建目标三角形标记 - 黄色箭头样式
            marker_size = 100 * min(1.0, target.track_quality + 0.3)  # 根据跟踪质量调整大小
            
            # 计算目标朝向
            heading = np.degrees(np.arctan2(target.velocity[0], target.velocity[1])) % 360
            
            # 创建三角形标记
            triangle = plt.Polygon([
                [dx, dy + 1],
                [dx - 0.8, dy - 0.6],
                [dx + 0.8, dy - 0.6]
            ], closed=True, color='#ffff00', alpha=0.8 * target.track_quality + 0.2)
            
            # 旋转三角形以匹配目标航向
            transform = Affine2D().rotate_deg_around(dx, dy, heading - 90)
            triangle.set_transform(transform + self.ax.transData)
            
            self.ax.add_patch(triangle)
            self.target_artists.append(triangle)
            
            # 添加速度矢量线
            speed = np.linalg.norm(target.velocity[:2])
            vector_length = speed / 100  # 速度矢量线长度比例
            
            vx = vector_length * np.sin(np.radians(heading))
            vy = vector_length * np.cos(np.radians(heading))
            
            vector_line = plt.Line2D([dx, dx + vx], [dy, dy + vy], 
                                    color='#ffff00', alpha=0.7)
            self.ax.add_line(vector_line)
            self.target_artists.append(vector_line)
            
            # 添加历史轨迹点
            if len(target.track_history) > 1:
                history_x = [(pos[0] - self.own_position[0]) / 1852 for pos in target.track_history[:-1]]
                history_y = [(pos[1] - self.own_position[1]) / 1852 for pos in target.track_history[:-1]]
                
                for i, (hx, hy) in enumerate(zip(history_x, history_y)):
                    alpha = 0.3 * (i + 1) / len(history_x)
                    dot = plt.Circle((hx, hy), 0.3, color='#ffff00', alpha=alpha)
                    self.ax.add_patch(dot)
                    self.target_artists.append(dot)
    
    def add_noise_effect(self):
        """添加雷达噪点效果"""
        # 移除之前的噪点
        if hasattr(self, 'noise_dots'):
            for dot in self.noise_dots:
                dot.remove()
        
        # 创建新的噪点
        self.noise_dots = []
        num_dots = 50
        
        for _ in range(num_dots):
            # 随机位置
            r = random.uniform(0, 80)
            theta = random.uniform(0, 2 * np.pi)
            x = r * np.cos(theta)
            y = r * np.sin(theta)
            
            # 随机大小和透明度
            size = random.uniform(0.1, 0.3)
            alpha = random.uniform(0.1, 0.4)
            
            dot = plt.Circle((x, y), size, color='#00ff00', alpha=alpha)
            self.ax.add_patch(dot)
            self.noise_dots.append(dot)
    
    def run(self):
        """运行雷达模拟"""
        self.setup_display()
        
        # 使用plt.ion()代替FuncAnimation
        plt.ion()  # 打开交互模式
        
        try:
            while True:
                self.update_frame(0)  # 帧号不重要，传0即可
                plt.pause(0.05)  # 暂停0.05秒，相当于20FPS
        except KeyboardInterrupt:
            print("模拟已停止")
        finally:
            plt.ioff()  # 关闭交互模式
            plt.show()  # 保持图形窗口打开


# 运行模拟
if __name__ == "__main__":
    sim = RadarSimulation()
    sim.run()
