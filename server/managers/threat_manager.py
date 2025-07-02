import random
import asyncio
import time
import json
from typing import List, Dict, Any

class ThreatManager:
    """SA威胁管理器，负责威胁生成和紧急事件处理"""
    
    def __init__(self):
        self.SA_ICON_TYPES = [
            'PrimaryAir',
            'SecondaryAir',
            'PrimaryAntiAircraftArtillery',
            'SecondaryAntiAircraftArtillery',
            'PrimaryNaval',
            'SecondaryNaval',
        ]
        
        self.SA_LABELS = {
            'PrimaryAir': ['J-11', 'F-16', 'Su-27', 'F-15'],
            'SecondaryAir': ['MiG-29', 'F-5', 'F-7', 'Su-30'],
            'PrimaryAntiAircraftArtillery': ['SA-10', 'HQ-9', 'S-300'],
            'SecondaryAntiAircraftArtillery': ['SA-6', 'HQ-7', 'S-75'],
            'PrimaryNaval': ['052D', '054A', '055', 'Kirov'],
            'SecondaryNaval': ['056', '053H3', 'Frigate', 'Corvette'],
        }
    
    def generate_sa_threats(self, difficulty_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """根据传入的难度配置生成SA威胁"""
        # 从传入的配置中获取威胁数量
        n = difficulty_config.get('threat_count', 4)

        threats = []
        
        # 方案1：允许重复类型，主要使用Secondary类型，但可以重复生成
        secondary_types = [t for t in self.SA_ICON_TYPES if t.startswith('Secondary')]
        
        # 如果需要的威胁数量超过Secondary类型数量，允许重复选择
        if n <= len(secondary_types):
            # 如果需要的数量不超过可用类型，正常选择不重复
            chosen_types = random.sample(secondary_types, k=n)
        else:
            # 如果需要更多威胁，允许重复选择类型
            chosen_types = []
            for i in range(n):
                chosen_types.append(random.choice(secondary_types))
        
        # 生成威胁
        for i, threat_type in enumerate(chosen_types):
            label = random.choice(self.SA_LABELS[threat_type])
            threats.append({
                'id': f'{threat_type}-{random.randint(1000,9999)}-{i}',  # 添加索引避免ID重复
                'type': threat_type,
                'label': label
            })
        
        print(f"[SA威胁生成] 生成了{len(threats)}个威胁 (Difficulty: {difficulty_config.get('name')})")
        return threats
    
    def generate_sa_emergency(self, threats: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成SA紧急事件"""
        # 随机选择事件类型
        event_type = random.choice(['upgrade', 'missile'])
        
        if event_type == 'upgrade':
            # 随机决定是否进行类型升级 (50%概率升级类型，50%概率保持原类型)
            should_upgrade_type = random.choice([True, False])
            
            if should_upgrade_type:
                # 找到所有secondary威胁并升级为primary
                secondary = [t for t in threats if t['type'].startswith('Secondary')]
                if secondary:
                    to_upgrade = random.choice(secondary)
                    # 升级为primary
                    primary_type = to_upgrade['type'].replace('Secondary', 'Primary')
                    to_upgrade['type'] = primary_type
                    to_upgrade['label'] = random.choice(self.SA_LABELS[primary_type])
                    print(f"[SA升级] 威胁类型升级: {to_upgrade['id']} -> {primary_type}")
            else:
                # 不升级类型，保持现有威胁，让客户端根据位置判断优先级
                print(f"[SA升级] 威胁未升级类型，客户端将根据位置判断优先级")
            
            return {
                'type': 'SAEmergency',
                'event': 'upgrade',
                'saThreats': threats
            }
        else:
            missile_type = random.choice(['MissileUp', 'MissileDown'])
            return {
                'type': 'SAEmergency',
                'event': 'missile',
                'missileType': missile_type,
                'saThreats': threats
            }
    
    async def auto_send_sa_emergency(self, websocket, threats: List[Dict[str, Any]], 
                                   user_id: str, event_owner: str, session_state: Dict[str, Any]) -> None:
        """自动发送SA紧急事件"""
        await asyncio.sleep(random.uniform(2, 3))
        emergency_msg = self.generate_sa_emergency(threats)
        
        # 发送消息
        try:
            json_str = json.dumps(emergency_msg)
            await websocket.send(json_str)
            print(f"[自动] 已发送SAEmergency事件: {emergency_msg['event']}")
        except Exception as e:
            print(f"发送SAEmergency消息失败: {e}")
            return
        
        # 记录临机事件日志
        try:
            # 只有在非练习模式下才记录数据库
            if not session_state.get('is_practice', False):
                from .database_manager import db_manager
                operation = {
                    'task_id': session_state.get('current_task_id'),  # 需要从会话状态获取
                    'operationType': 'sa_emergency',
                    'timestamp': int(time.time() * 1000),
                    'isActive': False,
                    'parameters': emergency_msg,
                    'user_id': user_id,
                    'event_owner': event_owner
                }
                db_manager.record_operation(operation, session_state.get('is_practice', False))
            else:
                print("练习模式，跳过 sa_emergency 数据库记录。")
        except Exception as e:
            print(f"记录SAEmergency日志失败: {e}")

# 全局威胁管理器实例
threat_manager = ThreatManager() 