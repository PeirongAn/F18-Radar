#!/usr/bin/env python3
"""
测试导弹威胁分数归一化计算
验证导弹威胁生成后是否正确参与了分数归一化计算
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models.threat_models import EnhancedThreat, RadarConfig, ThreatPosition
from managers.threat_manager import ThreatManager
from services.position_calculator import position_calculator
from services.priority_calculator import priority_calculator

def test_missile_score_normalization():
    """测试导弹威胁分数归一化"""
    print("🧪 测试导弹威胁分数归一化计算")
    print("=" * 60)
    
    # 创建威胁管理器
    threat_manager = ThreatManager()
    
    # 创建雷达配置
    radar_config = RadarConfig(
        center_x=400.0,
        center_y=360.0,
        radius1=100.0,
        radius2=180.0,
        radius3=306.0,
        canvas_width=800.0,
        canvas_height=600.0
    )
    
    # 创建一些基础威胁
    base_threats = [
        EnhancedThreat(
            id="threat_1",
            type="PrimaryAircraft",
            label="敌机A",
            position=ThreatPosition(x=300, y=200),
            priority="high",
            score=0,
            distance_from_center=0,
            is_missile=False,
            missile_type=None
        ),
        EnhancedThreat(
            id="threat_2", 
            type="SecondaryShip",
            label="敌舰B",
            position=ThreatPosition(x=500, y=300),
            priority="medium",
            score=0,
            distance_from_center=0,
            is_missile=False,
            missile_type=None
        )
    ]
    
    print(f"📊 基础威胁数量: {len(base_threats)}")
    for threat in base_threats:
        print(f"  - {threat.id}: {threat.type} (原始分数: {threat.score})")
    
    print("\n🚀 生成导弹事件...")
    
    # 生成导弹紧急事件
    emergency_msg = threat_manager.generate_enhanced_sa_emergency(base_threats, radar_config)
    
    print(f"📨 紧急事件类型: {emergency_msg.get('event', 'unknown')}")
    
    # 获取更新后的威胁列表
    updated_threats = emergency_msg.get('enhanced_data', {}).get('updated_threats', [])
    missile_threat = emergency_msg.get('enhanced_data', {}).get('missile_threat')
    
    print(f"\n📊 更新后威胁数量: {len(updated_threats)}")
    print("📋 重新定位的威胁:")
    for threat in updated_threats:
        print(f"  - {threat['id']}: {threat['type']} -> 分数: {threat['score']:.2f}, 距离: {threat['distance_from_center']:.1f}")
    
    if missile_threat:
        print(f"\n🎯 导弹威胁:")
        print(f"  - {missile_threat['id']}: {missile_threat['type']} -> 分数: {missile_threat['score']:.2f}, 距离: {missile_threat['distance_from_center']:.1f}")
    
    # 验证分数归一化
    print(f"\n🔍 分数归一化验证:")
    
    # 收集所有威胁的分数
    all_scores = []
    for threat in updated_threats:
        all_scores.append(threat['score'])
    if missile_threat:
        all_scores.append(missile_threat['score'])
    
    if all_scores:
        min_score = min(all_scores)
        max_score = max(all_scores)
        score_range = max_score - min_score
        
        print(f"  - 最低分数: {min_score:.2f}")
        print(f"  - 最高分数: {max_score:.2f}")
        print(f"  - 分数范围: {score_range:.2f}")
        
        # 检查分数是否在合理范围内（0-100）
        if all(0 <= score <= 100 for score in all_scores):
            print("  ✅ 所有分数都在0-100范围内")
        else:
            print("  ❌ 存在超出0-100范围的分数")
        
        # 检查分数是否有合理的差异
        if score_range > 0:
            print("  ✅ 威胁分数存在差异，归一化生效")
        else:
            print("  ⚠️  所有威胁分数相同，可能归一化有问题")
    
    print("\n" + "=" * 60)
    print("✅ 导弹威胁分数归一化测试完成")

if __name__ == "__main__":
    test_missile_score_normalization() 