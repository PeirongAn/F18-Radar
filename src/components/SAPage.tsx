import React, { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { Stage, Layer, Circle, Line, Group, Text, Rect } from 'react-konva';
import PrimaryAirIcon from '../icons/PrimaryAirIcon';
import SecondaryAirIcon from '../icons/SecondaryAirIcon';
import PrimaryAntiAircraftArtilleryIcon from '../icons/PrimaryAntiAircraftArtilleryIcon';
import SecondaryAntiAircraftArtilleryIcon from '../icons/SecondaryAntiAircraftArtilleryIcon';
import PrimaryNavalIcon from '../icons/PrimaryNavalIcon';
import SecondaryNavalIcon from '../icons/SecondaryNavalIcon';
import MissileUpIcon from '../icons/MissileUpIcon';
import MissileDownIcon from '../icons/MissileDownIcon';
import useRadarData from '../hooks/useRadarData';
import { MessageType } from './CommunicationLog';
import { useAIAgent } from '../hooks/useAIAgent';
import agentStore from '../stores/AgentStore';
import { observer } from 'mobx-react-lite';
import radarStore from '../stores/RadarStore';
import audioManager from '../managers/AudioManager';                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 
// import SAButtons from './SAButtons';

interface SAPageProps {
  width?: number;
  height?: number;
  onAddMessage?: (type: MessageType, content: string) => void;
  userId?: string;
  onResetSA?: () => void;
  onResetTargets?: () => void;
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
  // 为"查看结果"按钮使用更宽的样式
  const isResultButton = label === '查看结果';
  
  return (
    <button
      className={`${isResultButton ? 'w-20 h-10' : 'w-12 h-10'} bg-gray-900 text-green-400 border-2 border-white rounded font-mono hover:bg-gray-800 focus:outline-none text-xs`}
      onClick={onClick}
    >
      {label}
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

const SAPage: React.FC<SAPageProps> = observer(({ width = 900, height = 900, onAddMessage, userId: originalUserId, onResetSA, onResetTargets }) => {
  // 删除本地 mock threats
  // const [threats] = useState<ThreatData[]>([ ... ]);


  const [userId, setUserId] = useState(originalUserId);

  useEffect(() => {
    if (originalUserId) {
      setUserId(originalUserId);
    }
  }, [originalUserId]);

  // 从 agentStore 获取初始音频状态，并设置本地 state
  const [audioEnabled, setAudioEnabled] = useState(agentStore.audioEnabled);
  
  // 监听来自 agentStore 的变化，确保初始加载后能正确同步
  useEffect(() => {
    setAudioEnabled(agentStore.audioEnabled);
  }, [agentStore.audioEnabled]);
  
  // 处理手动切换
  const handleAudioToggle = useCallback(() => {
    agentStore.toggleAudioEnabled();
  }, []);

  const { connected, radarData, error, sendMessage, sendResetSA } = useRadarData();

  // 使用 useEffect 监听来自 useRadarData 的 audioEnabled 状态
  useEffect(() => {
    if (radarData && typeof radarData.audioEnabled === 'boolean') {
      console.log(`[SAPage] Audio state updated from config: ${radarData.audioEnabled}`);
    }
  }, [radarData?.audioEnabled]);

  // 添加刻度数值标记状态
  const [scaleValues] = useState(() => ({
    leftScale: Math.floor(Math.random() * 900) + 100,
    rightScale: Math.floor(Math.random() * 900) + 100
  }));

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

  // 添加动态旋转角度状态
  const [dynamicRotation, setDynamicRotation] = React.useState(0);

  // 方向字母和短线（E S W N，顺时针，带出头短线）
  const directionLabels = [
    { label: 'E', angle: 0 },
    { label: 'S', angle: 90 },
    { label: 'W', angle: 180 },
    { label: 'N', angle: 270 },
  ];
  const shortLen = 18; // 短线总长度
  const markerLines = directionLabels.map(({ label, angle }) => {
    // 使用组合的旋转角度：初始随机角度 + 动态旋转角度
    const totalRotation = rotation + dynamicRotation;
    const rad = ((angle + totalRotation) * Math.PI) / 180;
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

  // 刻度数值标记渲染函数
  const renderScaleValues = () => {
    const scaleMarkers = [];
    const totalArcAngle = 100;
    const divisionAngle = totalArcAngle / 10; // 10个间隔
    const arcBaseAngle = -140;
    
    // 左侧第4个刻度（索引3）
    const leftScaleIndex = 3;
    const leftAngle = arcBaseAngle + leftScaleIndex * divisionAngle;
    // 根据内圈旋转调整数值显示角度
    const leftAdjustedAngle = leftAngle + rotation + dynamicRotation;
    const leftRad = (leftAngle * Math.PI) / 180;
    const leftX = config.centerX + (radius3 - 30) * Math.cos(leftRad); // 移到弧线内侧
    const leftY = config.centerY + (radius3 - 30) * Math.sin(leftRad);
    
    // 计算基于旋转的数值（模拟雷达扫描数值变化）
    const leftDisplayValue = Math.floor(scaleValues.leftScale + (leftAdjustedAngle % 360) / 10);
    
    // 绿色数字，无背景圆圈
    scaleMarkers.push(
      <Text
        key="left-scale"
        x={leftX}
        y={leftY}
        text={leftDisplayValue.toString()}
        fill="#00ff00"  // 绿色数值
        fontSize={16}   // 增大字体
        fontFamily="monospace"
        align="center"
        verticalAlign="middle"
        offsetX={8}
        offsetY={8}
      />
    );
    
    // 右侧第2个刻度（索引8）
    const rightScaleIndex = 8;
    const rightAngle = arcBaseAngle + rightScaleIndex * divisionAngle;
    // 根据内圈旋转调整数值显示角度
    const rightAdjustedAngle = rightAngle + rotation + dynamicRotation;
    const rightRad = (rightAngle * Math.PI) / 180;
    const rightX = config.centerX + (radius3 - 30) * Math.cos(rightRad); // 移到弧线内侧
    const rightY = config.centerY + (radius3 - 30) * Math.sin(rightRad);
    
    // 计算基于旋转的数值（模拟雷达扫描数值变化）
    const rightDisplayValue = Math.floor(scaleValues.rightScale + (rightAdjustedAngle % 360) / 10);
    
    // 绿色数字，无背景圆圈
    scaleMarkers.push(
      <Text
        key="right-scale"
        x={rightX}
        y={rightY}
        text={rightDisplayValue.toString()}
        fill="#00ff00"  // 绿色数值
        fontSize={16}   // 增大字体
        fontFamily="monospace"
        align="center"
        verticalAlign="middle"
        offsetX={8}
        offsetY={8}
      />
    );
    
    // // 每5秒输出一次调试信息
    // if (Math.floor(Date.now() / 5000) % 5 === 0) {
    //   console.log(`📊 刻度数值更新: 左侧=${leftDisplayValue}(索引${leftScaleIndex}), 右侧=${rightDisplayValue}(索引${rightScaleIndex}), 旋转角度=${dynamicRotation.toFixed(1)}°`);
    // }
    
    return scaleMarkers;
  };

  // 创建按钮标签
  const topButtons = Array(5).fill(0).map((_, i) => i === 2 ? '查看结果' : `T${i + 1}`);
  const leftButtons = Array(5).fill(0).map((_, i) => i === 1 ? '重置' : `T${i + 1}`);
  const rightButtons = Array(5).fill(0).map((_, i) => `R${i + 1}`);
  
  // 按钮点击处理函数
  const handleButtonClick = (label: string) => {
    console.log(`按钮 ${label} 被点击`);
    
    
    // 当点击第3个按钮（查看结果）时，显示选择结果
    if (label === '查看结果' && userSelection) {
      const { threat, isCorrect } = userSelection;
      
      // 获取正确的威胁标签
      const getThreatLabel = (threat: any): string => {
        if (threat.type === 'MissileUp') return '上升导弹';
        if (threat.type === 'MissileDown') return '下降导弹';
        return threat.label || '未知威胁';
      };

      // 生成所有威胁的得分信息日志
      if (onAddMessage && threatsWithScore.length > 0) {
        // 添加得分详情日志
        onAddMessage('sa_threat', '=== 威胁得分排序详情 ===');
        
        const effectiveCenterY = config.centerY - 50; // 正确的圆心Y坐标
        
        threatsWithScore.forEach((threatInfo, index) => {
          const threatLabel = getThreatLabel(threatInfo.threat);
          const threatId = threatInfo.threat.id;
          const originalIndex = threatInfo.originalIndex;
          
          // 计算与本机的距离（像素距离）
          let distance = 0;
          let threatNumber = '未知';
          
          if (threatInfo.isMissile) {
            // 导弹距离计算
            const missile = threatInfo.threat as MissileData;
            distance = Math.sqrt(Math.pow(missile.x - config.centerX, 2) + Math.pow(missile.y - effectiveCenterY, 2));
            threatNumber = `导弹${originalIndex + 1}`;
          } else {
            // 常规威胁距离计算
            const pos = iconPositions[originalIndex];
            if (pos) {
              distance = Math.sqrt(Math.pow(pos.x - config.centerX, 2) + Math.pow(pos.y - effectiveCenterY, 2));
            }
            // 从威胁列表中查找对应的标号
            const sortedIndex = threatIdToSortedIndexMap.get(threatId);
            threatNumber = sortedIndex !== undefined ? `[${sortedIndex}]` : `威胁${originalIndex + 1}`;
          }
          
          const scoreText = `排名${index + 1}: ${threatLabel} - 得分: ${threatInfo.score.toFixed(2)}${threatInfo.isMissile ? ' (导弹)' : ''} [ID: ${threatId}, 序号: ${originalIndex}, 标号: ${threatNumber}, 距离: ${distance.toFixed(1)}px]`;
          onAddMessage('sa_threat', scoreText);
        });
        
        onAddMessage('sa_threat', '========================');
      }

      if (isCorrect) {
        setCompletedThreat(`✅ 正确！${getThreatLabel(threat)}`);
      } else {
        const highestPriorityThreat = getCurrentHighestPriorityThreat();
        const correctThreatLabel = highestPriorityThreat ? highestPriorityThreat.label : '未知威胁';
        setCompletedThreat(`❌ 错误！正确答案是：${correctThreatLabel}`);
      }
      
      setShowTaskComplete(true);
      
      // 如果选择错误，需要确保最高优先级威胁也显示红色边框
      if (!isCorrect) {
        // 将正确答案也添加到威胁列表中，确保显示红色边框
        const highestPriorityThreat = getCurrentHighestPriorityThreat();
        if (highestPriorityThreat) {
          const getOriginalPriority = (threat: any): 'high' | 'medium' | 'low' => {
            if (threat.type?.toLowerCase().includes('missile')) return 'high';
            if (threat.type?.includes('Primary') || threat.id?.includes('Primary')) return 'high';
            return 'medium';
          };
          
          setThreatList(prev => {
            const newList = [...prev.filter(t => t.id !== highestPriorityThreat.id)];
            // 将正确答案添加到列表中（但不放在第一位）
            newList.push({
              id: highestPriorityThreat.id,
              type: highestPriorityThreat.type,
              label: highestPriorityThreat.label,
              source: highestPriorityThreat.label,
              distance: 0,
              heading: 0,
              priority: getOriginalPriority(highestPriorityThreat),
            });
            return newList;
          });
        }
      }
      
      // 清除用户选择状态
      setUserSelection(null);
    }
  };

  // 计算按钮容器尺寸
  const topContainerWidth = width; // 使顶部容器宽度与雷达宽度相同
  const sideContainerHeight = height * 0.8; // 侧边容器高度与雷达高度的80%相同

  // 随机分布icon
  const [saThreats, setSaThreats] = useState(radarData?.saThreats ?? []);
  const [missiles, setMissiles] = useState<MissileData[]>([]);
  const [threatList, setThreatList] = useState<ThreatData[]>([]);
  
  // 添加一个状态，用于判断是否已经进行过选择
  const hasSelectionBeenMade = useMemo(() => threatList.length > 0, [threatList]);

  // 添加refs控制日志写入
  const hasInitLogRef = useRef(false);
  const lastEmergencyRef = useRef<string | null>(null);
  const lastThreatsLengthRef = useRef<number>(0);
  // 记录最近一次SAEmergency的接收时间戳
  const lastEmergencyReceiveTimestampRef = useRef<number | null>(null);

  // 添加任务结束弹窗状态
  const [showTaskComplete, setShowTaskComplete] = useState(false);
  const [completedThreat, setCompletedThreat] = useState<string>('');
  
  // 添加用户选择状态（但不立即显示结果）
  const [userSelection, setUserSelection] = useState<{threat: any, isCorrect: boolean} | null>(null);

  // 添加接管按钮处理函数
  const handleTakeControl = useCallback(() => {
    console.log('[SA页面] 用户手动接管控制');
    // 禁用AI控制
    // agentStore.setAIActive(false);
    
    // 发送接管消息到服务器
    if (sendMessage) {
      sendMessage({
        type: 'user_take_control',
        timestamp: Date.now(),
        user_id: userId || 'current_user',
        page: 'SA' // 标记是SA页面的接管
      });
    }
    
    console.log('✅ [SA页面] 用户已接管威胁排序控制');
  }, [sendMessage, userId]);

  // 添加F10快捷键监听
  useEffect(() => {
    const handleKeyPress = (event: KeyboardEvent) => {
      if (event.key === 'F10') {
        event.preventDefault();
        handleTakeControl();
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => {
      window.removeEventListener('keydown', handleKeyPress);
    };
  }, [handleTakeControl]);

  // 处理重置SA
  const handleResetSA = useCallback(() => {
    console.log('====== SA系统重置 ======');
    
    // 发送重置消息到服务器
    sendResetSA();
    
    // 核心修复：重置 MobX store 中的临机事件状态
    radarStore.resetSAEmergency();

    // 清除所有本地状态
    setMissiles([]);
    setThreatList([]);
    setSaThreats([]);
    setShowTaskComplete(false); // 关闭任务完成弹窗
    setCompletedThreat(''); // 清空已完成威胁
    setUserSelection(null); // 清空用户选择
    setDynamicRotation(0); // 重置仪表盘旋转
    
    // 重置控制标志
    hasInitLogRef.current = false;
    lastThreatsLengthRef.current = 0;
    lastEmergencyRef.current = null;
    lastEmergencyReceiveTimestampRef.current = null;
    
    // 记录重置日志
    if (typeof onAddMessage === 'function') {
      onAddMessage('sa_init', 'SA系统已重置，所有威胁和状态已清空');
    }
    
    console.log('✅ SA系统重置完成');
  }, [sendResetSA, onAddMessage]);

  // 主动同步saThreats
  useEffect(() => {
    console.log('【SAPage】radarData?.saThreats changed:', radarData?.saThreats);
    if (radarData?.saThreats) {
      setSaThreats(radarData.saThreats);
    }
  }, [radarData?.saThreats]);

  // saThreats变化时，只负责写入初始化日志，不再自动填充威胁列表
  useEffect(() => {
    console.log('【SAPage】saThreats changed:', saThreats);
    if (saThreats.length > 0) {
      // 修改日志写入逻辑：确保初始化日志写入
      if (!hasInitLogRef.current && onAddMessage) {
        console.log('【SAPage】Writing SA init log...'); // 调试日志
        onAddMessage('sa_init', `SA系统初始化完成，当前威胁数量：${saThreats.length}`);
        audioManager.play('saInit');
        hasInitLogRef.current = true;
      }
    } else {
      // 当威胁列表从服务器清空时（例如任务重置），本地也清空
      setThreatList([]);
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
        // // 上报日志到后端
        // sendMessage && sendMessage({
        //   type: 'sa_emergency_received',
        //   receive_timestamp: receiveTimestamp,
        //   event: data.event,
        //   missileType: data.missileType,
        //   saThreats: data.saThreats
        // });
        if (data.event === 'missile') {
          audioManager.play(data.missileType === 'MissileUp' ? 'missileUp' : 'missileDown');
          
          // 优化导弹位置分布策略
          let angle, r, rawX, rawY;
          let attempts = 0;
          const maxAttempts = 10;
          const effectiveCenterY = config.centerY - 50; // 统一使用正确的圆心Y坐标
          
          do {
            // 导弹更倾向于出现在上半圆区域（-π到0，即上方180度）
            // 这样更符合导弹威胁的逻辑，且不容易超出边界
            if (Math.random() < 0.7) {
              // 70%概率在上半圆
              angle = -Math.PI + Math.random() * Math.PI; // -π到0
            } else {
              // 30%概率在任意位置
              angle = Math.random() * Math.PI * 2;
            }
            
            // 导弹距离稍微靠近内圈，避免太边缘
            r = radius2 + Math.random() * (radius3 - radius2) * 0.8; // 只使用80%的范围
            
            rawX = config.centerX + r * Math.cos(angle);
            rawY = effectiveCenterY + r * Math.sin(angle);
            
            attempts++;
          } while (
            (rawX < 60 || rawX > width - 60 || rawY < 60 || rawY > height - 60) && 
            attempts < maxAttempts
          );
          
          // 添加边界检查，确保导弹在可视区域内
          const missileSize = 30; // 导弹图标大小
          const x = Math.max(missileSize, Math.min(width - missileSize, rawX));
          const y = Math.max(missileSize, Math.min(height - missileSize, rawY));
          
          console.log(`🚀 导弹位置: 尝试${attempts}次, 原始(${rawX.toFixed(0)}, ${rawY.toFixed(0)}) -> 修正后(${x.toFixed(0)}, ${y.toFixed(0)})`);
          
          const missileType: 'MissileUp' | 'MissileDown' = data.missileType === 'MissileUp' ? 'MissileUp' : 'MissileDown';
          const newMissile: MissileData = {
            id: Date.now().toString(),
            type: missileType,
            x,
            y
          };
          setMissiles(prev => [...prev, newMissile]);
          if (onAddMessage) {
            console.log('Writing missile warning log...');
            onAddMessage('sa_missile', `警告！导弹来袭！类型：${data.missileType === 'MissileUp' ? '上升导弹' : '下降导弹'}`);
          }
        } else if (data.event === 'upgrade' && data.saThreats) {
          audioManager.play('threatUpgrade');
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
    const positions: Array<{x: number, y: number}> = [];
    const effectiveCenterY = config.centerY - 50; // 统一使用正确的圆心Y坐标
    
    // 检查位置是否与已有位置冲突
    const isPositionConflicting = (newPos: {x: number, y: number}, existingPositions: Array<{x: number, y: number}>, minDistance: number = ICON_SIZE * 1.2) => {
      return existingPositions.some(pos => {
        const distance = Math.sqrt(Math.pow(newPos.x - pos.x, 2) + Math.pow(newPos.y - pos.y, 2));
        return distance < minDistance;
      });
    };
    
    // 分别处理Primary和Secondary威胁
    const primaryThreats = saThreats.filter((t: { type: string; }) => t.type.startsWith('Primary'));
    const secondaryThreats = saThreats.filter((t: { type: string; }) => !t.type.startsWith('Primary'));
    
    // 先处理Primary威胁 - 在内圈完整圆圈中分布
    primaryThreats.forEach((threat: { type: string; }, index: string | number) => {
      let attempts = 0;
      let pos;
      
      do {
        const angle = Math.random() * 2 * Math.PI;
        const r = radius2 + Math.random() * 40; // 在radius2附近分布，范围稍大一些
        const x = config.centerX + r * Math.cos(angle) - ICON_SIZE / 2;
        const y = effectiveCenterY + r * Math.sin(angle) - ICON_SIZE / 2;
        
        // 确保在屏幕范围内
        const clampedX = Math.max(ICON_SIZE, Math.min(width - ICON_SIZE, x));
        const clampedY = Math.max(ICON_SIZE, Math.min(height - ICON_SIZE, y));
        
        pos = { x: clampedX, y: clampedY };
        attempts++;
      } while (isPositionConflicting(pos, positions) && attempts < 20);
      
      positions.push(pos);
    });
    
    // 再处理Secondary威胁 - 在外圈弧线区域分布
    secondaryThreats.forEach((threat: any, index: number) => {
      let attempts = 0;
      let pos;
      
      do {
        // 扩大Secondary威胁的分布角度范围
        const minDeg = -180; // 进一步扩大角度范围
        const maxDeg = 0;     // 覆盖整个上半圆
        
        let angle;
        if (secondaryThreats.length > 1) {
          // 多个Secondary威胁时，先尝试均匀分布
          const angleStep = (maxDeg - minDeg) / secondaryThreats.length;
          const baseAngle = minDeg + angleStep * index + angleStep * 0.5;
          // 添加随机偏移避免完全对齐
          angle = (baseAngle + (Math.random() - 0.5) * angleStep * 0.4) * Math.PI / 180;
        } else {
          // 单个Secondary威胁随机分布
          angle = (minDeg + Math.random() * (maxDeg - minDeg)) * Math.PI / 180;
        }
        
        // 在radius2到radius3之间随机分布半径
        const radiusRange = radius3 - radius2;
        const r = radius2 + Math.random() * radiusRange;
        
        const x = config.centerX + r * Math.cos(angle) - ICON_SIZE / 2;
        const y = effectiveCenterY + r * Math.sin(angle) - ICON_SIZE / 2;
        
        // 确保在屏幕范围内
        const clampedX = Math.max(ICON_SIZE, Math.min(width - ICON_SIZE, x));
        const clampedY = Math.max(ICON_SIZE, Math.min(height - ICON_SIZE, y));
        
        pos = { x: clampedX, y: clampedY };
        attempts++;
      } while (isPositionConflicting(pos, positions, ICON_SIZE * 1.1) && attempts < 30);
      
      positions.push(pos);
    });
    
    // 重新组装positions数组，按照原始saThreats的顺序
    const finalPositions = saThreats.map((threat: { type: string; id: any; }) => {
      const isPrimary = threat.type.startsWith('Primary');
      if (isPrimary) {
        const primaryIndex = primaryThreats.findIndex((t: { id: any; }) => t.id === threat.id);
        return positions[primaryIndex];
      } else {
        const secondaryIndex = secondaryThreats.findIndex((t: { id: any; }) => t.id === threat.id);
        return positions[primaryThreats.length + secondaryIndex];
      }
    });
    
    // 调试信息：输出威胁分布情况
    if (saThreats.length > 0) {
      const primaryCount = primaryThreats.length;
      const secondaryCount = secondaryThreats.length;
      console.log(`🎯 威胁分布更新: 总数=${saThreats.length}, Primary=${primaryCount}, Secondary=${secondaryCount}`);
      
      // 输出每个威胁的位置信息
      saThreats.forEach((threat: { label: any; type: any; }, index: string | number) => {
        const pos = finalPositions[index];
        console.log(`  - ${threat.label} (${threat.type}): (${pos.x.toFixed(0)}, ${pos.y.toFixed(0)})`);
      });
    }
    
    return finalPositions;
  }, [config.centerX, config.centerY, radius2, radius3, saThreats, width, height]);

  // 英文类型转中文
  const TYPE_MAP: Record<string, string> = {
    PrimaryAir: '一级空中威胁',
    SecondaryAir: '二级空中威胁',
    PrimaryAntiAircraftArtillery: '一级防空炮',
    SecondaryAntiAircraftArtillery: '二级防空炮',
    PrimaryNaval: '一级水面威胁',
    SecondaryNaval: '二级水面威胁',
  };

  // 为包含分数的威胁定义接口
  interface ThreatWithScore {
    threat: any;
    score: number;
    isMissile: boolean;
    originalIndex: number; // 新增：用于打破平局的原始索引
  }

  // 计算所有威胁的分数并排序
  const threatsWithScore = useMemo(() => {
    // 1. 定义威胁类型的权重
    const getTypeWeight = (type: string): number => {
      if (type.toLowerCase().includes('missile')) return 210; // 导弹权重最高
      if (type.startsWith('Primary')) return 210;           // Primary类型次之
      if (type.startsWith('Secondary')) return 200;         // Secondary类型权重较低
      return 80; // 其他未知类型
    };

    const allThreats: ThreatWithScore[] = [];
    const effectiveCenterY = config.centerY - 50; // 正确的圆心Y坐标

    // 2. 计算导弹的威胁分数
    missiles.forEach((missile, index) => {
      const distance = Math.sqrt(Math.pow(missile.x - config.centerX, 2) + Math.pow(missile.y - effectiveCenterY, 2));
      const weight = getTypeWeight('missile');
      const score = weight / (distance + 1e-6);
      allThreats.push({
        threat: missile,
        score,
        isMissile: true,
        originalIndex: index, // 存储原始索引
      });
    });

    // 3. 计算常规威胁的分数
    saThreats.forEach((threat: { type: string; }, index: number) => {
      const pos = iconPositions[index];
      if (pos) {
        const distance = Math.sqrt(Math.pow(pos.x - config.centerX, 2) + Math.pow(pos.y - effectiveCenterY, 2));
        const weight = getTypeWeight(threat.type);
        const score = weight / (distance + 1e-6);
        allThreats.push({
          threat,
          score,
          isMissile: false,
          originalIndex: index, // 存储原始索引
        });
      }
    });

    // 修改排序逻辑：当分数相同时，使用类型和原始索引作为"打破平局"的规则
    return allThreats.sort((a, b) => {
      const scoreDiff = b.score - a.score;
      // 使用一个极小值(epsilon)来比较浮点数
      if (Math.abs(scoreDiff) > 1e-9) {
        return scoreDiff;
      }
      // 如果分数相同，导弹优先
      if (a.isMissile !== b.isMissile) {
        return a.isMissile ? -1 : 1;
      }
      // 如果类型也相同，则比较原始索引
      return a.originalIndex - b.originalIndex;
    });
  }, [missiles, saThreats, iconPositions, config.centerX, config.centerY]);

  // 创建一个从威胁ID到其排序后索引的映射，方便快速查找
  const threatIdToSortedIndexMap = useMemo(() => 
    new Map(threatsWithScore.map((item, index) => [item.threat.id, index]))
  , [threatsWithScore]);

  // 获取当前最高优先级威胁的函数
  const getCurrentHighestPriorityThreat = useCallback(() => {
    if (threatsWithScore.length === 0) {
      return null;
    }

    const bestThreatInfo = threatsWithScore[0];

    if (!bestThreatInfo) return null;

    if (bestThreatInfo.isMissile) {
      const missile = bestThreatInfo.threat as MissileData;
      return {
        id: missile.id,
        type: 'missile',
        label: missile.type === 'MissileUp' ? '上升导弹' : '下降导弹',
        isMissile: true,
      };
    } else {
      const saThreat = bestThreatInfo.threat as {id: string, type: string, label: string};
      return {
        id: saThreat.id,
        type: saThreat.type,
        label: saThreat.label,
        isMissile: false,
      };
    }
  }, [threatsWithScore]);

  // 将对"选中"和"最高优先级"目标的引用移动到这里
  const highestPriorityThreat = useMemo(() => getCurrentHighestPriorityThreat(), [getCurrentHighestPriorityThreat]);
  const selectedThreatId = useMemo(() => threatList[0]?.id, [threatList]);

  useEffect(()=> {
    console.log('[AI Agent]xxxxxxx', threatList)
  }, [threatList])

  // 点击icon将其加入威胁列表首位但保持原优先级
  const handleThreatIconClick = useCallback((threat: any, eventOwner: string) => {
    console.log('[AI Agent] handleThreatIconClick', threat, eventOwner)
    const highestPriorityThreat = getCurrentHighestPriorityThreat();
    const isClickedHighestPriority = highestPriorityThreat && (threat.id === highestPriorityThreat.id);

    const getOriginalPriority = (threat: any): 'high' | 'medium' | 'low' => {
      if (threat.type?.toLowerCase().includes('missile')) return 'high';
      if (threat.type?.includes('Primary') || threat.id?.includes('Primary')) return 'high';
      return 'medium';
    };

    // 统一获取威胁标签的函数
    const getThreatLabel = (threat: any): string => {
      if (threat.type === 'MissileUp') return '上升导弹';
      if (threat.type === 'MissileDown') return '下降导弹';
      return threat.label || '未知威胁';
    };

    const originalPriority = getOriginalPriority(threat);
    const threatLabel = getThreatLabel(threat);

    setThreatList(prev => {
      const newList = [...prev.filter(t => t.id !== threat.id)];
      newList.unshift({
        id: threat.id,
        type: threat.type,
        label: threatLabel,
        source: threatLabel,
        distance: 0,
        heading: 0,
        priority: originalPriority,
      });
      return newList;
    });

    // 存储用户选择，但不立即显示弹窗
    setUserSelection({
      threat,
      isCorrect: !!isClickedHighestPriority
    });
    
    // 发送威胁选择消息，区分人工和AI操作
    if (sendMessage) {
      
      sendMessage({
        type: 'threat_clicked',
        threat_id: threat.id,
        label: threatLabel,
        priority: originalPriority,
        is_highest_priority: !!isClickedHighestPriority,
        timestamp: Date.now(),
        receive_timestamp: lastEmergencyReceiveTimestampRef.current,
        user_id: userId,
        event_owner: eventOwner,
        operation_type: 'icon_click', // 标识这是通过图标点击的操作
      });
    }
    
    // 确保威胁处理日志写入
    if (onAddMessage) {
      const actor = agentStore.isAIActive ? '[AI]' : '[用户]';
      const priorityText = originalPriority === 'high' ? '高' : originalPriority === 'medium' ? '中' : '低';
      onAddMessage('sa_threat', `${actor} 选择威胁：${threatLabel}，优先级：${priorityText}，等待确认`);
    }
  }, [getCurrentHighestPriorityThreat, onAddMessage, sendMessage, userId, lastEmergencyReceiveTimestampRef]);

  // 渲染导弹
  const renderMissiles = () => {
    return missiles.map(missile => {
      const Icon = missile.type === 'MissileUp' ? MissileUpIcon : MissileDownIcon;
      const isSelected = missile.id === selectedThreatId;
      const isHighestPriority = missile.id === highestPriorityThreat?.id;

      return (
        <Group key={missile.id} onClick={() => handleThreatIconClick(missile, 'manual')}>
          {/* 只有在做出选择后才渲染虚线框 */}
          {hasSelectionBeenMade && (isSelected || (showTaskComplete && isHighestPriority)) && (
            <Rect
              x={missile.x - 5}
              y={missile.y - 5}
              width={30 + 10} // missile icon size is 30
              height={30 + 10}
              stroke={showTaskComplete && isHighestPriority ? '#ff4136' : '#ffd700'} // 确认后最高威胁显示红色，否则黄色
              strokeWidth={2}
              dash={[6, 3]} // 虚线样式
              cornerRadius={5}
            />
          )}
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

  // 稳定化AI处理函数
  const handleEmergency = useCallback((threat: any) => {
    if (threat) {
      console.log(`[AI Agent] Handling emergency with provided threat: ${threat.id}, type: ${threat.type}`);
      handleThreatIconClick(threat, 'AI');
      return;
    }

    // 如果没有提供threat，则作为后备方案重新查找威胁
    const bestThreat = threatList.find(threat => 
      (threat.type && threat.type.toLowerCase().includes('missile')) || 
      (threat.id && threat.id.includes('Primary'))
    ) || threatList[0];

    if (bestThreat) {
      console.log(`[AI Agent] Handling emergency with fallback threat: ${bestThreat.id}, type: ${bestThreat.type}`);
      handleThreatIconClick(bestThreat, 'AI');
    }
  }, [handleThreatIconClick, threatList]);

  const getBestThreat = useCallback(() => {
    if (threatsWithScore.length === 0) return null;

    const level = agentStore.currentAILevel;
    const probabilities = agentStore.currentAILevelConfig?.decision_probabilities || [1.0];
    
    // 根据配置生成准确率（从正确池子选择的概率）
    let accuracy = 1.0; // 默认值
    if (probabilities.length === 1) {
      // 只有一个值，直接使用
      accuracy = probabilities[0];
    } else if (probabilities.length >= 2) {
      // 有两个或多个值，第一个是最小值，第二个是最大值，在范围内随机生成
      const min = probabilities[0];
      const max = probabilities[1];
      accuracy = parseFloat((Math.random() * (max - min) + min).toFixed(2));
    }
    
    // 根据准确率决定选择：正确池子 vs 错误池子
    const randomChoice = Math.random();
    let choiceIndex = 0;
    
    if (randomChoice <= accuracy) {
      // 从正确池子选择：选择最佳威胁（排序第一的）
      choiceIndex = 0;
    } else {
      // 从错误池子选择：选择非最佳威胁
      if (threatsWithScore.length > 1) {
        choiceIndex = Math.floor(Math.random() * (threatsWithScore.length - 1)) + 1;
      } else {
        // 如果只有一个威胁，即使要选错误的，也只能选这个
        choiceIndex = 0;
      }
    }
    
    const bestThreatInfo = threatsWithScore[choiceIndex];

    if (!bestThreatInfo) return null;

    console.log(`[AI Agent] Level: ${level}, Accuracy: ${accuracy}, Choice Index: ${choiceIndex}, Threat: ${bestThreatInfo.threat.label || bestThreatInfo.threat.type}`);

    // 返回被选中威胁的原始对象，因为 handleThreatIconClick 需要它
    return bestThreatInfo.threat;
  }, [threatsWithScore, agentStore.currentAILevel, agentStore.currentAILevelConfig]);

  // 智能体自动处理临机事件
  useAIAgent({
    isActive: agentStore.isAIActive,
    emergency: radarData?.emergency,
    onHandleEmergency: handleEmergency,
    getBestThreat: getBestThreat
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

  useEffect(() => {
    // 仪表盘间歇式旋转 - 旋转一段时间后暂停，模拟真实雷达扫描
    let animationId: number;
    let stateChangeTimeout: number;
    let lastTime = 0;
    let isRotating = true; // 旋转状态标志
    
    const rotationSpeed = 12; // 旋转速度：每秒12度（旋转时）
    const rotationDuration = 8000; // 旋转持续时间：8秒
    const pauseDuration = 2000; // 暂停持续时间：2秒
    
    // console.log(`🎯 仪表盘开始间歇式旋转，旋转${rotationDuration/1000}秒，暂停${pauseDuration/1000}秒`);
    
    const animate = (currentTime: number) => {
      if (lastTime === 0) lastTime = currentTime;
      const deltaTime = (currentTime - lastTime) / 1000; // 转换为秒
      
      // 只有在旋转状态时才更新角度
      if (isRotating) {
        setDynamicRotation(prev => {
          const newRotation = (prev + rotationSpeed * deltaTime) % 360;
          return newRotation;
        });
      }
      
      lastTime = currentTime;
      animationId = requestAnimationFrame(animate);
    };
    
    // 状态切换函数
    const toggleRotationState = () => {
      isRotating = !isRotating;
      const nextDuration = isRotating ? rotationDuration : pauseDuration;
      
      // console.log(`🎯 仪表盘${isRotating ? '开始旋转' : '暂停旋转'}，下次切换: ${nextDuration/1000}秒后`);
      
      stateChangeTimeout = window.setTimeout(toggleRotationState, nextDuration);
    };
    
    // 启动动画和状态切换
    animationId = requestAnimationFrame(animate);
    stateChangeTimeout = window.setTimeout(toggleRotationState, rotationDuration);
    
    return () => {
      if (animationId) {
        cancelAnimationFrame(animationId);
        // console.log(`🎯 仪表盘旋转动画已停止`);
      }
      if (stateChangeTimeout) {
        window.clearTimeout(stateChangeTimeout);
      }
    };
  }, []);

  const handleConfirmAndReset = () => {
    if (onResetSA) {
      onResetSA();
    }
    setShowTaskComplete(false);
  };

  return (
    <div className="w-full h-full p-4 bg-black text-green-400 font-mono flex flex-col items-center relative">
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
              <div key={label} className="relative">
                <Button
                  label={label}
                  onClick={idx === 1 ? handleResetSA : () => handleButtonClick(label)}
                />
              
              </div>
            ))}
          </div>
          
          {/* 雷达显示 - 仅包含雷达相关元素 */}
          <div className="sa-page bg-black relative" style={{ width, height }}>
            {/* 接管控制按钮 - 位置更靠近操作区域 临时隐藏*/}
            {/* {agentStore.isAIActive && (
              <button 
                className="absolute bg-orange-600 hover:bg-orange-700 text-white font-bold py-2 px-4 rounded shadow-lg transition-colors duration-200 z-50"
                style={{
                  top: '10px',
                  right: '10px'
                }}
                onClick={handleTakeControl}
                title="按F10或点击此按钮接管威胁排序控制"
              >
                接管控制 (F10)
              </button>
            )} */}
            
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
                
                {/* 在第二个圆的圆心位置添加一个小圆点 */}
                <Circle
                  x={config.centerX}
                  y={config.centerY - 50}
                  radius={3}
                  fill={config.lineColor}
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
                {renderDirectionMarkers()}
                
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
                
                {/* 刻度数值标记 */}
                {renderScaleValues()}
                
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
                {saThreats.map((threat: { type: string; label: string | undefined; id: React.Key | null | undefined; }, idx: string | number) => {
                  const IconComp = ICON_MAP[threat.type as keyof typeof ICON_MAP];
                  
                  // 添加调试信息
                  if (!IconComp) {
                    console.warn(`⚠️ 未找到威胁类型 "${threat.type}" 对应的图标组件`);
                    console.log('可用的图标类型:', Object.keys(ICON_MAP));
                    console.log('当前威胁数据:', threat);
                    return null;
                  }
                  
                  const isSelected = threat.id === selectedThreatId;
                  const isHighestPriority = threat.id === highestPriorityThreat?.id;

                  return (
                    <Group key={threat.id} onClick={() => handleThreatIconClick(threat, 'manual')}>
                       {/* 只有在做出选择后才渲染虚线框 */}
                      {hasSelectionBeenMade && (isSelected || (showTaskComplete && isHighestPriority)) && (
                        <Rect
                          x={iconPositions[idx].x - 5}
                          y={iconPositions[idx].y - 5}
                          width={ICON_SIZE + 10}
                          height={ICON_SIZE + 10}
                          stroke={showTaskComplete && isHighestPriority ? '#ff4136' : '#ffd700'} // 确认后最高威胁显示红色，否则黄色
                          strokeWidth={2}
                          dash={[6, 3]} // 虚线样式
                          cornerRadius={5}
                        />
                      )}
                      <IconComp
                        x={iconPositions[idx].x}
                        y={iconPositions[idx].y}
                        size={ICON_SIZE}
                        color={iconColors[Object.keys(ICON_MAP).indexOf(threat.type as keyof typeof ICON_MAP)]}
                        label={threat.label}
                      />
                      <Text
                        x={iconPositions[idx].x + ICON_SIZE + 5}
                        y={iconPositions[idx].y + ICON_SIZE / 2 - 8}
                        text={`${threat.label} [${threatIdToSortedIndexMap.get(threat.id)}]`}
                        fontSize={14}
                        fill="#00ff00"
                        fontFamily="monospace"
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
            {/* 音频控制按钮 - 状态直接来自 agentStore */}
            
            
            {rightButtons.map(label => (
              <Button key={label} label={label} onClick={() => handleButtonClick(label)} />
            ))}
          </div>
        </div>
      </div>
      
      {/* 威胁列表 */}
      <div className="w-full max-w-4xl bg-black border border-gray-700 rounded-md overflow-hidden" style={{marginTop: '20px'}}>
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
        
      {[
        ...threatList, 
        ...saThreats.filter((saThreat: any) => !threatList.some(t => t.id === saThreat.id)),
        ...missiles.filter((missile: any) => !threatList.some(t => t.id === missile.id))
          .map((missile: any) => ({
            id: missile.id,
            type: missile.type,
            label: missile.type === 'MissileUp' ? '上升导弹' : '下降导弹',
            source: missile.type === 'MissileUp' ? '上升导弹' : '下降导弹',
            distance: 0,
            heading: 0,
            priority: 'high' as const
          }))
      ].map((threat, index) => (
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
                style={{ backgroundColor: (threat.priority === 'high' || threat.type?.includes('Primary')) ? '#ff0000' : (threat.priority === 'medium' || threat.type?.includes('Secondary')) ? '#ffff00' : '#00ffff' }}
              ></span>
              <span className="text-white">{(threat.priority === 'high' || threat.type?.includes('Primary')) ? '高' : (threat.priority === 'medium' || threat.type?.includes('Secondary')) ? '中' : '低'}</span>
            </div>
          </div>
        ))}
      </div>
      
      {/* 任务结束弹窗 */}
      {showTaskComplete && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 border-2 border-green-400 rounded-lg p-6 max-w-md mx-4 text-center">
            <div className="text-green-400 text-2xl font-bold mb-2">
              ✅ 任务结束
            </div>
            <div className="text-white mb-4">
              最具威胁项处理完成：<br />
              <span className="text-yellow-400 font-mono">{completedThreat}</span>
            </div>
            <p className="text-white text-lg mb-6">是否进行下一个任务？</p>
            <div className="flex justify-center space-x-4">
              <button
                className="bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-6 rounded transition-colors duration-200"
                onClick={() => setShowTaskComplete(false)}
              >
                否
              </button>
              <button
                className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-6 rounded transition-colors duration-200"
                onClick={handleResetSA}
              >
                是
              </button>
            </div>
          </div>
        </div>
      )}
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