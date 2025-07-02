import random
import time
import numpy as np
from typing import List, Dict, Any

class TargetManager:
    """雷达目标管理器，负责目标生成、更新和威胁评估"""
    
    def __init__(self):
        self.unknown_targets: List[Dict[str, Any]] = []
        self.own_heading = 278  # 当前航向 (度)
        self.radar_azimuth = 0  # 固定的雷达方位角值
        self.radar_range = 80   # 雷达范围 (海里)
        self.scan_angle = 60    # 扫描角度 (度)
        
        # 威胁评估权重配置
        self.DISTANCE_WEIGHT = 0.9
        self.HEADING_WEIGHT = 0.1
    
    def initialize_targets(self, difficulty_config: Dict[str, Any]) -> None:
        """根据传入的难度配置初始化目标，并基于威胁评估来决定敌友"""
        total_targets = difficulty_config.get('target_count', 5)
        num_enemies = 2  # 我们总是将威胁分数最高的2个目标设为敌机

        # 1. 生成所有目标，初始时都视为"未知"
        potential_targets = []
        for i in range(total_targets):
            angle = random.uniform(-self.scan_angle / 2, self.scan_angle / 2)
            distance = random.uniform(self.radar_range * 0.1, self.radar_range)
            speed = random.uniform(3, 12)  # 速度范围更广
            direction = random.uniform(0, 2 * np.pi)  # 初始朝向是完全随机的
            
            potential_targets.append({
                "id": f"target-{i+1}",  # 临时ID
                "position": {"x": angle, "y": distance},
                "speed": speed,
                "direction": direction,  # 弧度制
                "last_update": time.time()  # 新增：记录上次更新时间
            })

        # 2. 对每个"未知"目标进行威胁评估
        evaluated_targets = []
        for target in potential_targets:
            distance = target['position']['y']
            
            # 将弧度转换为角度，并应用导航坐标系转换 (0-360度)
            direction_deg = (target['direction'] * 180 / np.pi) % 360
            
            # a. 计算距离分数 (0-1)
            distance_score = 1 - (distance / self.radar_range)
            
            # b. 连续变化的朝向分数：0度威胁最小，180度威胁最大
            heading_score = -np.cos(np.deg2rad(direction_deg))  # 范围从-1到1，180度时最大
            
            # c. 计算加权总分
            threat_score = (distance_score * self.DISTANCE_WEIGHT) + \
                          (heading_score * self.HEADING_WEIGHT)
            
            target['threat_score'] = threat_score
            evaluated_targets.append(target)
            
            # 调试打印详细的计算过程
            print(f"  [Threat Eval for {target['id']}]")
            print(f"    - Distance: {distance:.1f}nm -> Score: {distance_score:.2f}")
            print(f"    - Direction: {direction_deg:.1f}° -> Score: {heading_score:.2f} (0°最小威胁，180°最大威胁)")
            print(f"    - Weighted Score: ({distance_score:.2f}*{self.DISTANCE_WEIGHT}) + ({heading_score:.2f}*{self.HEADING_WEIGHT}) = {threat_score:.2f}")
            
        # 3. 根据威胁分数排序，分数最高的为敌机
        evaluated_targets.sort(key=lambda t: t['threat_score'], reverse=True)
        
        # 4. 分配最终的ID和类型
        final_targets = []
        for i, target in enumerate(evaluated_targets):
            if i < num_enemies:
                target['type'] = 'army'
                target['id'] = f"enemy-{i+1}"
            else:
                target['type'] = 'friend'
                target['id'] = f"friend-{i - num_enemies + 1}"
            
            # 新增：根据速度计算拖尾长度
            target['trail_length'] = target['speed'] * 2  # 拖尾长度与速度成正比，系数可调整
            
            # 预计算导航坐标系角度供前端使用
            target['direction_degrees'] = (target['direction'] * 180 / np.pi) % 360

            final_targets.append(target)
            
        self.unknown_targets = final_targets
        
        print(f"已初始化 {len(self.unknown_targets)} 个未知目标 (Difficulty: {difficulty_config.get('name')})")
        for target in self.unknown_targets:
            print(f"  -> ID: {target['id']}, Type: {target['type']}, Threat Score: {target['threat_score']:.2f}, "
                  f"Pos: ({target['position']['x']:.1f}°, {target['position']['y']:.1f}nm)")
    
    def update_targets(self) -> None:
        """更新所有目标的位置和朝向"""
        current_time = time.time()

        for target in self.unknown_targets:
            delta_t = current_time - target.get('last_update', current_time)
            
            # 简单的线性移动模型
            speed_x = target['speed'] * np.cos(target['direction']) * 0.1  # 减小横向移动幅度
            speed_y = target['speed'] * np.sin(target['direction']) * 0.1  # 减小纵向移动幅度
            
            target['position']['x'] += speed_x * delta_t
            target['position']['y'] -= speed_y * delta_t  # Y轴向下是距离减小
            
            # 随机轻微调整航向，模拟机动
            target['direction'] += random.uniform(-0.05, 0.05)
            
            # 确保航向在 [0, 2*pi] 范围内
            target['direction'] = target['direction'] % (2 * np.pi)
            
            # 将后端弧度转换为前端需要的导航坐标系角度（度数）
            target['direction_degrees'] = (target['direction'] * 180 / np.pi) % 360

            # 计算并更新相对航向
            own_heading_rad = np.deg2rad(self.own_heading)
            diff_rad = target['direction'] - own_heading_rad
            
            # 归一化到 [-pi, pi]
            if diff_rad > np.pi:
                diff_rad -= 2 * np.pi
            elif diff_rad < -np.pi:
                diff_rad += 2 * np.pi

            target['relative_heading'] = np.rad2deg(diff_rad)
            target['last_update'] = current_time
    
    def get_radar_data(self, include_targets: bool = False) -> Dict[str, Any]:
        """获取要发送给前端的雷达数据"""
        try:
            self.update_targets()
            
            print("【调试】开始生成雷达数据...")
            
            # 基础数据，不包含目标
            data = {
                "radar_azimuth": float(self.radar_azimuth),
                "own_heading": float(self.own_heading),
                "timestamp": time.time(),
                "range": float(self.radar_range),
                "scanAngle": float(self.scan_angle),
                "audioEnabled": True  # 这个值应该从配置中获取
            }
            
            # 仅当明确指定要包含目标时，才添加目标数据
            if include_targets:
                print("【调试】请求包含目标数据 - 正在验证格式")
                
                # 验证目标数据格式
                validated_targets = []
                for target in self.unknown_targets:
                    try:
                        if ("id" in target and 
                            "position" in target and 
                            isinstance(target["position"], dict) and
                            "x" in target["position"] and 
                            "y" in target["position"]):
                            validated_targets.append(target)
                        else:
                            print(f"【警告】跳过格式不正确的目标: {target}")
                    except Exception as e:
                        print(f"【错误】处理目标时出错: {e}")
                
                data["externalTargets"] = validated_targets
                print(f"【调试】添加目标数据到响应, 有效目标数量: {len(validated_targets)}")
            
            return data
        except Exception as e:
            print(f"【错误】生成雷达数据时出错: {e}")
            # 返回一个最小的有效数据结构
            return {
                "radar_azimuth": float(self.radar_azimuth),
                "own_heading": float(self.own_heading),
                "timestamp": time.time(),
                "range": float(self.radar_range),
                "scanAngle": float(self.scan_angle)
            }
    
    def should_include_targets(self, message: Dict[str, Any] = None) -> bool:
        """检查是否满足发送目标数据的条件"""
        print("\n【调试】===== 条件检查开始 =====")
        
        # 如果没有传入消息，使用全局变量
        if message is None:
            print("【调试】使用全局变量进行检查")
            scan_angle_value = self.scan_angle
            radar_range_value = self.radar_range
        else:
            print("【调试】使用消息中的参数进行检查")
            scan_angle_value = message.get('scanAngle')
            radar_range_value = message.get('range')
        
        print(f"【调试】当前参数: scan_angle={scan_angle_value} (类型: {type(scan_angle_value)}), radar_range={radar_range_value} (类型: {type(radar_range_value)})")
        
        # 使用更宽松的条件检查
        try:
            scan_angle_float = float(scan_angle_value)
            radar_range_float = float(radar_range_value)
            
            # 计算与设定值的差异百分比
            scan_angle_diff = abs(scan_angle_float - 30) / 30 * 100  # 30是设定值
            range_diff = abs(radar_range_float - 80) / 80 * 100     # 80是设定值
            
            # 允许2%的误差
            scan_angle_condition = scan_angle_diff <= 2
            range_condition = range_diff <= 2
            
            print(f"【调试】参数值: scan_angle={scan_angle_float}, range={radar_range_float}")
            print(f"【调试】差异百分比: scan_angle={scan_angle_diff:.2f}%, range={range_diff:.2f}%")
            print(f"【调试】条件判断: scan_angle条件={scan_angle_condition}, range条件={range_condition}")
            
            result = scan_angle_condition and range_condition
            print(f"【调试】最终结果: {result}")
            
            if result:
                print("【调试】✅ 满足条件，将发送目标数据")
                print("【调试】unknown_targets 长度:", len(self.unknown_targets))
            else:
                print("【调试】❌ 不满足条件，不发送目标数据")
            
        except (ValueError, TypeError) as e:
            print(f"【错误】条件检查出错: {e}")
            result = False
        
        print("【调试】===== 条件检查结束 =====\n")
        return result
    
    def get_targets(self) -> List[Dict[str, Any]]:
        """获取当前所有目标"""
        return self.unknown_targets

# 全局目标管理器实例
target_manager = TargetManager() 