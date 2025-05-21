import React, { useState, useCallback, useEffect, useRef } from 'react';
import { Stage, Layer, Circle, Line, Group, Text, Rect } from 'react-konva';
import PrimaryAirIcon from '../icons/PrimaryAirIcon';
import SecondaryAirIcon from '../icons/SecondaryNavalIcon';
import PrimaryAntiAircraftArtilleryIcon from '../icons/PrimaryAntiAircraftArtilleryIcon';
import SecondaryAntiAircraftArtilleryIcon from '../icons/SecondaryAntiAircraftArtilleryIcon';
import PrimaryNavalIcon from '../icons/PrimaryNavalIcon';
import SecondaryNavalIcon from '../icons/SecondaryAirIcon';
import MissileUpIcon from '../icons/MissileUpIcon';
import MissileDownIcon from '../icons/MissileDownIcon';
import useRadarData from '../hooks/useRadarData';
import { MessageType } from './CommunicationLog';
import { useAIAgent } from '../hooks/useAIAgent';
import agentStore from '../stores/AgentStore';
import { observer } from 'mobx-react-lite';
import radarStore from '../stores/RadarStore';
// import SAButtons from './SAButtons';

interface SAPageProps {
  width?: number;
  height?: number;
  onAddMessage?: (type: MessageType, content: string) => void;
  userId?: string;
}

// 添加威胁数据接口
interface ThreatData {
  id: string;
  type: string;
  source: string;
  distance: number;
  heading: number;
  priority: 'high' | 'medium' | 'low';
  label: string;
}

// 添加导弹数据接口
interface MissileData {
  id: string;
  type: 'MissileUp' | 'MissileDown';
  x: number;
  y: number;
}

// 按钮组件 - 使用普通DOM元素而非Konva
interface ButtonProps {
  label: string;
  onClick?: () => void;
}

const Button: React.FC<ButtonProps> = ({ label, onClick }) => {
  return (
    <button
      className="w-12 h-10 bg-gray-900 text-green-400 border-2 border-white rounded font-mono hover:bg-gray-800 focus:outline-none"
      onClick={onClick}
    >
    
    </button>
  );
};

const ICON_SIZE = 48;
const ICON_MAP = {
  PrimaryAir: PrimaryAirIcon,
  SecondaryAir: SecondaryAirIcon,
  PrimaryAntiAircraftArtillery: PrimaryAntiAircraftArtilleryIcon,
  SecondaryAntiAircraftArtillery: SecondaryAntiAircraftArtilleryIcon,
  PrimaryNaval: PrimaryNavalIcon,
  SecondaryNaval: SecondaryNavalIcon,
};
const iconColors = [
  '#ff0000', // PrimaryAirIcon
  '#ffff00', // SecondaryAirIcon
  '#ff0000', // PrimaryAntiAircraftArtilleryIcon
  '#ffff00', // SecondaryAntiAircraftArtilleryIcon
  '#ff0000', // PrimaryNavalIcon
  '#ffff00', // SecondaryNavalIcon
];

// 添加音频管理器
const AudioManager = {
  missileUp: new Audio('/sounds/MissileLaunch.wav'),
  missileDown: new Audio('/sounds/MissileLaunch.wav'),
  threatUpgrade: new Audio('/sounds/Tracking.wav'),
  saInit: new Audio('/sounds/ThreatNew.wav'),
  
  play(type: 'missileUp' | 'missileDown' | 'threatUpgrade' | 'saInit') {
    const audio = this[type];
    if (audio) {
      audio.currentTime = 0; // 重置音频播放位置
      audio.play().catch(err => console.error('播放音频失败:', err));
    }
  }
};

const SAPage: React.FC<SAPageProps> = observer(({ width = 900, height = 900, onAddMessage, userId: originalUserId}) => {
  // 删除本地 mock threats
  // const [threats] = useState<ThreatData[]>([ ... ]);

  // 获取优先级对应的颜色
  const getPriorityColor = (priority: string): string => {
    switch (priority) {
      case 'high': return '#ff0000';
      case 'medium': return '#ffff00';
      case 'low': return '#00ffff';
      default: return '#ffffff';
    }
  };
  const [userId, setUserId] = useState(originalUserId);

  useEffect(() => {
    if (originalUserId) {
      setUserId(originalUserId);
    }
  }, [originalUserId]);
  // 配置
  const config = {
    backgroundColor: '#000000',
    lineColor: '#00ff00',    // 绿色线条
    accentColor: '#ff0000',  // 红色强调线
    textColor: '#00ff00',    // 绿色文本
    centerX: width / 2,
    // 将圆心向下移动，将原来的centerY从height/2移动到更低的位置
    centerY: height * 0.6,   // 向下移动圆心位置到60%的高度位置
  };

  // 圆的半径 - 增大所有圆的半径
  const radius1 = 100; // 原来是70，增大到100
  // 计算第二个圆的半径，使其与底部白线相切
  // 底部线的位置约在stageHeight减去一定边距，这里设置为高度的90%
  const bottomLineY = height * 0.9;
  const radius2 = bottomLineY - config.centerY; // 使第二个圆与底部线相切
  const radius3 = radius2 * 1.7; // 第三个圆的半径，原来是1.5倍，现在增大到1.6倍
  
  // 计算弧线角度
  const arcStartAngle = 210; // 开始角度 (210度)
  const arcEndAngle = 330;   // 结束角度 (330度)
  



  // 随机旋转角度（0~360度）
  const [rotation] = React.useState(() => Math.random() * 360);

  // 方向字母和短线（E S W N，顺时针，带出头短线）
  const directionLabels = [
    { label: 'E', angle: 0 },
    { label: 'S', angle: 90 },
    { label: 'W', angle: 180 },
    { label: 'N', angle: 270 },
  ];
  const shortLen = 18; // 短线总长度
  const markerLines = directionLabels.map(({ label, angle }) => {
    const rad = ((angle + rotation) * Math.PI) / 180;
    const centerX = config.centerX;
    const centerY = config.centerY - 50;
    const r1 = radius1 - shortLen * 0.6;
    const r2 = radius1 + shortLen * 0.5;
    // 短线起点
    const x1 = centerX + r1 * Math.cos(rad);
    const y1 = centerY + r1 * Math.sin(rad);
    // 短线终点
    const x2 = centerX + r2 * Math.cos(rad);
    const y2 = centerY + r2 * Math.sin(rad);
    // 字母位置
    const textX = centerX + (r2 + 10) * Math.cos(rad);
    const textY = centerY + (r2 + 10) * Math.sin(rad);
    return {
      label,
      line: [x1, y1, x2, y2],
      textX,
      textY
    };
  });

  // 第三个圆弧刻度线 - 11等分
  const arcScaleLines = [];
  // 弧线总角度
  const totalArcAngle = 100; // 修改为100度，与Arc组件的angle值保持一致
  // 计算每一等分的角度
  const divisionAngle = totalArcAngle / 11; // 10个间隔产生11个刻度点
  
  // 弧线起始角度 (根据rotation值计算)
  const arcBaseAngle = -140; // 与Arc组件的rotation值相同
  
  // 生成11个刻度点
  for (let i = 0; i <= 10; i++) {
    const angle = arcBaseAngle + i * divisionAngle;
    const rad = (angle * Math.PI) / 180;
    
    arcScaleLines.push({
      innerX: config.centerX + (radius3 + 10) * Math.cos(rad), // 向内延伸
      innerY: config.centerY + (radius3 + 10) * Math.sin(rad),
      outerX: config.centerX + radius3 * Math.cos(rad),
      outerY: config.centerY + radius3 * Math.sin(rad)
    });
  }

  // 刻度线位置计算（第二个圆和第三个圆之间的刻度线）
  const scaleLines = [];
  for (let angle = 0; angle < 360; angle += 30) {
    // 只绘制在弧线范围内的刻度线 (210-330度)
    if (angle >= arcStartAngle - 360 && angle <= arcEndAngle - 360) {
      const rad = (angle * Math.PI) / 180;
      scaleLines.push({
        angle,
        innerX: config.centerX + radius2 * Math.cos(rad),
        innerY: config.centerY + radius2 * Math.sin(rad),
        outerX: config.centerX + (radius3 - 10) * Math.cos(rad),
        outerY: config.centerY + (radius3 - 10) * Math.sin(rad)
      });
    }
  }

  // 方向标记渲染函数
  const renderDirectionMarkers = () => {
    return directionLabels.map(({ label, angle }) => {
      // 只渲染在弧线范围内的方向标记
      if (angle >= arcStartAngle - 360 && angle <= arcEndAngle - 360) {
        const rad = (angle * Math.PI) / 180;
        const x = config.centerX + (radius2 - 25) * Math.cos(rad);
        const y = config.centerY + (radius2 - 25) * Math.sin(rad);
        return (
          <Text
            key={label}
            x={x}
            y={y}
            text={label}
            fill={config.lineColor}
            fontSize={16}
            align="center"
            verticalAlign="middle"
            offsetX={8}
            offsetY={8}
          />
        );
      }
      return null;
    });
  };

  // 创建按钮标签
  const topButtons = Array(5).fill(0).map((_, i) => `T${i + 1}`);
  const leftButtons = Array(5).fill(0).map((_, i) => `L${i + 1}`);
  const rightButtons = Array(5).fill(0).map((_, i) => `R${i + 1}`);
  
  // 按钮点击处理函数
  const handleButtonClick = (label: string) => {
    console.log(`按钮 ${label} 被点击`);
  };

  // 计算按钮容器尺寸
  const topContainerWidth = width; // 使顶部容器宽度与雷达宽度相同
  const sideContainerHeight = height * 0.8; // 侧边容器高度与雷达高度的80%相同

  // 随机分布icon
  const { connected, radarData, error, sendMessage, sendResetSA } = useRadarData();
 
  
  const [saThreats, setSaThreats] = useState(radarData?.saThreats ?? []);
  const [missiles, setMissiles] = useState<MissileData[]>([]);
  const [threatList, setThreatList] = useState<ThreatData[]>([]);
  
  // 添加refs控制日志写入
  const hasInitLogRef = useRef(false);
  const lastEmergencyRef = useRef<string | null>(null);
  const lastThreatsLengthRef = useRef<number>(0);
  // 记录最近一次SAEmergency的接收时间戳
  const lastEmergencyReceiveTimestampRef = useRef<number | null>(null);

  // 处理重置SA
  const handleResetSA = useCallback(() => {
    sendResetSA();
    setMissiles([]);
    setThreatList([]);
    hasInitLogRef.current = false;
    lastThreatsLengthRef.current = 0;
    if (typeof onAddMessage === 'function') {
      onAddMessage('sa_init', 'SA系统已重置，导弹状态已清空');
    }
  }, [sendResetSA, onAddMessage]);

  // 主动同步saThreats
  useEffect(() => {
    console.log('【SAPage】radarData?.saThreats changed:', radarData?.saThreats);
    if (radarData?.saThreats) {
      setSaThreats(radarData.saThreats);
    }
  }, [radarData?.saThreats]);

  // saThreats变化时，重置威胁列表，优先级为中等
  useEffect(() => {
    console.log('【SAPage】saThreats changed:', saThreats);
    if (saThreats.length > 0) {
      setThreatList(saThreats.map(t => ({
        id: t.id,
        type: t.type,
        label: t.label,
        source: t.label,
        distance: 0,
        heading: 0,
        priority: 'medium',
      })));
      
      // 修改日志写入逻辑：确保初始化日志写入
      if (!hasInitLogRef.current && onAddMessage) {
        console.log('【SAPage】Writing SA init log...'); // 调试日志
        onAddMessage('sa_init', `SA系统初始化完成，当前威胁数量：${saThreats.length}`);
        AudioManager.play('saInit');
        hasInitLogRef.current = true;
      }
    }
  }, [saThreats, onAddMessage]);

  // 监听 emergency 变化，自动处理（防止死循环）
  useEffect(() => {
    if (radarData?.emergency) {
      const eventId = JSON.stringify(radarData.emergency);
      if (lastEmergencyRef.current !== eventId) {
        const data = radarData.emergency;
        // 记录前端接收SAEmergency的本地时间戳
        const receiveTimestamp = Date.now();
        lastEmergencyReceiveTimestampRef.current = receiveTimestamp;
        // 上报日志到后端
        sendMessage && sendMessage({
          type: 'sa_emergency_received',
          receive_timestamp: receiveTimestamp,
          event: data.event,
          missileType: data.missileType,
          saThreats: data.saThreats
        });
        if (data.event === 'missile') {
          AudioManager.play(data.missileType === 'MissileUp' ? 'missileUp' : 'missileDown');
          const angle = Math.random() * Math.PI * 2;
          const r = radius2 + Math.random() * (radius3 - radius2);
          const x = config.centerX + r * Math.cos(angle);
          const y = config.centerY + r * Math.sin(angle);
          const missileType: 'MissileUp' | 'MissileDown' = data.missileType === 'MissileUp' ? 'MissileUp' : 'MissileDown';
          const newMissile: MissileData = {
            id: Date.now().toString(),
            type: missileType,
            x,
            y
          };
          setMissiles(prev => [...prev, newMissile]);
          setThreatList(prev => [{
            id: newMissile.id,
            type: 'missile_lock',
            label: data.missileType === 'MissileUp' ? '上升导弹' : '下降导弹',
            source: data.missileType === 'MissileUp' ? '上升导弹' : '下降导弹',
            distance: Math.floor(r / 100),
            heading: Math.floor((angle * 180 / Math.PI + 90) % 360),
            priority: 'high',
          }, ...prev]);
          if (onAddMessage) {
            console.log('Writing missile warning log...');
            onAddMessage('sa_missile', `警告！导弹来袭！类型：${data.missileType === 'MissileUp' ? '上升导弹' : '下降导弹'}`);
          }
        } else if (data.event === 'upgrade' && data.saThreats) {
          AudioManager.play('threatUpgrade');
          setSaThreats(data.saThreats);
          if (onAddMessage) {
            console.log('Writing threat upgrade log...');
            onAddMessage('sa_emergency', '收到临机事件：威胁升级，已有威胁提升为一级');
          }
        }
        lastEmergencyRef.current = eventId;
      }
    }
  }, [radarData?.emergency, radius2, radius3, config.centerX, config.centerY, onAddMessage, sendMessage]);



  // iconPositions 依赖 saThreats
  const iconPositions = React.useMemo(() => {
    return saThreats.map((threat) => {
      let angle;
      let r;
      if (threat.type.startsWith('Primary')) {
        // Primary类型仍然在radius2附近随机分布
        angle = Math.random() * 2 * Math.PI;
        r = radius2 + Math.random() * 20;
      } else {
        // 其余类型分布在radius3的上方弧线（-140°到-40°）
        // 转为弧度
        const minDeg = -140;
        const maxDeg = -40;
        angle = (minDeg + Math.random() * (maxDeg - minDeg)) * Math.PI / 180;
        r = radius2 + Math.random() * (radius3 - radius2);
      }
      const x = config.centerX + r * Math.cos(angle) - ICON_SIZE / 2;
      const y = config.centerY + r * Math.sin(angle) - ICON_SIZE / 2;
      return { x, y };
    });
  }, [config.centerX, config.centerY, radius2, radius3, saThreats]);

  // 英文类型转中文
  const TYPE_MAP: Record<string, string> = {
    PrimaryAir: '一级空中威胁',
    SecondaryAir: '二级空中威胁',
    PrimaryAntiAircraftArtillery: '一级防空炮',
    SecondaryAntiAircraftArtillery: '二级防空炮',
    PrimaryNaval: '一级水面威胁',
    SecondaryNaval: '二级水面威胁',
  };

  // 点击icon将其加入威胁列表首位且优先级为高
  const handleThreatIconClick = useCallback((threat: any) => {
    setThreatList(prev => {
      const idx = prev.findIndex(t => t.id === threat.id);
      let newList = [...prev];
      if (idx !== -1) {
        newList.splice(idx, 1);
      }
      newList.unshift({
        id: threat.id,
        type: threat.type,
        label: threat.label,
        source: threat.label,
        distance: 0,
        heading: 0,
        priority: 'high',
      });
      return newList;
    });
    // 确保威胁处理日志写入
    if (onAddMessage) {
      onAddMessage('sa_threat', `处理威胁：${threat.label || '导弹'}，已设为高优先级`);
    }
    // 上报点击日志到后端，带上最近一次receive_timestamp
    sendMessage && sendMessage({
      type: 'threat_clicked',
      threat_id: threat.id,
      label: threat.label,
      priority: 'high',
      timestamp: Date.now(),
      receive_timestamp: lastEmergencyReceiveTimestampRef.current,
      user_id: userId,
      event_owner: agentStore.currentOperationOwner,
    });
  }, [onAddMessage, sendMessage]);

  // 渲染导弹
  const renderMissiles = () => {
    return missiles.map(missile => {
      const Icon = missile.type === 'MissileUp' ? MissileUpIcon : MissileDownIcon;
      return (
        <Group key={missile.id} onClick={() => handleThreatIconClick(missile)}>
          <Icon
            x={missile.x}
            y={missile.y}
            size={30}
            color="#ff0000"
            strokeWidth={3}
          />
        </Group>
      );
    });
  };

  // 最内侧圆心扰动（±10像素）
  const [centerPerturb] = React.useState(() => ({
    dx: (Math.random() - 0.5) * 20, // -10~+10
    dy: (Math.random() - 0.5) * 20  // -10~+10
  }));

  // 智能体自动处理临机事件
  useAIAgent({
    isActive: agentStore.isAIActive,
    emergency: radarData?.emergency,
    onHandleEmergency: (threat) => {
      if (threat) {
        console.log(`[AI Agent] Handling emergency with provided threat: ${threat.id}, type: ${threat.type}`);
        handleThreatIconClick(threat);
        return;
      }

      // 如果没有提供threat，则作为后备方案重新查找威胁
      const bestThreat = threatList.find(threat => 
        (threat.type && threat.type.toLowerCase().includes('missile')) || 
        (threat.id && threat.id.includes('Primary'))
      ) || threatList[0];

      if (bestThreat) {
        console.log(`[AI Agent] Handling emergency with fallback threat: ${bestThreat.id}, type: ${bestThreat.type}`);
        handleThreatIconClick(bestThreat);
      }
    },
    getBestThreat: () => {
      // 如果当前emergency是missile类型，优先处理它
      if (radarData?.emergency?.event === 'missile') {
        const missileType = radarData.emergency.missileType;
        return {
          id: `missile_${Date.now()}`,
          type: 'missile',
          label: missileType === 'MissileUp' ? '上升导弹' : '下降导弹',
          source: missileType === 'MissileUp' ? '上升导弹' : '下降导弹',
          distance: 0,
          heading: 0,
          priority: 'high'
        };
      }

      // 如果是upgrade类型的emergency，检查新的saThreats数据
      if (radarData?.emergency?.event === 'upgrade' && radarData.emergency.saThreats) {
        // 在新的saThreats中查找Primary目标
        const primaryThreat = radarData.emergency.saThreats.find(threat => 
          threat.id.includes('Primary')
        );
        if (primaryThreat) {
          return {
            id: primaryThreat.id,
            type: primaryThreat.type,
            label: primaryThreat.label,
            source: primaryThreat.label,
            distance: 0,
            heading: 0,
            priority: 'high'
          };
        }
      }

      // 其次检查threatList中的威胁
      const missileThreat = threatList.find(threat => 
        (threat.type && threat.type.toLowerCase().includes('missile')) || 
        (threat.id && threat.id.includes('Primary'))
      );
      
      // 如果找到符合条件的威胁，返回它，否则返回第一个威胁
      return missileThreat || threatList[0];
    }
  });

  const [isStarted, setIsStarted] = useState(false);
  const [antennaAdjustmentRequired, setAntennaAdjustmentRequired] = useState(false);
  const [targetAntennaElevation, setTargetAntennaElevation] = useState<number | null>(null);
  const [confirmAntennaAdjustmentHandled, setConfirmAntennaAdjustmentHandled] = useState(false);

  useEffect(() => {
    console.log('[AI Radar Antenna Effect Check]', {
      isAIActive: agentStore.isAIActive,
      isStarted,
      antennaAdjustmentRequired,
      targetAntennaElevation,
    });
    if (
      agentStore.isAIActive &&
      isStarted &&
      antennaAdjustmentRequired &&
      targetAntennaElevation !== null
    ) {
      console.log(`[AI Radar] Antenna adjustment required. Target elevation: ${targetAntennaElevation}. AI is taking action.`);
      
      // Pass 'ai' as source and the sendMessage callback
      radarStore.setCurrentAntennaElevation(targetAntennaElevation, 'ai', sendMessage);
      
    
      console.log(`[AI Radar] Antenna elevation automatically set to ${targetAntennaElevation} by AI and requirement cleared.`);
    }
  }, [
    agentStore.isAIActive,
    isStarted,
    antennaAdjustmentRequired,
    targetAntennaElevation,
    sendMessage,
    confirmAntennaAdjustmentHandled,
    radarStore
  ]);

  return (
    <div className="flex flex-col items-center justify-center">
      <div className="flex flex-col items-center">
        {/* 顶部按钮 - 使用justify-between均匀分布 */}
        <div 
          className="flex justify-between mb-4" 
          style={{ width: topContainerWidth, padding: '0 20px' }}
        >
          {topButtons.map(label => (
            <Button key={label} label={label} onClick={() => handleButtonClick(label)} />
          ))}
        </div>
        
        <div className="flex">
          {/* 左侧按钮 - 使用flex-col和justify-between均匀分布 */}
          <div 
            className="flex flex-col justify-between mr-4 mt-12" 
            style={{ height: sideContainerHeight }}
          >
            {leftButtons.map((label, idx) => (
              <Button
                key={label}
                label={label}
                onClick={idx === 1 ? handleResetSA : () => handleButtonClick(label)}
              />
            ))}
          </div>
          
          {/* 雷达显示 - 仅包含雷达相关元素 */}
          <div className="sa-page bg-black" style={{ width, height }}>
            <Stage width={width} height={height}>
              <Layer>
                {/* 第一个圆（中心圆） */}
                <Circle
                  x={config.centerX + centerPerturb.dx}
                  y={config.centerY - 50 + centerPerturb.dy}
                  radius={radius1}
                  stroke={config.lineColor}
                  strokeWidth={1}
                />
                {/* 四个方向短线和字母 */}
                {markerLines.map((marker, i) => (
                  <React.Fragment key={marker.label}>
                    <Line
                      points={marker.line}
                      stroke={config.lineColor}
                      strokeWidth={2}
                    />
                    <Text
                      x={marker.textX}
                      y={marker.textY}
                      text={marker.label}
                      fill={config.lineColor}
                      fontSize={18}
                      align="center"
                      verticalAlign="middle"
                      offsetX={8}
                      offsetY={8}
                    />
                  </React.Fragment>
                ))}
                
                {/* 第二个圆 */}
                <Circle
                  x={config.centerX}
                  y={config.centerY - 50}
                  radius={radius2}
                  stroke={config.lineColor}
                  strokeWidth={1}
                />
                
                {/* 第三个圆（只显示120度弧线，去掉中心线） */}
                <Group>
                  <Arc
                    x={config.centerX}
                    y={config.centerY}
                    radius={radius3}
                    angle={100}
                    rotation={-140} // 弧线居中于顶部，-150度使120度的弧线位于顶部
                    stroke={config.lineColor}
                    strokeWidth={1}
                  />
                </Group>
                
                {/* 方向和刻度线 */}
                {renderDirectionMarkers && renderDirectionMarkers()}
                
                {/* 第二个和第三个圆之间的刻度线 */}
                {scaleLines && scaleLines.map((line, i) => (
                  <Line
                    key={`scale-${i}`}
                    points={[line.innerX, line.innerY, line.outerX, line.outerY]}
                    stroke={config.lineColor}
                    strokeWidth={1}
                  />
                ))}
                
                {/* 第三个圆上的11等分刻度线 */}
                {arcScaleLines && arcScaleLines.map((line, i) => (
                  <Line
                    key={`arc-scale-${i}`}
                    points={[line.innerX, line.innerY, line.outerX, line.outerY]}
                    stroke={config.lineColor}
                    strokeWidth={1}
                  />
                ))}
                
                {/* 底部横线 */}
                <Line
                  points={[0, bottomLineY, width, bottomLineY]}
                  stroke="#ffffff"
                  strokeWidth={2}
                />
                
                {/* 添加边框线，使边界可见 */}
                {/* <Rect
                  x={framePositions.startX}
                  y={framePositions.startY}
                  width={framePositions.endX - framePositions.startX}
                  height={framePositions.endY - framePositions.startY}
                  stroke={config.accentColor}
                  strokeWidth={2}
                  dash={[5, 5]}
                /> */}

                {/* 随机分布的icon */}
                {saThreats.map((threat, idx) => {
                  const IconComp = ICON_MAP[threat.type as keyof typeof ICON_MAP];
                  if (!IconComp) return null;
                  return (
                    <Group key={threat.id} onClick={() => handleThreatIconClick(threat)}>
                      <IconComp
                        x={iconPositions[idx].x}
                        y={iconPositions[idx].y - 100}
                        size={ICON_SIZE}
                        color={iconColors[Object.keys(ICON_MAP).indexOf(threat.type as keyof typeof ICON_MAP)]}
                        label={threat.label}
                      />
                    </Group>
                  );
                })}

                {/* 渲染导弹 */}
                {renderMissiles()}

              </Layer>
            </Stage>
          </div>
          
          {/* 右侧按钮 - 使用flex-col和justify-between均匀分布 */}
          <div 
            className="flex flex-col justify-between ml-4 mt-12" 
            style={{ height: sideContainerHeight }}
          >
            {rightButtons.map(label => (
              <Button key={label} label={label} onClick={() => handleButtonClick(label)} />
            ))}
          </div>
        </div>
      </div>
      
      {/* 威胁列表 */}
      <div className="w-full max-w-4xl bg-black border border-gray-700 rounded-md overflow-hidden" style={{marginTop: '-80px'}}>
        <div className="bg-gray-800 p-2 border-b border-gray-700">
          <h3 className="text-green-400 font-mono text-lg text-center">威胁列表</h3>
        </div>
        
        <div className="p-2 bg-gray-900 font-mono text-sm text-gray-300 flex border-b border-gray-800">
          <div className="w-8 text-center">#</div>
          <div className="w-32">类型</div>
          <div className="w-32">来源</div>
          <div className="w-48">距离/方位</div>
          <div className="w-24">优先级</div>
        </div>
        
        {threatList.map((threat, index) => (
          <div 
            key={threat.id} 
            className={`p-2 border-b border-gray-800 font-mono text-sm flex items-center ${
              index % 2 === 0 ? 'bg-gray-900' : 'bg-gray-950'
            }`}
          >
            <div className="w-8 text-center text-gray-400">{index + 1}</div>
            <div className="w-32 text-green-400">{TYPE_MAP[threat.type] || threat.type}</div>
            <div className="w-32 text-yellow-400">{threat.label}</div>
            <div className="w-48 text-blue-300">--</div>
            <div className="w-24 flex items-center">
              <span 
                className="w-3 h-3 rounded-full mr-2" 
                style={{ backgroundColor: threat.priority === 'high' ? '#ff0000' : threat.priority === 'medium' ? '#ffff00' : '#00ffff' }}
              ></span>
              <span className="text-white">{threat.priority === 'high' ? '高' : threat.priority === 'medium' ? '中' : '低'}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
});

// 自定义弧线组件
interface ArcProps {
  x: number;
  y: number;
  radius: number;
  angle: number;
  rotation?: number;
  stroke: string;
  strokeWidth: number;
}

const Arc: React.FC<ArcProps> = ({ x, y, radius, angle, rotation = 0, stroke, strokeWidth }) => {
  // 转换角度为弧度
  const angleRad = (angle * Math.PI) / 180;
  const rotationRad = (rotation * Math.PI) / 180;
  
  // 生成弧线点
  const points = [];
  const segments = Math.max(30, Math.floor(angle)); // 分段数，越大越平滑
  
  for (let i = 0; i <= segments; i++) {
    const segmentAngle = rotationRad + (i / segments) * angleRad;
    const pointX = x + radius * Math.cos(segmentAngle);
    const pointY = y + radius * Math.sin(segmentAngle);
    points.push(pointX, pointY);
  }
  
  return (
    <Line
      points={points}
      stroke={stroke}
      strokeWidth={strokeWidth}
      lineCap="round"
    />
  );
};

export default SAPage; 