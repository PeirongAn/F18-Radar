#!/usr/bin/env python3
"""
位置计算服务
将前端SAPage.tsx中的位置计算逻辑迁移到服务端
"""

import random
import math
from typing import List, Dict, Tuple, Any
from models.threat_models import RadarConfig, ThreatPosition, EnhancedThreat

class PositionCalculator:
    """威胁位置计算器"""
    
    def __init__(self):
        self.ICON_SIZE = 48  # 图标大小，与前端保持一致
    
    def calculate_threat_positions(
        self, 
        threats: List[Dict[str, Any]], 
        radar_config: RadarConfig
    ) -> List[ThreatPosition]:
        """
        计算威胁位置，复制前端iconPositions的逻辑
        
        Args:
            threats: 基础威胁数据列表
            radar_config: 雷达配置参数
            
        Returns:
            计算好的位置列表
        """
        positions = []
        effective_center_y = radar_config.center_y - 50  # 与前端保持一致
        
        # 完全模拟前端逻辑：统一处理所有威胁，而不是分别处理Primary和Secondary
        print(f"[位置计算] 统一处理所有威胁，总数: {len(threats)}")
        print(f"[位置计算] 雷达配置: 中心({radar_config.center_x}, {radar_config.center_y}), radius2={radar_config.radius2}, radius3={radar_config.radius3}")
        print(f"[位置计算] Canvas尺寸: {radar_config.canvas_width}x{radar_config.canvas_height}")
        print(f"[位置计算] 第2个圆中心: ({radar_config.center_x}, {effective_center_y})")
        print(f"[位置计算] 威胁分布策略: 交替在radius2({radar_config.radius2})和radius2+50({radar_config.radius2+50})两个半径上")
        
        # 模拟前端 saThreats.map((threat: any, index: number) => {
        for index, threat in enumerate(threats):
            # 基础角度分布（均匀分布）+ 随机偏移
            base_angle = (index / len(threats)) * 2 * math.pi
            # 添加随机角度偏移（±30度范围内）
            angle_offset = (random.random() - 0.5) * math.pi / 3  # ±π/6 = ±30度
            angle = base_angle + angle_offset
            
            # 基础半径分布（交替） + 随机偏移
            base_radius = radar_config.radius2 + (index % 2) * 50
            # 添加随机半径偏移（±15px范围内）
            radius_offset = (random.random() - 0.5) * 30  # ±15px
            r = base_radius + radius_offset
            
            # 确保半径在合理范围内（不能太靠近中心或太远）
            min_radius = radar_config.radius2 - 20
            max_radius = radar_config.radius2 + 70
            r = max(min_radius, min(max_radius, r))
            
            # 计算威胁图标中心点应该在的理论位置
            ideal_center_x = radar_config.center_x + r * math.cos(angle)
            ideal_center_y = effective_center_y + r * math.sin(angle)
            
            # 从中心点计算图标左上角位置
            x = ideal_center_x - self.ICON_SIZE / 2
            y = ideal_center_y - self.ICON_SIZE / 2
            
            # 边界检查，确保图标完全在Canvas内
            clamped_x = max(self.ICON_SIZE, min(radar_config.canvas_width - self.ICON_SIZE, x))
            clamped_y = max(self.ICON_SIZE, min(radar_config.canvas_height - self.ICON_SIZE, y))
            
            # 检测与已有威胁的碰撞，如果碰撞则微调位置
            pos = ThreatPosition(x=clamped_x, y=clamped_y)
            max_collision_attempts = 5
            collision_attempt = 0
            
            while collision_attempt < max_collision_attempts and self.detect_collision(pos, positions):
                # 微调角度来避免碰撞
                angle += math.pi / 8  # 22.5度增量
                ideal_center_x = radar_config.center_x + r * math.cos(angle)
                ideal_center_y = effective_center_y + r * math.sin(angle)
                
                x = ideal_center_x - self.ICON_SIZE / 2
                y = ideal_center_y - self.ICON_SIZE / 2
                
                clamped_x = max(self.ICON_SIZE, min(radar_config.canvas_width - self.ICON_SIZE, x))
                clamped_y = max(self.ICON_SIZE, min(radar_config.canvas_height - self.ICON_SIZE, y))
                
                pos = ThreatPosition(x=clamped_x, y=clamped_y)
                collision_attempt += 1
            
            # 计算实际的威胁中心点位置（可能因边界检查而偏移）
            actual_center_x = clamped_x 
            actual_center_y = clamped_y
            
            # 计算实际距离（用于验证）
            actual_distance = math.sqrt((actual_center_x - radar_config.center_x)**2 + 
                                      (actual_center_y - effective_center_y)**2)
            
            positions.append(pos)
            
            print(f"  威胁{index} {threat['id']}: 随机半径={r:.1f}, 实际距离={actual_distance:.1f}, 位置=({clamped_x:.1f}, {clamped_y:.1f})")
            
            # 如果发生碰撞处理，记录日志
            if collision_attempt > 0:
                print(f"    🔄 碰撞处理: 进行了{collision_attempt}次位置调整")
            
            # 如果边界检查导致偏移，发出警告
            if abs(actual_distance - r) > 2.0:
                print(f"    ⚠️  警告: 边界检查导致距离偏移 {abs(actual_distance - r):.1f}px")
        
        return positions
    
    def calculate_missile_position(
        self, 
        missile_type: str, 
        radar_config: RadarConfig
    ) -> ThreatPosition:
        """
        计算导弹位置，复制前端导弹位置生成逻辑
        
        Args:
            missile_type: 导弹类型 ('MissileUp' 或 'MissileDown')
            radar_config: 雷达配置
            
        Returns:
            导弹位置
        """
        effective_center_y = radar_config.center_y - 50
        max_attempts = 10
        
        for attempt in range(max_attempts):
            # 导弹可以在整个360度范围内出现，但更倾向于上半圆区域
            if random.random() < 0.7:
                # 70%概率在上半圆
                angle = -math.pi + random.random() * math.pi  # -π到0
            else:
                # 30%概率在任意位置
                angle = random.random() * math.pi * 2
            
            # 完全模拟前端导弹逻辑
            # const r = radius2 + Math.random() * (radius3 - radius2) * 0.8;
            effective_center_y = radar_config.center_y - 50  # 第2个圆的中心Y
            r = radar_config.radius2 + random.random() * (radar_config.radius3 - radar_config.radius2) * 0.8
            
            # 模拟前端逻辑
            # const rawX = config.centerX + r * Math.cos(angle);
            # const rawY = effectiveCenterY + r * Math.sin(angle);
            raw_x = radar_config.center_x + r * math.cos(angle)
            raw_y = effective_center_y + r * math.sin(angle)
            
            # 模拟前端边界检查逻辑
            # const x = Math.max(missileSize, Math.min(width - missileSize, rawX));
            # const y = Math.max(missileSize, Math.min(height - missileSize, rawY));
            missile_size = 30  # 导弹图标大小
            x = max(missile_size, min(radar_config.canvas_width - missile_size, raw_x))
            y = max(missile_size, min(radar_config.canvas_height - missile_size, raw_y))
            
            position = ThreatPosition(x=x, y=y)
            print(f"[导弹位置] {missile_type} 成功生成: ({x:.1f}, {y:.1f}), 半径: {r:.1f}")
            return position
        
        # 如果多次尝试都失败，返回一个安全位置
        safe_r = radar_config.radius2 + (radar_config.radius3 - radar_config.radius2) * 0.4
        safe_x = radar_config.center_x + safe_r * math.cos(math.pi/4)
        safe_y = effective_center_y + safe_r * math.sin(math.pi/4)
        safe_x = max(30, min(radar_config.canvas_width - 30, safe_x))
        safe_y = max(30, min(radar_config.canvas_height - 30, safe_y))
        print(f"[导弹位置] {missile_type} 使用安全位置: ({safe_x:.1f}, {safe_y:.1f})")
        return ThreatPosition(x=safe_x, y=safe_y)
    
    def detect_collision(
        self, 
        new_pos: ThreatPosition, 
        existing_positions: List[ThreatPosition], 
        min_distance: float = None
    ) -> bool:
        """
        检测位置冲突
        
        Args:
            new_pos: 新位置
            existing_positions: 已有位置列表
            min_distance: 最小距离，默认为图标大小*1.2
            
        Returns:
            bool: 如果发生冲突返回True，否则返回False
        """
        if min_distance is None:
            min_distance = self.ICON_SIZE * 1.2
        
        for existing_pos in existing_positions:
            distance = math.sqrt(
                (new_pos.x - existing_pos.x) ** 2 + 
                (new_pos.y - existing_pos.y) ** 2
            )
            if distance < min_distance:
                return True
        return False

# 全局位置计算器实例
position_calculator = PositionCalculator() 