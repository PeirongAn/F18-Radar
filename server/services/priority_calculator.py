#!/usr/bin/env python3
"""
优先级计算服务
将前端SAPage.tsx中的威胁优先级计算逻辑迁移到服务端
"""

import math
from typing import List, Dict, Any, Tuple, Optional
from models.threat_models import RadarConfig, ThreatPosition, EnhancedThreat

class PriorityCalculator:
    """威胁优先级计算器"""
    
    def __init__(self):
        # 威胁类型权重定义（与前端SAPage.tsx保持一致）
        self.TYPE_WEIGHTS = {
            'missile': 245,           # 来袭导弹 - 最高优先级（与前端一致）
            'Primary': 240,           # 一级威胁 - 高危险单位  
            'Secondary': 200,         # 二级威胁 - 次要威胁单位
            'default': 80             # 其他未知类型
        }
    
    def calculate_threat_scores(
        self,
        threats_with_positions: List[Tuple[Dict[str, Any], ThreatPosition]],
        radar_config: RadarConfig,
        difficulty_config: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        计算威胁分数，复制前端threatsWithScore的逻辑
        
        Args:
            threats_with_positions: 威胁和位置的元组列表
            radar_config: 雷达配置
            difficulty_config: 难度配置，用于调整威胁值差异
            
        Returns:
            包含分数的威胁信息列表
        """
        effective_center_y = radar_config.center_y - 50
        threats_with_score = []
        raw_scores = []
        
        # 根据难度调整威胁值差异
        difficulty_factor = self._get_difficulty_factor(difficulty_config)
        
        print(f"[优先级计算] 开始计算 {len(threats_with_positions)} 个威胁的优先级...")
        print(f"[优先级计算] 难度系数: {difficulty_config.get('name')} {difficulty_factor:.2f} ({'高难度-小差异' if difficulty_factor < 1.0 else '低难度-大差异'})")
        
        # 1. 计算所有威胁的原始分数
        for i, (threat, position) in enumerate(threats_with_positions):
            # 威胁图标的中心点位置（黄色圆点位置）
            threat_center_x = position.x
            threat_center_y = position.y
            
            # 计算距离雷达中心的距离
            distance = math.sqrt(
                (threat_center_x - radar_config.center_x) ** 2 + 
                (threat_center_y - effective_center_y) ** 2
            )
            
            # 获取威胁类型权重（考虑难度调整）
            weight = self._get_type_weight(threat['type'], difficulty_factor)
            
            # 计算原始分数：权重 / 距离
            raw_score = weight / max(distance, 1)  # 避免除零
            raw_scores.append(raw_score)
            
            print(f"  威胁 {threat['id']}: 距离={distance:.1f}, 权重={weight}, 原始分数={raw_score:.2f}")
        
        # 2. 找到最大分数用于归一化
        max_score = max(raw_scores) if raw_scores else 1
        print(f"[优先级计算] 最大原始分数: {max_score:.2f}")
        
        # 3. 生成归一化后的威胁信息
        for i, (threat, position) in enumerate(threats_with_positions):
            # 归一化分数
            normalized_score = round(raw_scores[i] / max_score, 2)
            
            # 判断是否为导弹
            is_missile = 'missile' in threat['type'].lower()
            
            # 计算距离中心的距离
            threat_center_x = position.x
            threat_center_y = position.y
            distance_from_center = math.sqrt(
                (threat_center_x - radar_config.center_x) ** 2 +
                (threat_center_y - effective_center_y) ** 2
            )
            
            # 确定优先级
            priority = self._determine_priority(threat['type'])
            
            threat_with_score = {
                'threat': threat,
                'position': position,
                'score': normalized_score,
                'is_missile': is_missile,
                'distance_from_center': distance_from_center,
                'priority': priority,
                'original_index': i  # 用于打破平局的原始索引
            }
            
            threats_with_score.append(threat_with_score)
            print(f"  最终 {threat['id']}: 分数={normalized_score}, 优先级={priority}")
        
        # 4. 排序威胁（复制前端排序逻辑）
        # sorted_threats = self._sort_threats_by_priority(threats_with_score)
        
        # return sorted_threats
        return threats_with_score
    
    def sort_threats_by_priority(self, threats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        按优先级排序威胁
        复制前端的排序逻辑：分数 > 导弹类型 > 原始索引
        """
        return self._sort_threats_by_priority(threats)
    
    def get_highest_priority_threat(self, threats: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        获取最高优先级威胁
        
        Args:
            threats: 威胁列表
            
        Returns:
            最高优先级威胁，如果没有威胁则返回None
        """
        if not threats:
            return None
            
        sorted_threats = self._sort_threats_by_priority(threats)
        highest_threat = sorted_threats[0] if sorted_threats else None
        
        if highest_threat:
            print(f"[优先级计算] 最高优先级威胁: {highest_threat['threat']['id']}, 分数: {highest_threat['score']}")
        
        return highest_threat
    
    def create_enhanced_threats(
        self,
        threats_with_scores: List[Dict[str, Any]],
        radar_config: RadarConfig
    ) -> List[EnhancedThreat]:
        """
        创建增强威胁对象列表
        
        Args:
            threats_with_scores: 包含分数的威胁列表
            radar_config: 雷达配置
            
        Returns:
            增强威胁对象列表
        """
        enhanced_threats = []
        
        for threat_info in threats_with_scores:
            threat = threat_info['threat']
            position = threat_info['position']
            
            # 处理导弹类型
            missile_type = None
            if threat_info['is_missile']:
                if 'MissileUp' in threat.get('type', ''):
                    missile_type = 'MissileUp'
                elif 'MissileDown' in threat.get('type', ''):
                    missile_type = 'MissileDown'
            
            enhanced_threat = EnhancedThreat(
                id=threat['id'],
                type=threat['type'],
                label=threat['label'],
                position=position,
                priority=threat_info['priority'],
                score=threat_info['score'],
                distance_from_center=threat_info['distance_from_center'],
                is_missile=threat_info['is_missile'],
                missile_type=missile_type
            )
            
            enhanced_threats.append(enhanced_threat)
        
        return enhanced_threats
    
    def _get_type_weight(self, threat_type: str, difficulty_factor: float = 1.0) -> int:
        """
        获取威胁类型权重（考虑难度调整）
        
        Args:
            threat_type: 威胁类型
            difficulty_factor: 难度系数（<1.0为高难度，>1.0为低难度）
        
        Returns:
            调整后的权重值
        """
        threat_type_lower = threat_type.lower()
        
        # 获取基础权重
        if 'missile' in threat_type_lower:
            base_weight = self.TYPE_WEIGHTS['missile']
        elif threat_type.startswith('Primary'):
            base_weight = self.TYPE_WEIGHTS['Primary']
        elif threat_type.startswith('Secondary'):
            base_weight = self.TYPE_WEIGHTS['Secondary']
        else:
            base_weight = self.TYPE_WEIGHTS['default']
        
        # 根据难度调整权重
        if difficulty_factor < 1.0:
            # 高难度：缩小权重差异，让分数更接近
            # 将所有权重向中等值（200）靠拢
            adjusted_weight = base_weight * difficulty_factor + 200 * (1 - difficulty_factor)
        else:
            # 低难度：保持或增大权重差异
            adjusted_weight = base_weight * difficulty_factor
        
        return int(adjusted_weight)
    
    def _determine_priority(self, threat_type: str) -> str:
        """确定威胁优先级"""
        if 'missile' in threat_type.lower():
            return 'high'
        elif threat_type.startswith('Primary'):
            return 'high'
        elif threat_type.startswith('Secondary'):
            return 'medium'
        else:
            return 'low'
    
    def _sort_threats_by_priority(self, threats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        排序威胁逻辑（复制前端逻辑）
        排序规则：分数降序 > 导弹类型优先 > 原始索引升序
        """
        def sort_key(threat_info):
            score = threat_info['score']
            is_missile = threat_info['is_missile']
            original_index = threat_info['original_index']
            
            # 返回排序元组：(负分数用于降序, 导弹类型倒序优先, 原始索引升序)
            return (-score, not is_missile, original_index)
        
        sorted_threats = sorted(threats, key=sort_key)
        
        # 打印排序结果
        print(f"[优先级计算] 威胁排序结果:")
        for i, threat_info in enumerate(sorted_threats):
            threat = threat_info['threat']
            print(f"  {i+1}. {threat['id']}: 分数={threat_info['score']}, 导弹={threat_info['is_missile']}")
        
        return sorted_threats
    
    def _get_difficulty_factor(self, difficulty_config: Optional[Dict[str, Any]]) -> float:
        """
        根据难度配置计算难度系数
        
        Args:
            difficulty_config: 难度配置
            
        Returns:
            难度系数：
            - < 1.0: 高难度，威胁值差异小
            - = 1.0: 中等难度，保持原有差异
            - > 1.0: 低难度，威胁值差异大
        """
        if not difficulty_config:
            return 1.0  # 默认中等难度
        
        difficulty_name = difficulty_config.get('name', '').lower()
        
        # 根据难度名称映射系数
        difficulty_mapping = {
            'low': 1.3,      # 低难度：增大差异30%
            'normal': 1.0,    # 中等难度：保持原有差异
            # 'hard': 0.7,      # 高难度：缩小差异30%
            # 'expert': 0.5,    # 专家难度：缩小差异50%
            'high': 0.7    # 大师难度：缩小差异70%
        }
        
        # 支持中文难度名称
        chinese_mapping = {
            '低': 1.3,
            '中': 1.0,
            # '困难': 0.7,
            # '专家': 0.5,
            '高': 0.6
        }
        
        # 优先使用英文映射，然后中文映射
        factor = difficulty_mapping.get(difficulty_name)
        if factor is None:
            factor = chinese_mapping.get(difficulty_name, 1.0)
        
        print(f"[难度调整] 难度: {difficulty_config.get('name')}, 系数: {factor}")
        return factor

# 全局优先级计算器实例 
priority_calculator = PriorityCalculator() 