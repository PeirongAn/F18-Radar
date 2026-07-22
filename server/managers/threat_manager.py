import random
import asyncio
import time
import json
from typing import List, Dict, Any, Optional

# 导入新的数据模型和服务
from models.threat_models import RadarConfig, ThreatGenerationResult, EnhancedThreat
from services.position_calculator import position_calculator
from services.priority_calculator import priority_calculator
# 延迟导入 message_protocol 以避免循环导入

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
    
    def generate_enhanced_sa_threats(
        self, 
        difficulty_config: Dict[str, Any], 
        radar_config: RadarConfig
    ) -> ThreatGenerationResult:
        """
        生成增强的SA威胁（包含位置和优先级计算）
        
        Args:
            difficulty_config: 难度配置
            radar_config: 雷达配置参数
            
        Returns:
            完整的威胁生成结果
        """
        print(f"[增强威胁生成] 开始生成威胁，难度: {difficulty_config.get('name')}")
        print(f"[增强威胁生成] 雷达配置: 中心({radar_config.center_x}, {radar_config.center_y}), 半径({radar_config.radius1}, {radar_config.radius2}, {radar_config.radius3})")
        
        # 1. 生成基础威胁数据
        basic_threats = self.generate_sa_threats(difficulty_config)
        
        # 2. 计算威胁位置
        threat_positions = position_calculator.calculate_threat_positions(
            basic_threats, radar_config
        )
        
        # 3. 组合威胁和位置数据
        threats_with_positions = list(zip(basic_threats, threat_positions))
        
        # 4. 计算威胁优先级和分数（传递难度配置）
        threats_with_scores = priority_calculator.calculate_threat_scores(
            threats_with_positions, radar_config, difficulty_config
        )
        
        # 5. 创建增强威胁对象
        enhanced_threats = priority_calculator.create_enhanced_threats(
            threats_with_scores, radar_config
        )
        
        # 6. 创建威胁生成结果
        result = ThreatGenerationResult(
            threats=enhanced_threats,
            radar_config=radar_config
        )
        
        print(f"[增强威胁生成] 完成！生成{len(enhanced_threats)}个增强威胁")
        print(f"[增强威胁生成] 最高优先级威胁: {result.highest_priority_threat_id}")
        
        return result
    
    def generate_enhanced_missile_threat(
        self, 
        missile_type: str, 
        radar_config: RadarConfig
    ) -> EnhancedThreat:
        """
        生成增强的导弹威胁
        
        Args:
            missile_type: 导弹类型 ('MissileUp' 或 'MissileDown')
            radar_config: 雷达配置
            
        Returns:
            增强的导弹威胁对象
        """
        print(f"[增强导弹生成] 生成{missile_type}导弹威胁")
        
        # 1. 计算导弹位置
        missile_position = position_calculator.calculate_missile_position(
            missile_type, radar_config
        )
        
        # 2. 计算距离中心的距离
        effective_center_y = radar_config.center_y - 50
        distance_from_center = ((missile_position.x - radar_config.center_x) ** 2 + 
                               (missile_position.y - effective_center_y) ** 2) ** 0.5
        
        # 3. 创建增强导弹威胁
        enhanced_missile = EnhancedThreat(
            id=f"missile-{random.randint(1000, 9999)}",
            type="missile",
            label="上升导弹" if missile_type == "MissileUp" else "下降导弹",
            position=missile_position,
            priority="high",
            score=1.0,  # 导弹总是最高分数
            distance_from_center=distance_from_center,
            is_missile=True,
            missile_type=missile_type
        )
        
        print(f"[增强导弹生成] 导弹位置: ({missile_position.x:.1f}, {missile_position.y:.1f})")
        print(f"[增强导弹生成] 距离中心: {distance_from_center:.1f}")
        
        return enhanced_missile
    
    def generate_enhanced_sa_emergency(
        self,
        threats: List[EnhancedThreat],
        radar_config: RadarConfig
    ) -> Dict[str, Any]:
        """
        生成增强的SA紧急事件
        
        Args:
            threats: 当前威胁列表
            radar_config: 雷达配置
            
        Returns:
            增强紧急事件消息
        """
        # 随机选择事件类型
        event_type = random.choice(['upgrade', 'missile'])
        
        # 重新生成所有现有威胁的位置（增加动态效果）
        print(f"[SA增强事件] 开始重新生成所有威胁位置，原威胁数量: {len(threats)}")
        
        if event_type == 'upgrade':
            # 随机决定是否进行类型升级 (50%概率升级类型，50%概率保持原类型)
            should_upgrade_type = random.choice([True, False])
            
            upgraded_threats_only = []  # 仅升级的威胁
            all_threats_after_upgrade = []  # 升级后的完整威胁列表
            
            # 准备所有威胁的基础信息进行重新生成
            all_basic_threats = []
            upgrade_target_id = None
            new_upgrade_type = None
            
            if should_upgrade_type:
                # 找到所有secondary威胁并升级为primary
                secondary_threats = [t for t in threats if t.type.startswith('Secondary')]
                if secondary_threats:
                    to_upgrade = random.choice(secondary_threats)
                    upgrade_target_id = to_upgrade.id
                    new_upgrade_type = to_upgrade.type.replace('Secondary', 'Primary')
                    print(f"[SA增强升级] 将升级威胁: {upgrade_target_id} -> {new_upgrade_type}")
            
            # 构建所有威胁的基础信息（包括可能的类型升级）
            for threat in threats:
                if threat.id == upgrade_target_id:
                    # 升级威胁
                    all_basic_threats.append({
                        'id': threat.id,
                        'type': new_upgrade_type,
                        'original_threat': threat,
                        'is_upgraded': True
                    })
                else:
                    # 保持原类型
                    all_basic_threats.append({
                        'id': threat.id,
                        'type': threat.type,
                        'original_threat': threat,
                        'is_upgraded': False
                    })
            
            # 重新生成所有威胁的位置
            basic_threat_list = [{'id': bt['id'], 'type': bt['type']} for bt in all_basic_threats]
            new_positions = position_calculator.calculate_threat_positions(
                basic_threat_list, radar_config
            )
            
            # 重新计算所有威胁的分数（紧急事件时使用默认难度）
            threats_with_positions = list(zip(basic_threat_list, new_positions))
            threats_with_scores = priority_calculator.calculate_threat_scores(
                threats_with_positions, radar_config, None
            )
            
            # 创建更新后的威胁对象
            for i, basic_threat_info in enumerate(all_basic_threats):
                original_threat = basic_threat_info['original_threat']
                score_info = threats_with_scores[i]
                new_position = threats_with_scores[i]['position']
                
                if basic_threat_info['is_upgraded']:
                    # 升级的威胁
                    upgraded_threat = EnhancedThreat(
                        id=original_threat.id,
                        type=basic_threat_info['type'],
                        label=random.choice(self.SA_LABELS[basic_threat_info['type']]),
                        position=new_position,
                        priority='high',  # Primary类型是高优先级
                        score=score_info['score'],
                        distance_from_center=score_info['distance_from_center'],
                        is_missile=original_threat.is_missile,
                        missile_type=original_threat.missile_type
                    )
                    upgraded_threats_only.append(upgraded_threat)
                    all_threats_after_upgrade.append(upgraded_threat)
                    print(f"[SA增强升级] 威胁升级: {original_threat.id} -> {basic_threat_info['type']}, 新位置: ({new_position.x:.1f}, {new_position.y:.1f})")
                else:
                    # 重新定位的原威胁
                    relocated_threat = EnhancedThreat(
                        id=original_threat.id,
                        type=original_threat.type,
                        label=original_threat.label,
                        position=new_position,  # 新位置
                        priority=original_threat.priority,
                        score=score_info['score'],  # 重新计算的分数
                        distance_from_center=score_info['distance_from_center'],
                        is_missile=original_threat.is_missile,
                        missile_type=original_threat.missile_type
                    )
                    all_threats_after_upgrade.append(relocated_threat)
                    print(f"[SA增强升级] 威胁重新定位: {original_threat.id}, 新位置: ({new_position.x:.1f}, {new_position.y:.1f})")
            
            # 延迟导入避免循环依赖
            from network.message_protocol import message_protocol
            return message_protocol.create_enhanced_emergency_message(
                event_type='upgrade',
                radar_config=radar_config,
                updated_threats=all_threats_after_upgrade,  # 传递完整的威胁列表
                specific_upgraded_threats=upgraded_threats_only  # 可选：标明具体升级的威胁
            )
        else:
        # 导弹事件：重新生成所有现有威胁位置 + 添加新导弹
            print(f"[SA增强导弹] 重新生成所有威胁位置并添加导弹")
            
            # 重新生成所有现有威胁的位置
            basic_threat_list = [{'id': t.id, 'type': t.type} for t in threats]
            new_positions = position_calculator.calculate_threat_positions(
                basic_threat_list, radar_config
            )
            
            # 生成导弹威胁（先获取基础导弹信息）
            missile_type = random.choice(['MissileUp', 'MissileDown'])
            enhanced_missile = self.generate_enhanced_missile_threat(missile_type, radar_config)
            
            # 将所有威胁（包括导弹）一起进行分数归一化计算
            all_basic_threats = basic_threat_list + [{'id': enhanced_missile.id, 'type': enhanced_missile.type}]
            all_positions = new_positions + [enhanced_missile.position]
            
            # 重新计算所有威胁的分数（包括导弹，紧急事件时使用默认难度）
            all_threats_with_positions = list(zip(all_basic_threats, all_positions))
            all_threats_with_scores = priority_calculator.calculate_threat_scores(
                all_threats_with_positions, radar_config, None
            )
            
            # 创建重新定位的威胁列表
            relocated_threats = []
            for i, threat in enumerate(threats):
                new_position = new_positions[i]
                score_info = all_threats_with_scores[i]  # 使用归一化后的分数
                
                relocated_threat = EnhancedThreat(
                    id=threat.id,
                    type=threat.type,
                    label=threat.label,
                    position=new_position,  # 新位置
                    priority=threat.priority,
                    score=score_info['score'],  # 归一化后的分数
                    distance_from_center=score_info['distance_from_center'],
                    is_missile=threat.is_missile,
                    missile_type=threat.missile_type
                )
                relocated_threats.append(relocated_threat)
                print(f"[SA增强导弹] 威胁重新定位: {threat.id}, 新位置: ({new_position.x:.1f}, {new_position.y:.1f}), 归一化分数: {score_info['score']:.2f}")
            
            # 更新导弹威胁的归一化分数
            missile_score_info = all_threats_with_scores[-1]  # 导弹是最后一个
            enhanced_missile.score = missile_score_info['score']
            enhanced_missile.distance_from_center = missile_score_info['distance_from_center']
            print(f"[SA增强导弹] 导弹威胁: {enhanced_missile.id}, 位置: ({enhanced_missile.position.x:.1f}, {enhanced_missile.position.y:.1f}), 归一化分数: {enhanced_missile.score:.2f}")
            
            # 延迟导入避免循环依赖
            from network.message_protocol import message_protocol
            return message_protocol.create_enhanced_emergency_message(
                event_type='missile',
                radar_config=radar_config,
                updated_threats=relocated_threats,  # 传递重新定位的威胁列表
                missile_threat=enhanced_missile
            )
    
    async def auto_send_enhanced_sa_emergency(
        self,
        websocket,
        threats: List[EnhancedThreat],
        radar_config: RadarConfig,
        user_id: str,
        event_owner: str,
        session_state: Dict[str, Any],
        use_enhanced_protocol: bool = True
    ) -> None:
        """
        自动发送增强SA紧急事件
        
        Args:
            websocket: WebSocket连接
            threats: 当前威胁列表
            radar_config: 雷达配置
            user_id: 用户ID
            event_owner: 事件所有者
            session_state: 会话状态
            use_enhanced_protocol: 是否使用增强协议
        """
        await asyncio.sleep(random.uniform(2, 3))
        
        if use_enhanced_protocol:
            emergency_msg = self.generate_enhanced_sa_emergency(threats, radar_config)
            current_candidates = list(emergency_msg.get("updated_threats") or [])
            missile_candidate = emergency_msg.get("missile_threat")
            if isinstance(missile_candidate, dict):
                current_candidates.append(missile_candidate)
            scored_candidates = [
                candidate for candidate in current_candidates
                if isinstance(candidate, dict) and candidate.get("id") is not None
            ]
            ground_truth = max(
                scored_candidates,
                key=lambda candidate: float(candidate.get("score") or 0),
                default=None,
            )
            task_id = session_state.get("current_task_id")
            if task_id is not None and ground_truth is not None:
                snapshots = session_state.setdefault("trust_task_snapshots", {})
                snapshots[str(task_id)] = {
                    "task_type": "SA_THREAT_RESPONSE",
                    "candidate_ids": [str(candidate["id"]) for candidate in scored_candidates],
                    "candidates": [
                        {
                            "id": str(candidate["id"]),
                            "type": candidate.get("type"),
                            "score": candidate.get("score"),
                        }
                        for candidate in scored_candidates
                    ],
                    "ground_truth_id": str(ground_truth["id"]),
                    "updated_at_ms": int(time.time() * 1000),
                }
        else:
            # 回退到传统协议
            legacy_threats = [
                {'id': t.id, 'type': t.type, 'label': t.label} 
                for t in threats
            ]
            emergency_msg = self.generate_sa_emergency(legacy_threats)
        
        # 发送消息
        event_type = emergency_msg.get('event', 'unknown')
        msg_type = emergency_msg.get('type', 'unknown')
        
        try:
            json_str = json.dumps(emergency_msg)
            # 先尝试标准的send方法
            try:
                await websocket.send(json_str)
            except AttributeError:
                # 如果send方法不存在，尝试send_str方法
                await websocket.send_str(json_str)
            
            print(f"[自动] 已发送{msg_type}事件: {event_type}")
        except Exception as e:
            print(f"发送{msg_type}消息失败: {e}")
            return
        
        # 记录临机事件日志
        try:
            # 只有在非练习模式下才记录数据库
            if not session_state.get('is_practice', False):
                from .database_manager import db_manager
                operation = {
                    'task_id': session_state.get('current_task_id'),
                    'operationType': 'sa_emergency_enhanced' if use_enhanced_protocol else 'sa_emergency',
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
            print(f"记录SA增强Emergency日志失败: {e}")
    
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
            # 先尝试标准的send方法
            try:
                await websocket.send(json_str)
            except AttributeError:
                # 如果send方法不存在，尝试send_str方法
                await websocket.send_str(json_str)
            
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
