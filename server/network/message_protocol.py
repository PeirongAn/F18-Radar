#!/usr/bin/env python3
"""
WebSocket消息协议定义
扩展现有协议以支持完整的威胁数据传输
"""

from typing import Dict, Any, List, Optional, TypedDict, Literal
from models.threat_models import ThreatGenerationResult, EnhancedThreat, RadarConfig

# 消息类型定义
MessageType = Literal[
    # 现有消息类型
    'task_start',
    'settings_update', 
    'antenna_adjusted',
    'target_selected',
    'threat_clicked',
    'record_operation',
    'sa_task_updated',
    'SAEmergency',
    
    # 增强消息类型（保持原有类型名以维持兼容性）
    'sa_task_updated',               # 威胁数据（增强版本但保持原有类型名）
    'SAEmergency',                   # 紧急事件（保持原有类型名）
]

class BaseMessage(TypedDict):
    """基础消息结构"""
    type: MessageType
    timestamp: Optional[int]

class EnhancedThreatsMessage(BaseMessage):
    """增强威胁消息（使用原有sa_task_updated类型保持兼容性）"""
    type: Literal['sa_task_updated']
    threats: List[Dict[str, Any]]  # EnhancedThreat的字典表示
    radar_config: Dict[str, Any]   # RadarConfig的字典表示
    highest_priority_threat_id: Optional[str]
    generation_timestamp: int
    task_type: str
    repetition_info: Dict[str, Any]
    is_ai_active: bool
    ai_level: Optional[str]
    ai_configs: Dict[str, Any]
    audio_enabled: bool

class EnhancedEmergencyMessage(BaseMessage):
    """增强紧急事件消息（使用原有SAEmergency类型保持兼容性）"""
    type: Literal['SAEmergency']
    event: Literal['upgrade', 'missile']
    enhanced_data: Dict[str, Any]  # 包含完整的威胁数据或导弹数据
    radar_config: Dict[str, Any]
    # 针对不同事件的特定字段
    missile_threat: Optional[Dict[str, Any]]  # 导弹事件时包含
    updated_threats: Optional[List[Dict[str, Any]]]  # 升级事件时包含

class EnhancedMissileMessage(BaseMessage):
    """增强导弹威胁消息"""
    type: Literal['SA_MISSILE_ENHANCED']
    missile_threat: Dict[str, Any]  # EnhancedThreat的字典表示
    radar_config: Dict[str, Any]
    
class MessageProtocol:
    """消息协议处理器"""
    
    @staticmethod
    def create_enhanced_threats_message(
        threat_result: ThreatGenerationResult,
        task_type: str,
        repetition_info: Dict[str, Any],
        is_ai_active: bool,
        ai_level: Optional[str],
        ai_configs: Dict[str, Any],
        audio_enabled: bool
    ) -> EnhancedThreatsMessage:
        """
        创建增强威胁消息
        
        Args:
            threat_result: 威胁生成结果
            task_type: 任务类型
            repetition_info: 重复信息
            is_ai_active: AI是否激活
            ai_level: AI等级名称
            ai_configs: AI配置
            audio_enabled: 音频是否启用
            
        Returns:
            增强威胁消息
        """
        return {
            'type': 'sa_task_updated',
            'threats': [threat.to_dict() for threat in threat_result.threats],
            'radar_config': threat_result.radar_config.to_dict(),
            'highest_priority_threat_id': threat_result.highest_priority_threat_id,
            'generation_timestamp': threat_result.generation_timestamp,
            'task_type': task_type,
            'repetition_info': repetition_info,
            'is_ai_active': is_ai_active,
            'ai_level': ai_level,
            'ai_configs': ai_configs,
            'audio_enabled': audio_enabled,
            'timestamp': int(threat_result.generation_timestamp)
        }
    
    @staticmethod
    def create_enhanced_emergency_message(
        event_type: str,
        radar_config: RadarConfig,
        missile_threat: Optional[EnhancedThreat] = None,
        updated_threats: Optional[List[EnhancedThreat]] = None,
        specific_upgraded_threats: Optional[List[EnhancedThreat]] = None
    ) -> EnhancedEmergencyMessage:
        """
        创建增强紧急事件消息
        
        Args:
            event_type: 事件类型 ('upgrade' 或 'missile')
            radar_config: 雷达配置
            missile_threat: 导弹威胁（导弹事件时）
            updated_threats: 更新后的完整威胁列表（升级事件时）
            specific_upgraded_threats: 具体被升级的威胁列表（可选，用于统计）
            
        Returns:
            增强紧急事件消息
        """
        import time
        
        enhanced_data = {}
        missile_threat_dict = None
        updated_threats_dict = None
        
        if event_type == 'missile' and missile_threat:
            missile_threat_dict = missile_threat.to_dict()
            enhanced_data['missile_type'] = missile_threat.missile_type
            enhanced_data['missile_position'] = missile_threat.position.to_dict()
            enhanced_data['missile_score'] = missile_threat.score
        elif event_type == 'upgrade' and updated_threats:
            updated_threats_dict = [threat.to_dict() for threat in updated_threats]
            # 如果有具体升级的威胁信息，使用它来计算升级统计
            if specific_upgraded_threats:
                enhanced_data['upgrade_count'] = len(specific_upgraded_threats)
                enhanced_data['affected_threat_ids'] = [threat.id for threat in specific_upgraded_threats]
                enhanced_data['specifically_upgraded_threats'] = [threat.to_dict() for threat in specific_upgraded_threats]
            else:
                # 回退逻辑：假设所有威胁都可能被升级
                enhanced_data['upgrade_count'] = len(updated_threats)
                enhanced_data['affected_threat_ids'] = [threat.id for threat in updated_threats]
        
        return {
            'type': 'SAEmergency',
            'event': event_type,
            'enhanced_data': enhanced_data,
            'radar_config': radar_config.to_dict(),
            'missile_threat': missile_threat_dict,
            'updated_threats': updated_threats_dict,
            'timestamp': int(time.time() * 1000)
        }
    
    @staticmethod
    def create_enhanced_missile_message(
        missile_threat: EnhancedThreat,
        radar_config: RadarConfig
    ) -> EnhancedMissileMessage:
        """
        创建增强导弹威胁消息
        
        Args:
            missile_threat: 导弹威胁对象
            radar_config: 雷达配置
            
        Returns:
            增强导弹威胁消息
        """
        return {
            'type': 'SA_MISSILE_ENHANCED',
            'missile_threat': missile_threat.to_dict(),
            'radar_config': radar_config.to_dict(),
            'timestamp': missile_threat.creation_timestamp
        }
    
    @staticmethod
    def is_enhanced_message(message_type: str) -> bool:
        """
        检查是否为增强消息类型
        
        Args:
            message_type: 消息类型
            
        Returns:
            是否为增强消息类型
        """
        enhanced_types = {
            'sa_task_updated',
            'SAEmergency'
        }
        return message_type in enhanced_types
    
    @staticmethod
    def get_legacy_message_type(enhanced_type: str) -> Optional[str]:
        """
        获取对应的传统消息类型
        
        Args:
            enhanced_type: 增强消息类型
            
        Returns:
            对应的传统消息类型，如果没有则返回None
        """
        mapping = {
            'sa_task_updated': 'sa_task_updated',
            'SAEmergency': 'SAEmergency'
        }
        return mapping.get(enhanced_type)

# 向后兼容性支持
class LegacyMessageAdapter:
    """传统消息适配器，用于向后兼容"""
    
    @staticmethod
    def enhanced_to_legacy(enhanced_message: Dict[str, Any]) -> Dict[str, Any]:
        """
        将增强消息转换为传统格式
        
        Args:
            enhanced_message: 增强消息
            
        Returns:
            传统格式消息
        """
        message_type = enhanced_message.get('type')
        
        if message_type == 'sa_task_updated':
            # 将增强威胁消息转换为传统sa_task_updated格式
            legacy_threats = []
            for threat_dict in enhanced_message['threats']:
                legacy_threats.append({
                    'id': threat_dict['id'],
                    'type': threat_dict['type'],
                    'label': threat_dict['label']
                })
            
            return {
                'type': 'sa_task_updated',
                'saThreats': legacy_threats,
                'repetition_info': enhanced_message['repetition_info'],
                'task_type': enhanced_message['task_type'],
                'is_ai_active': enhanced_message['is_ai_active'],
                'ai_level': enhanced_message.get('ai_level'),
                'ai_configs': enhanced_message['ai_configs'],
                'audio_enabled': enhanced_message['audio_enabled']
            }
        
        elif message_type == 'SAEmergency':
            # 将增强紧急事件转换为传统SAEmergency格式
            if enhanced_message['event'] == 'missile':
                return {
                    'type': 'SAEmergency',
                    'event': 'missile',
                    'missileType': enhanced_message['enhanced_data'].get('missile_type'),
                    'saThreats': []  # 传统格式需要，但可以为空
                }
            else:  # upgrade
                return {
                    'type': 'SAEmergency',
                    'event': 'upgrade',
                    'saThreats': [
                        {
                            'id': threat['id'],
                            'type': threat['type'], 
                            'label': threat['label']
                        } for threat in enhanced_message.get('updated_threats', [])
                    ]
                }
        
        # 如果不是增强消息，直接返回原消息
        return enhanced_message

# 全局消息协议实例
message_protocol = MessageProtocol() 