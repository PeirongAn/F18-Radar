from typing import Dict, Any, Optional, Literal
from dataclasses import dataclass, asdict
import time

@dataclass
class RadarConfig:
    """雷达配置参数"""
    center_x: float
    center_y: float
    radius1: float           # 内圆半径
    radius2: float           # 中圆半径  
    radius3: float           # 外圆半径
    canvas_width: float      # 画布宽度
    canvas_height: float     # 画布高度
    icon_size: float = 48    # 图标大小
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return asdict(self)

@dataclass 
class ThreatPosition:
    """威胁位置信息"""
    x: float
    y: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class EnhancedThreat:
    """增强的威胁数据结构"""
    id: str
    type: str
    label: str
    position: ThreatPosition
    priority: Literal['high', 'medium', 'low']
    score: float                           # 优先级分数（归一化后的值）
    distance_from_center: float            # 距离雷达中心的距离
    is_missile: bool
    missile_type: Optional[Literal['MissileUp', 'MissileDown']] = None
    creation_timestamp: int = None
    
    def __post_init__(self):
        """初始化后处理"""
        if self.creation_timestamp is None:
            self.creation_timestamp = int(time.time() * 1000)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，用于JSON序列化"""
        result = asdict(self)
        # 展平position结构以保持与前端兼容
        result['position'] = self.position.to_dict()
        return result

@dataclass
class ThreatGenerationResult:
    """威胁生成结果"""
    threats: list[EnhancedThreat]
    radar_config: RadarConfig
    highest_priority_threat_id: Optional[str] = None
    generation_timestamp: int = None
    
    def __post_init__(self):
        if self.generation_timestamp is None:
            self.generation_timestamp = int(time.time() * 1000)
            
        # 自动计算最高优先级威胁
        if self.threats and self.highest_priority_threat_id is None:
            sorted_threats = sorted(self.threats, key=lambda t: t.score, reverse=True)
            self.highest_priority_threat_id = sorted_threats[0].id
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'threats': [threat.to_dict() for threat in self.threats],
            'radar_config': self.radar_config.to_dict(),
            'highest_priority_threat_id': self.highest_priority_threat_id,
            'generation_timestamp': self.generation_timestamp
        }

# 类型别名，用于更好的类型提示
ThreatType = Literal[
    'PrimaryAir',
    'SecondaryAir', 
    'PrimaryAntiAircraftArtillery',
    'SecondaryAntiAircraftArtillery',
    'PrimaryNaval',
    'SecondaryNaval'
]

MissileType = Literal['MissileUp', 'MissileDown']
PriorityLevel = Literal['high', 'medium', 'low'] 