#!/usr/bin/env python3
"""
测试难度调整对威胁值差异的影响
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.priority_calculator import priority_calculator
from models.threat_models import RadarConfig, ThreatPosition

def test_difficulty_adjustment():
    """测试不同难度下的威胁分数差异"""
    
    # 创建测试配置
    radar_config = RadarConfig(
        center_x=400.0,
        center_y=360.0,
        radius1=100.0,
        radius2=180.0,
        radius3=306.0,
        canvas_width=800.0,
        canvas_height=600.0
    )
    
    # 创建测试威胁和位置
    test_threats = [
        {'id': 'primary_1', 'type': 'PrimaryAir'},
        {'id': 'secondary_1', 'type': 'SecondaryAir'},
        {'id': 'missile_1', 'type': 'MissileUp'}
    ]
    
    test_positions = [
        ThreatPosition(x=350, y=310),  # Primary威胁位置
        ThreatPosition(x=400, y=350),  # Secondary威胁位置
        ThreatPosition(x=450, y=320)   # 导弹位置
    ]
    
    threats_with_positions = list(zip(test_threats, test_positions))
    
    # 测试不同难度
    difficulties = [
        {'name': 'easy'},
        {'name': 'normal'},
        {'name': 'hard'},
        {'name': 'expert'}
    ]
    
    print("🎯 威胁分数差异测试\n")
    
    for difficulty in difficulties:
        print(f"📊 难度: {difficulty['name'].upper()}")
        
        # 计算威胁分数
        threats_with_scores = priority_calculator.calculate_threat_scores(
            threats_with_positions, radar_config, difficulty
        )
        
        # 提取分数并计算差异
        scores = [t['score'] for t in threats_with_scores]
        max_score = max(scores)
        min_score = min(scores)
        score_diff = max_score - min_score
        
        print(f"  分数范围: {min_score:.3f} ~ {max_score:.3f}")
        print(f"  分数差异: {score_diff:.3f}")
        print(f"  详细分数:")
        
        for threat_info in threats_with_scores:
            threat = threat_info['threat']
            score = threat_info['score']
            print(f"    {threat['type']}: {score:.3f}")
        
        print("-" * 40)

if __name__ == "__main__":
    test_difficulty_adjustment() 