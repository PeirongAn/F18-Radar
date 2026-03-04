#!/usr/bin/env python3
"""
前端适配改造测试
验证增强威胁协议的前端兼容性
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
from models.threat_models import RadarConfig, ThreatGenerationResult, EnhancedThreat, ThreatPosition
from network.message_protocol import MessageProtocol, LegacyMessageAdapter, message_protocol
from managers.threat_manager import threat_manager

def test_enhanced_message_structure():
    """测试增强消息结构是否符合前端预期"""
    print("=== 测试增强消息结构 ===")
    
    # 创建雷达配置
    radar_config = RadarConfig(
        center_x=450.0, center_y=540.0,
        radius1=100.0, radius2=270.0, radius3=459.0,
        canvas_width=900.0, canvas_height=900.0
    )
    
    # 生成增强威胁
    difficulty_config = {'name': 'test', 'threat_count': 3}
    threat_result = threat_manager.generate_enhanced_sa_threats(
        difficulty_config, radar_config
    )
    
    # 创建增强威胁消息
    enhanced_message = message_protocol.create_enhanced_threats_message(
        threat_result=threat_result,
        task_type="SA_THREAT_RESPONSE",
        repetition_info={"current": 1, "total": 3},
        is_ai_active=False,
        ai_level="level1",
        ai_configs={"level1": {"name": "初级"}},
        audio_enabled=True
    )
    
    print("增强消息结构验证:")
    print(f"  消息类型: {enhanced_message['type']}")
    print(f"  威胁数量: {len(enhanced_message['threats'])}")
    print(f"  雷达配置: {enhanced_message['radar_config']['center_x']}, {enhanced_message['radar_config']['center_y']}")
    
    # 验证前端需要的字段
    required_fields = [
        'type', 'threats', 'radar_config', 'highest_priority_threat_id',
        'task_type', 'repetition_info', 'is_ai_active', 'audio_enabled'
    ]
    
    for field in required_fields:
        assert field in enhanced_message, f"缺少必需字段: {field}"
    
    # 验证威胁数据结构
    if enhanced_message['threats']:
        threat = enhanced_message['threats'][0]
        threat_required_fields = [
            'id', 'type', 'label', 'position', 'priority', 'score',
            'distance_from_center', 'is_missile'
        ]
        
        for field in threat_required_fields:
            assert field in threat, f"威胁数据缺少必需字段: {field}"
        
        # 验证位置数据结构
        assert 'x' in threat['position'], "位置数据缺少x坐标"
        assert 'y' in threat['position'], "位置数据缺少y坐标"
    
    print("✅ 增强消息结构测试通过\n")
    return enhanced_message

def test_enhanced_emergency_structure():
    """测试增强紧急事件结构"""
    print("=== 测试增强紧急事件结构 ===")
    
    radar_config = RadarConfig(
        center_x=450.0, center_y=540.0,
        radius1=100.0, radius2=270.0, radius3=459.0,
        canvas_width=900.0, canvas_height=900.0
    )
    
    # 测试导弹紧急事件
    missile_threat = threat_manager.generate_enhanced_missile_threat("MissileUp", radar_config)
    missile_emergency = message_protocol.create_enhanced_emergency_message(
        event_type='missile',
        radar_config=radar_config,
        missile_threat=missile_threat
    )
    
    print("导弹紧急事件结构验证:")
    print(f"  事件类型: {missile_emergency['type']}")
    print(f"  事件: {missile_emergency['event']}")
    print(f"  导弹位置: ({missile_emergency['missile_threat']['position']['x']}, {missile_emergency['missile_threat']['position']['y']})")
    
    # 验证前端需要的字段
    missile_required_fields = [
        'type', 'event', 'missile_threat', 'radar_config', 'enhanced_data'
    ]
    
    for field in missile_required_fields:
        assert field in missile_emergency, f"导弹紧急事件缺少字段: {field}"
    
    # 验证导弹威胁数据
    missile_data = missile_emergency['missile_threat']
    assert 'id' in missile_data, "导弹数据缺少ID"
    assert 'position' in missile_data, "导弹数据缺少位置"
    assert 'missile_type' in missile_data, "导弹数据缺少类型"
    
    print("✅ 增强紧急事件结构测试通过\n")
    return missile_emergency

def test_legacy_compatibility():
    """测试传统协议兼容性"""
    print("=== 测试传统协议兼容性 ===")
    
    # 创建增强消息
    enhanced_message = test_enhanced_message_structure()
    
    # 转换为传统格式
    legacy_message = LegacyMessageAdapter.enhanced_to_legacy(enhanced_message)
    
    print("传统协议兼容性验证:")
    print(f"  传统消息类型: {legacy_message['type']}")
    print(f"  传统威胁数量: {len(legacy_message['saThreats'])}")
    
    # 验证传统消息结构
    assert legacy_message['type'] == 'sa_task_updated', "传统消息类型不正确"
    assert 'saThreats' in legacy_message, "传统消息缺少saThreats"
    assert 'repetition_info' in legacy_message, "传统消息缺少repetition_info"
    
    # 验证传统威胁结构
    if legacy_message['saThreats']:
        legacy_threat = legacy_message['saThreats'][0]
        legacy_threat_fields = ['id', 'type', 'label']
        
        for field in legacy_threat_fields:
            assert field in legacy_threat, f"传统威胁缺少字段: {field}"
    
    print("✅ 传统协议兼容性测试通过\n")
    return legacy_message

def test_frontend_data_format():
    """测试前端数据格式要求"""
    print("=== 测试前端数据格式要求 ===")
    
    # 创建模拟前端需要的数据格式
    radar_config = RadarConfig(
        center_x=450.0, center_y=540.0,
        radius1=100.0, radius2=270.0, radius3=459.0,
        canvas_width=900.0, canvas_height=900.0
    )
    
    difficulty_config = {'name': 'test', 'threat_count': 4}
    threat_result = threat_manager.generate_enhanced_sa_threats(
        difficulty_config, radar_config
    )
    
    # 模拟前端接收到的数据处理
    frontend_data = {
        'enhancedThreats': [threat.to_dict() for threat in threat_result.threats],
        'serverRadarConfig': radar_config.to_dict(),
        'highestPriorityThreatId': threat_result.highest_priority_threat_id
    }
    
    print("前端数据格式验证:")
    print(f"  增强威胁数量: {len(frontend_data['enhancedThreats'])}")
    print(f"  雷达配置完整性: {len(frontend_data['serverRadarConfig'])} 个字段")
    print(f"  最高优先级威胁: {frontend_data['highestPriorityThreatId']}")
    
    # 验证前端可以直接使用的数据格式
    for threat_dict in frontend_data['enhancedThreats']:
        # 验证位置数据可以直接使用
        assert 'position' in threat_dict, "威胁缺少位置数据"
        assert 'x' in threat_dict['position'], "位置缺少x坐标"
        assert 'y' in threat_dict['position'], "位置缺少y坐标"
        
        # 验证分数数据可以直接使用
        assert 'score' in threat_dict, "威胁缺少分数数据"
        assert isinstance(threat_dict['score'], (int, float)), "分数数据类型错误"
        
        # 验证优先级数据可以直接使用
        assert 'priority' in threat_dict, "威胁缺少优先级数据"
        assert threat_dict['priority'] in ['high', 'medium', 'low'], "优先级值无效"
        
        # 模拟前端的位置计算逻辑简化
        position = threat_dict['position']
        print(f"    威胁 {threat_dict['id']}: 位置({position['x']:.1f}, {position['y']:.1f}), 分数{threat_dict['score']}")
    
    print("✅ 前端数据格式测试通过\n")
    return frontend_data

def test_missile_event_handling():
    """测试导弹事件处理"""
    print("=== 测试导弹事件处理 ===")
    
    radar_config = RadarConfig(
        center_x=450.0, center_y=540.0,
        radius1=100.0, radius2=270.0, radius3=459.0,
        canvas_width=900.0, canvas_height=900.0
    )
    
    # 生成增强导弹事件
    missile_threat = threat_manager.generate_enhanced_missile_threat("MissileUp", radar_config)
    missile_emergency = message_protocol.create_enhanced_emergency_message(
        event_type='missile',
        radar_config=radar_config,
        missile_threat=missile_threat
    )
    
    print("导弹事件处理验证:")
    print(f"  导弹类型: {missile_emergency['missile_threat']['missile_type']}")
    print(f"  导弹位置: ({missile_emergency['missile_threat']['position']['x']:.1f}, {missile_emergency['missile_threat']['position']['y']:.1f})")
    
    # 模拟前端处理逻辑
    missile_data = missile_emergency['missile_threat']
    frontend_missile = {
        'id': missile_data['id'],
        'type': missile_data['missile_type'],
        'x': missile_data['position']['x'],
        'y': missile_data['position']['y']
    }
    
    # 验证前端可以直接使用
    assert frontend_missile['type'] in ['MissileUp', 'MissileDown'], "导弹类型无效"
    assert isinstance(frontend_missile['x'], (int, float)), "导弹X坐标类型错误"
    assert isinstance(frontend_missile['y'], (int, float)), "导弹Y坐标类型错误"
    
    print(f"  前端导弹数据: {frontend_missile}")
    print("✅ 导弹事件处理测试通过\n")
    return frontend_missile

def test_json_serialization_for_frontend():
    """测试前端JSON序列化兼容性"""
    print("=== 测试前端JSON序列化兼容性 ===")
    
    # 创建完整的前端数据包
    enhanced_message = test_enhanced_message_structure()
    missile_emergency = test_enhanced_emergency_structure()
    
    try:
        # 测试JSON序列化
        enhanced_json = json.dumps(enhanced_message, ensure_ascii=False, indent=2)
        missile_json = json.dumps(missile_emergency, ensure_ascii=False, indent=2)
        
        # 测试反序列化
        enhanced_parsed = json.loads(enhanced_json)
        missile_parsed = json.loads(missile_json)
        
        print("JSON序列化验证:")
        print(f"  增强消息JSON大小: {len(enhanced_json)} 字符")
        print(f"  导弹事件JSON大小: {len(missile_json)} 字符")
        
        # 验证数据完整性
        assert enhanced_parsed['type'] == enhanced_message['type'], "增强消息序列化后类型不一致"
        assert missile_parsed['event'] == missile_emergency['event'], "导弹事件序列化后事件不一致"
        
        # 验证前端关键数据不丢失
        if enhanced_parsed['threats']:
            threat = enhanced_parsed['threats'][0]
            assert 'position' in threat, "序列化后威胁位置丢失"
            assert 'score' in threat, "序列化后威胁分数丢失"
        
        print("✅ JSON序列化兼容性测试通过\n")
        
    except Exception as e:
        print(f"❌ JSON序列化失败: {e}")
        raise

def main():
    """运行所有前端适配测试"""
    print("开始测试前端适配改造...")
    print("=" * 60)
    
    try:
        # 运行各项测试
        test_enhanced_message_structure()
        test_enhanced_emergency_structure()
        test_legacy_compatibility()
        test_frontend_data_format()
        test_missile_event_handling()
        test_json_serialization_for_frontend()
        
        print("🎉 第四步测试全部通过！前端适配改造成功。")
        print("✅ 增强威胁消息结构符合前端要求")
        print("✅ 增强紧急事件结构符合前端要求")
        print("✅ 传统协议兼容性保持良好")
        print("✅ 前端数据格式完全可用")
        print("✅ 导弹事件处理逻辑正确")
        print("✅ JSON序列化完全兼容")
        print("\n📋 前端改造总结:")
        print("   - 前端无需复杂计算，直接使用服务端数据")
        print("   - 位置、分数、优先级都由服务端提供")
        print("   - 保持与传统协议的向后兼容")
        print("   - 导弹位置也由服务端计算")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 