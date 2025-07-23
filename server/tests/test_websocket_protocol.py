#!/usr/bin/env python3
"""
WebSocket协议扩展测试
验证新的增强威胁消息协议是否正确工作
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
from models.threat_models import RadarConfig, ThreatGenerationResult, EnhancedThreat, ThreatPosition
from network.message_protocol import MessageProtocol, LegacyMessageAdapter, message_protocol
from managers.threat_manager import threat_manager

def test_message_protocol_creation():
    """测试消息协议创建"""
    print("=== 测试消息协议创建 ===")
    
    # 创建测试数据
    radar_config = RadarConfig(
        center_x=450.0, center_y=540.0,
        radius1=100.0, radius2=270.0, radius3=459.0,
        canvas_width=900.0, canvas_height=900.0
    )
    
    # 创建测试威胁
    test_threat = EnhancedThreat(
        id="test-threat-1",
        type="PrimaryAir",
        label="F-16",
        position=ThreatPosition(x=300.0, y=200.0),
        priority="high",
        score=0.85,
        distance_from_center=150.0,
        is_missile=False
    )
    
    threat_result = ThreatGenerationResult(
        threats=[test_threat],
        radar_config=radar_config
    )
    
    # 测试增强威胁消息创建
    enhanced_message = message_protocol.create_enhanced_threats_message(
        threat_result=threat_result,
        task_type="SA_THREAT_RESPONSE",
        repetition_info={"current": 1, "total": 3},
        is_ai_active=False,
        ai_level="level1",
        ai_configs={"level1": {"name": "初级"}},
        audio_enabled=True
    )
    
    print(f"增强威胁消息类型: {enhanced_message['type']}")
    print(f"威胁数量: {len(enhanced_message['threats'])}")
    print(f"最高优先级威胁ID: {enhanced_message['highest_priority_threat_id']}")
    print(f"雷达配置包含: {list(enhanced_message['radar_config'].keys())}")
    
    # 验证消息结构
    assert enhanced_message['type'] == 'SA_THREATS_ENHANCED', "消息类型不正确"
    assert len(enhanced_message['threats']) == 1, "威胁数量不正确"
    assert enhanced_message['highest_priority_threat_id'] == test_threat.id, "最高优先级威胁ID不正确"
    assert 'center_x' in enhanced_message['radar_config'], "雷达配置缺失"
    assert enhanced_message['task_type'] == "SA_THREAT_RESPONSE", "任务类型不正确"
    
    print("✅ 增强威胁消息创建测试通过\n")
    return enhanced_message

def test_emergency_message_creation():
    """测试紧急事件消息创建"""
    print("=== 测试紧急事件消息创建 ===")
    
    radar_config = RadarConfig(
        center_x=450.0, center_y=540.0,
        radius1=100.0, radius2=270.0, radius3=459.0,
        canvas_width=900.0, canvas_height=900.0
    )
    
    # 测试导弹紧急事件
    missile_threat = EnhancedThreat(
        id="missile-123",
        type="missile",
        label="上升导弹",
        position=ThreatPosition(x=400.0, y=300.0),
        priority="high",
        score=1.0,
        distance_from_center=200.0,
        is_missile=True,
        missile_type="MissileUp"
    )
    
    missile_emergency = message_protocol.create_enhanced_emergency_message(
        event_type='missile',
        radar_config=radar_config,
        missile_threat=missile_threat
    )
    
    print(f"导弹紧急事件类型: {missile_emergency['type']}")
    print(f"事件: {missile_emergency['event']}")
    print(f"导弹类型: {missile_emergency['enhanced_data']['missile_type']}")
    
    # 测试升级紧急事件
    upgraded_threat = EnhancedThreat(
        id="upgraded-456",
        type="PrimaryAir",
        label="F-16",
        position=ThreatPosition(x=350.0, y=250.0),
        priority="high",
        score=0.9,
        distance_from_center=180.0,
        is_missile=False
    )
    
    upgrade_emergency = message_protocol.create_enhanced_emergency_message(
        event_type='upgrade',
        radar_config=radar_config,
        updated_threats=[upgraded_threat]
    )
    
    print(f"升级紧急事件类型: {upgrade_emergency['type']}")
    print(f"事件: {upgrade_emergency['event']}")
    print(f"升级威胁数量: {upgrade_emergency['enhanced_data']['upgrade_count']}")
    
    # 验证消息结构
    assert missile_emergency['type'] == 'SA_EMERGENCY_ENHANCED', "导弹紧急事件类型不正确"
    assert missile_emergency['event'] == 'missile', "导弹事件类型不正确"
    assert missile_emergency['missile_threat'] is not None, "导弹威胁数据缺失"
    
    assert upgrade_emergency['type'] == 'SA_EMERGENCY_ENHANCED', "升级紧急事件类型不正确"
    assert upgrade_emergency['event'] == 'upgrade', "升级事件类型不正确"
    assert upgrade_emergency['updated_threats'] is not None, "升级威胁数据缺失"
    
    print("✅ 紧急事件消息创建测试通过\n")
    return missile_emergency, upgrade_emergency

def test_legacy_message_adapter():
    """测试传统消息适配器"""
    print("=== 测试传统消息适配器 ===")
    
    # 使用之前创建的增强消息
    enhanced_message = test_message_protocol_creation()
    
    # 转换为传统格式
    legacy_message = LegacyMessageAdapter.enhanced_to_legacy(enhanced_message)
    
    print(f"传统消息类型: {legacy_message['type']}")
    print(f"传统威胁数据键: {list(legacy_message.keys())}")
    print(f"传统威胁数量: {len(legacy_message['saThreats'])}")
    
    # 验证转换结果
    assert legacy_message['type'] == 'sa_task_updated', "传统消息类型转换不正确"
    assert 'saThreats' in legacy_message, "传统威胁数据缺失"
    assert len(legacy_message['saThreats']) == 1, "传统威胁数量不正确"
    assert legacy_message['task_type'] == enhanced_message['task_type'], "任务类型不一致"
    
    # 检查传统威胁数据结构
    legacy_threat = legacy_message['saThreats'][0]
    assert 'id' in legacy_threat, "传统威胁缺少ID"
    assert 'type' in legacy_threat, "传统威胁缺少类型"
    assert 'label' in legacy_threat, "传统威胁缺少标签"
    
    print("✅ 传统消息适配器测试通过\n")
    return legacy_message

def test_enhanced_threat_manager_integration():
    """测试增强威胁管理器集成"""
    print("=== 测试增强威胁管理器集成 ===")
    
    # 创建难度配置和雷达配置
    difficulty_config = {'name': 'test', 'threat_count': 2}
    radar_config = RadarConfig(
        center_x=450.0, center_y=540.0,
        radius1=100.0, radius2=270.0, radius3=459.0,
        canvas_width=900.0, canvas_height=900.0
    )
    
    # 生成增强威胁
    threat_result = threat_manager.generate_enhanced_sa_threats(
        difficulty_config, radar_config
    )
    
    # 测试增强紧急事件生成
    enhanced_emergency = threat_manager.generate_enhanced_sa_emergency(
        threat_result.threats, radar_config
    )
    
    print(f"威胁管理器生成结果:")
    print(f"  威胁数量: {len(threat_result.threats)}")
    print(f"  紧急事件类型: {enhanced_emergency['type']}")
    print(f"  紧急事件: {enhanced_emergency['event']}")
    
    # 验证集成结果
    assert len(threat_result.threats) == difficulty_config['threat_count'], "威胁数量不匹配"
    assert enhanced_emergency['type'] == 'SA_EMERGENCY_ENHANCED', "紧急事件类型不正确"
    assert enhanced_emergency['event'] in ['missile', 'upgrade'], "紧急事件不正确"
    
    print("✅ 增强威胁管理器集成测试通过\n")
    return threat_result, enhanced_emergency

def test_json_serialization():
    """测试JSON序列化"""
    print("=== 测试JSON序列化 ===")
    
    # 生成测试数据
    enhanced_message = test_message_protocol_creation()
    missile_emergency, upgrade_emergency = test_emergency_message_creation()
    
    # 测试JSON序列化
    try:
        enhanced_json = json.dumps(enhanced_message)
        missile_json = json.dumps(missile_emergency)
        upgrade_json = json.dumps(upgrade_emergency)
        
        print(f"增强威胁消息JSON长度: {len(enhanced_json)}")
        print(f"导弹紧急事件JSON长度: {len(missile_json)}")
        print(f"升级紧急事件JSON长度: {len(upgrade_json)}")
        
        # 测试反序列化
        enhanced_data = json.loads(enhanced_json)
        missile_data = json.loads(missile_json)
        upgrade_data = json.loads(upgrade_json)
        
        # 验证数据完整性
        assert enhanced_data['type'] == enhanced_message['type'], "增强消息序列化后类型不一致"
        assert missile_data['event'] == missile_emergency['event'], "导弹事件序列化后事件不一致"
        assert upgrade_data['event'] == upgrade_emergency['event'], "升级事件序列化后事件不一致"
        
        print("✅ JSON序列化测试通过\n")
        
    except Exception as e:
        print(f"❌ JSON序列化失败: {e}")
        raise

def test_protocol_compatibility():
    """测试协议兼容性"""
    print("=== 测试协议兼容性 ===")
    
    # 测试消息类型检查
    assert message_protocol.is_enhanced_message('SA_THREATS_ENHANCED'), "增强消息类型检查失败"
    assert message_protocol.is_enhanced_message('SA_EMERGENCY_ENHANCED'), "增强紧急事件类型检查失败"
    assert not message_protocol.is_enhanced_message('sa_task_updated'), "传统消息类型检查错误"
    
    # 测试传统消息类型映射
    assert message_protocol.get_legacy_message_type('SA_THREATS_ENHANCED') == 'sa_task_updated', "传统消息类型映射错误"
    assert message_protocol.get_legacy_message_type('SA_EMERGENCY_ENHANCED') == 'SAEmergency', "传统紧急事件类型映射错误"
    
    print("协议兼容性检查:")
    print(f"  - SA_THREATS_ENHANCED -> {message_protocol.get_legacy_message_type('SA_THREATS_ENHANCED')}")
    print(f"  - SA_EMERGENCY_ENHANCED -> {message_protocol.get_legacy_message_type('SA_EMERGENCY_ENHANCED')}")
    print(f"  - SA_MISSILE_ENHANCED -> {message_protocol.get_legacy_message_type('SA_MISSILE_ENHANCED')}")
    
    print("✅ 协议兼容性测试通过\n")

def main():
    """运行所有测试"""
    print("开始测试WebSocket协议扩展...")
    print("=" * 60)
    
    try:
        # 运行各项测试
        test_message_protocol_creation()
        test_emergency_message_creation()
        test_legacy_message_adapter()
        test_enhanced_threat_manager_integration()
        test_json_serialization()
        test_protocol_compatibility()
        
        print("🎉 第三步测试全部通过！WebSocket协议扩展成功。")
        print("✅ 增强威胁消息协议正常工作")
        print("✅ 增强紧急事件协议正常工作")
        print("✅ 传统消息适配器正常工作")
        print("✅ JSON序列化正常工作")
        print("✅ 协议兼容性正常工作")
        print("✅ 威胁管理器集成正常工作")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 