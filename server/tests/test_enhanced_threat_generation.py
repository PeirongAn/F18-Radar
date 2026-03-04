#!/usr/bin/env python3
"""
增强威胁生成测试
验证服务端核心算法迁移是否正确工作
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models.threat_models import RadarConfig
from services.position_calculator import position_calculator
from services.priority_calculator import priority_calculator
from managers.threat_manager import threat_manager

def test_position_calculator():
    """测试位置计算器"""
    print("=== 测试位置计算器 ===")
    
    # 创建模拟雷达配置（基于SAPage.tsx的配置）
    radar_config = RadarConfig(
        center_x=450.0,       # width / 2 = 900 / 2
        center_y=540.0,       # height * 0.6 = 900 * 0.6
        radius1=100.0,
        radius2=270.0,        # 底部线位置 - center_y = 810 - 540 = 270
        radius3=459.0,        # radius2 * 1.7 = 270 * 1.7
        canvas_width=900.0,
        canvas_height=900.0
    )
    
    # 创建测试威胁数据
    test_threats = [
        {'id': 'PrimaryAir-1234', 'type': 'PrimaryAir', 'label': 'F-16'},
        {'id': 'SecondaryAir-5678', 'type': 'SecondaryAir', 'label': 'MiG-29'},
        {'id': 'PrimaryNaval-9999', 'type': 'PrimaryNaval', 'label': '052D'},
        {'id': 'SecondaryNaval-8888', 'type': 'SecondaryNaval', 'label': '056'}
    ]
    
    # 计算位置
    positions = position_calculator.calculate_threat_positions(test_threats, radar_config)
    
    print(f"计算了 {len(positions)} 个位置:")
    for i, (threat, pos) in enumerate(zip(test_threats, positions)):
        print(f"  {threat['id']} ({threat['type']}): ({pos.x:.1f}, {pos.y:.1f})")
        
        # 验证位置在合理范围内
        assert 0 <= pos.x <= radar_config.canvas_width, f"X坐标超出范围: {pos.x}"
        assert 0 <= pos.y <= radar_config.canvas_height, f"Y坐标超出范围: {pos.y}"
    
    print("✅ 位置计算器测试通过\n")
    return test_threats, positions, radar_config

def test_missile_position():
    """测试导弹位置计算"""
    print("=== 测试导弹位置计算 ===")
    
    radar_config = RadarConfig(
        center_x=450.0, center_y=540.0,
        radius1=100.0, radius2=270.0, radius3=459.0,
        canvas_width=900.0, canvas_height=900.0
    )
    
    # 测试上升导弹
    missile_up_pos = position_calculator.calculate_missile_position("MissileUp", radar_config)
    print(f"上升导弹位置: ({missile_up_pos.x:.1f}, {missile_up_pos.y:.1f})")
    
    # 测试下降导弹
    missile_down_pos = position_calculator.calculate_missile_position("MissileDown", radar_config)
    print(f"下降导弹位置: ({missile_down_pos.x:.1f}, {missile_down_pos.y:.1f})")
    
    # 验证导弹位置在合理范围内
    for pos, name in [(missile_up_pos, "上升导弹"), (missile_down_pos, "下降导弹")]:
        assert 30 <= pos.x <= radar_config.canvas_width - 30, f"{name} X坐标超出安全范围: {pos.x}"
        assert 30 <= pos.y <= radar_config.canvas_height - 30, f"{name} Y坐标超出安全范围: {pos.y}"
    
    print("✅ 导弹位置计算测试通过\n")
    return missile_up_pos, missile_down_pos

def test_priority_calculator():
    """测试优先级计算器"""
    print("=== 测试优先级计算器 ===")
    
    # 使用之前的测试数据
    test_threats, positions, radar_config = test_position_calculator()
    
    # 组合威胁和位置
    threats_with_positions = list(zip(test_threats, positions))
    
    # 计算优先级
    threats_with_scores = priority_calculator.calculate_threat_scores(
        threats_with_positions, radar_config
    )
    
    print(f"计算了 {len(threats_with_scores)} 个威胁的优先级:")
    for threat_info in threats_with_scores:
        threat = threat_info['threat']
        print(f"  {threat['id']}: 分数={threat_info['score']}, 优先级={threat_info['priority']}, 距离={threat_info['distance_from_center']:.1f}")
        
        # 验证分数在合理范围内
        assert 0 <= threat_info['score'] <= 1.0, f"分数超出范围: {threat_info['score']}"
        assert threat_info['priority'] in ['high', 'medium', 'low'], f"优先级无效: {threat_info['priority']}"
    
    # 测试获取最高优先级威胁
    highest_threat = priority_calculator.get_highest_priority_threat(threats_with_scores)
    if highest_threat:
        print(f"最高优先级威胁: {highest_threat['threat']['id']}, 分数: {highest_threat['score']}")
    
    print("✅ 优先级计算器测试通过\n")
    return threats_with_scores

def test_enhanced_threat_manager():
    """测试增强威胁管理器"""
    print("=== 测试增强威胁管理器 ===")
    
    # 创建难度配置
    difficulty_config = {
        'name': 'test',
        'threat_count': 3
    }
    
    # 创建雷达配置
    radar_config = RadarConfig(
        center_x=450.0, center_y=540.0,
        radius1=100.0, radius2=270.0, radius3=459.0,
        canvas_width=900.0, canvas_height=900.0
    )
    
    # 生成增强威胁
    threat_result = threat_manager.generate_enhanced_sa_threats(
        difficulty_config, radar_config
    )
    
    print(f"生成结果:")
    print(f"  威胁数量: {len(threat_result.threats)}")
    print(f"  最高优先级威胁ID: {threat_result.highest_priority_threat_id}")
    print(f"  生成时间戳: {threat_result.generation_timestamp}")
    
    # 验证每个威胁
    for i, threat in enumerate(threat_result.threats):
        print(f"  威胁 {i+1}: {threat.id} ({threat.type}) - 分数: {threat.score}, 位置: ({threat.position.x:.1f}, {threat.position.y:.1f})")
        
        # 验证威胁数据完整性
        assert threat.id, "威胁ID不能为空"
        assert threat.type, "威胁类型不能为空"
        assert threat.label, "威胁标签不能为空"
        assert threat.priority in ['high', 'medium', 'low'], f"优先级无效: {threat.priority}"
        assert 0 <= threat.score <= 1.0, f"分数超出范围: {threat.score}"
        assert 0 <= threat.position.x <= radar_config.canvas_width, f"X坐标超出范围: {threat.position.x}"
        assert 0 <= threat.position.y <= radar_config.canvas_height, f"Y坐标超出范围: {threat.position.y}"
    
    # 测试字典转换
    result_dict = threat_result.to_dict()
    assert 'threats' in result_dict, "缺少威胁数据"
    assert 'radar_config' in result_dict, "缺少雷达配置"
    assert 'highest_priority_threat_id' in result_dict, "缺少最高优先级威胁ID"
    
    print("✅ 增强威胁管理器测试通过\n")
    return threat_result

def test_enhanced_missile_generation():
    """测试增强导弹生成"""
    print("=== 测试增强导弹生成 ===")
    
    radar_config = RadarConfig(
        center_x=450.0, center_y=540.0,
        radius1=100.0, radius2=270.0, radius3=459.0,
        canvas_width=900.0, canvas_height=900.0
    )
    
    # 测试上升导弹生成
    missile_up = threat_manager.generate_enhanced_missile_threat("MissileUp", radar_config)
    print(f"上升导弹: {missile_up.id}, 位置: ({missile_up.position.x:.1f}, {missile_up.position.y:.1f})")
    
    # 测试下降导弹生成
    missile_down = threat_manager.generate_enhanced_missile_threat("MissileDown", radar_config)
    print(f"下降导弹: {missile_down.id}, 位置: ({missile_down.position.x:.1f}, {missile_down.position.y:.1f})")
    
    # 验证导弹数据
    for missile, name in [(missile_up, "上升导弹"), (missile_down, "下降导弹")]:
        assert missile.is_missile, f"{name} 应该标记为导弹"
        assert missile.priority == "high", f"{name} 应该是高优先级"
        assert missile.score == 1.0, f"{name} 应该有最高分数"
        assert missile.missile_type is not None, f"{name} 应该有导弹类型"
    
    print("✅ 增强导弹生成测试通过\n")
    return missile_up, missile_down

def main():
    """运行所有测试"""
    print("开始测试增强威胁生成系统...")
    print("=" * 60)
    
    try:
        # 运行各项测试
        test_position_calculator()
        test_missile_position()
        test_priority_calculator()
        test_enhanced_threat_manager()
        test_enhanced_missile_generation()
        
        print("🎉 第二步测试全部通过！服务端核心算法迁移成功。")
        print("✅ 位置计算服务正常工作")
        print("✅ 优先级计算服务正常工作") 
        print("✅ 增强威胁管理器正常工作")
        print("✅ 数据结构完整且一致")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 