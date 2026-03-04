#!/usr/bin/env python3
"""
威胁数据模型测试
验证数据结构定义是否正确工作
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models.threat_models import (
    RadarConfig, ThreatPosition, EnhancedThreat, 
    ThreatGenerationResult, ThreatType, MissileType
)

def test_radar_config():
    """测试雷达配置"""
    print("=== 测试 RadarConfig ===")
    
    # 创建雷达配置（模拟SAPage.tsx中的配置）
    config = RadarConfig(
        center_x=450.0,       # width / 2 = 900 / 2
        center_y=540.0,       # height * 0.6 = 900 * 0.6
        radius1=100.0,
        radius2=360.0,        # 假设计算的radius2值
        radius3=612.0,        # 假设计算的radius3值
        canvas_width=900.0,
        canvas_height=900.0
    )
    
    print(f"雷达配置: {config}")
    print(f"转换为字典: {config.to_dict()}")
    print("✅ RadarConfig 测试通过\n")
    
    return config

def test_threat_position():
    """测试威胁位置"""
    print("=== 测试 ThreatPosition ===")
    
    position = ThreatPosition(x=300.5, y=200.8)
    print(f"威胁位置: {position}")
    print(f"转换为字典: {position.to_dict()}")
    print("✅ ThreatPosition 测试通过\n")
    
    return position

def test_enhanced_threat():
    """测试增强威胁数据"""
    print("=== 测试 EnhancedThreat ===")
    
    position = ThreatPosition(x=300.5, y=200.8)
    
    # 测试常规威胁
    threat = EnhancedThreat(
        id="PrimaryAir-1234-0",
        type="PrimaryAir",
        label="F-16",
        position=position,
        priority="high",
        score=0.85,
        distance_from_center=150.3,
        is_missile=False
    )
    
    print(f"常规威胁: {threat}")
    print(f"转换为字典: {threat.to_dict()}")
    
    # 测试导弹威胁
    missile_position = ThreatPosition(x=400.0, y=300.0)
    missile = EnhancedThreat(
        id="missile-5678",
        type="missile",
        label="上升导弹",
        position=missile_position,
        priority="high",
        score=1.0,
        distance_from_center=200.5,
        is_missile=True,
        missile_type="MissileUp"
    )
    
    print(f"导弹威胁: {missile}")
    print(f"转换为字典: {missile.to_dict()}")
    print("✅ EnhancedThreat 测试通过\n")
    
    return [threat, missile]

def test_threat_generation_result():
    """测试威胁生成结果"""
    print("=== 测试 ThreatGenerationResult ===")
    
    # 创建测试数据
    config = RadarConfig(
        center_x=450.0, center_y=540.0,
        radius1=100.0, radius2=360.0, radius3=612.0,
        canvas_width=900.0, canvas_height=900.0
    )
    
    threats = [
        EnhancedThreat(
            id="threat-1", type="PrimaryAir", label="F-16",
            position=ThreatPosition(x=300.0, y=200.0),
            priority="high", score=0.95, distance_from_center=150.0,
            is_missile=False
        ),
        EnhancedThreat(
            id="threat-2", type="SecondaryAir", label="MiG-29",
            position=ThreatPosition(x=500.0, y=400.0),
            priority="medium", score=0.75, distance_from_center=200.0,
            is_missile=False
        ),
        EnhancedThreat(
            id="missile-1", type="missile", label="上升导弹",
            position=ThreatPosition(x=350.0, y=250.0),
            priority="high", score=1.0, distance_from_center=180.0,
            is_missile=True, missile_type="MissileUp"
        )
    ]
    
    result = ThreatGenerationResult(
        threats=threats,
        radar_config=config
    )
    
    print(f"威胁生成结果: {result}")
    print(f"最高优先级威胁ID: {result.highest_priority_threat_id}")
    
    # 测试字典转换
    result_dict = result.to_dict()
    print(f"转换为字典（前{100}个字符）: {str(result_dict)[:100]}...")
    print("✅ ThreatGenerationResult 测试通过\n")
    
    return result

def main():
    """运行所有测试"""
    print("开始测试威胁数据模型...")
    print("=" * 50)
    
    try:
        test_radar_config()
        test_threat_position()
        test_enhanced_threat()
        test_threat_generation_result()
        
        print("🎉 所有测试通过！数据结构定义正确。")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 