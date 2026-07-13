import React, { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { Stage, Layer, Circle, Line, Group, Text, Rect } from 'react-konva';
import MissileUpIcon from '../icons/MissileUpIcon';
import MissileDownIcon from '../icons/MissileDownIcon';
import useRadarData from '../hooks/useRadarData';
import { MessageType } from './CommunicationLog';
import { useAIAgent } from '../hooks/useAIAgent';
import agentStore from '../stores/AgentStore';
import { observer } from 'mobx-react-lite';
import radarStore from '../stores/RadarStore';
import audioManager from '../managers/AudioManager';
import { isLastRepetition, formatRepetitionText } from '../utils/repetitionUtils';
import type { ThreatListData } from './ThreatList';
import { useThreatTrustCalibration } from '../hooks/useThreatTrustCalibration';
import { ThreatTrustDecision } from '../types/trustCalibration';
// import SAButtons from './SAButtons';

interface SAPageProps {
  width?: number;
  height?: number;
  onAddMessage?: (type: MessageType, content: string) => void;
  onClearMessages?: () => void;
  userId?: string;
  onResetSA?: () => void;
  onResetTargets?: () => void;
  onThreatListUpdate?: (threatData: ThreatListData) => void; // 新增：威胁数据回调
  onShowDetailedInfoChange?: (showDetailed: boolean) => void; // 新增：详细信息显示状态回调
  onResultConfirmed?: () => void;
  onTrustDecisionUpdate?: (decision: ThreatTrustDecision) => void;
  onTrustActionsUpdate?: (actions: {
    markEvidenceViewed: () => void;
    markManualReviewDone: () => void;
  } | null) => void;
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
  label: string;
  score: number;
  distance_from_center: number;
  creation_timestamp?: number;
}

// 增强威胁位置接口
interface EnhancedThreatPosition {
  x: number;
  y: number;
}

// 增强威胁数据接口（与服务端保持一致）
interface EnhancedThreat {
  id: string;
  type: string;
  label: string;
  position: EnhancedThreatPosition;
  priority: 'high' | 'medium' | 'low';
  score: number;
  distance_from_center: number;
  is_missile: boolean;
  missile_type?: 'MissileUp' | 'MissileDown' | null;
  creation_timestamp: number;
}

// 增强威胁消息接口（使用原有sa_task_updated类型保持兼容性）
interface EnhancedThreatsMessage {
  type: 'sa_task_updated';
  threats: EnhancedThreat[];
  radar_config: {
    center_x: number;
    center_y: number;
    radius1: number;
    radius2: number;
    radius3: number;
    canvas_width: number;
    canvas_height: number;
    icon_size: number;
  };
  highest_priority_threat_id: string | null;
  generation_timestamp: number;
  task_type: string;
  repetition_info: any;
  is_ai_active: boolean;
  ai_level: string | null;
  ai_configs: any;
  audio_enabled: boolean;
  timestamp: number;
}

// 按钮组件 - 使用普通DOM元素而非Konva
interface ButtonProps {
  label: string;
  onClick?: () => void;
  disabled?: boolean;
}

  const Button: React.FC<ButtonProps> = ({ label, onClick, disabled }) => {
    const isResultButton = label === '查看结果';
    return (
      <button
        disabled={disabled}
        onClick={disabled ? undefined : onClick}
        style={{
          width: isResultButton ? '80px' : '48px',
          height: '40px',
          fontFamily: "'Share Tech Mono', monospace",
          fontSize: '13px',
          letterSpacing: '0.05em',
          cursor: disabled ? 'not-allowed' : 'pointer',
          outline: 'none',
          transition: 'background 0.15s, box-shadow 0.15s',
          borderRadius: '3px',
          ...(disabled ? {
            background: 'rgba(0,10,4,0.6)',
            color: '#3a7a44',
            border: '1px solid #0a2010',
          } : {
            background: 'rgba(0,20,8,0.7)',
            color: '#00aa44',
            border: '1px solid #0d4020',
            boxShadow: 'inset 0 0 6px rgba(0,180,70,0.05)',
          }),
        }}
        onMouseEnter={e => {
          if (!disabled) {
            (e.currentTarget as HTMLButtonElement).style.background = 'rgba(0,40,15,0.8)';
            (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 0 8px rgba(0,180,70,0.2), inset 0 0 6px rgba(0,180,70,0.08)';
          }
        }}
        onMouseLeave={e => {
          if (!disabled) {
            (e.currentTarget as HTMLButtonElement).style.background = 'rgba(0,20,8,0.7)';
            (e.currentTarget as HTMLButtonElement).style.boxShadow = 'inset 0 0 6px rgba(0,180,70,0.05)';
          }
        }}
      >
        {label}
      </button>
    );
  };

const ICON_SIZE = 48;
const PRIMARY_THREAT_COLOR = '#ff3333';
const SECONDARY_THREAT_COLOR = '#ffff00';
const SELECTED_FILL_COLOR = '#ffd700';
const RECOMMENDATION_COLOR = '#00ff66';
const CORRECT_ANSWER_COLOR = '#ff4136';

const getThreatStrokeColor = (type?: string, priority?: string): string => {
  if (priority === 'high' || type?.includes('Primary')) return PRIMARY_THREAT_COLOR;
  return SECONDARY_THREAT_COLOR;
};

interface StandardThreatIconProps {
  x: number;
  y: number;
  size?: number;
  stroke: string;
  fill?: string;
  label?: string;
}

const StandardThreatIcon: React.FC<StandardThreatIconProps> = ({ x, y, size = ICON_SIZE, stroke, fill, label }) => {
  const totalWidth = size * 0.86;
  const bodyWidth = size * 0.58;
  const tipWidth = totalWidth - bodyWidth;
  const bodyHeight = size * 0.38;
  const startX = x - totalWidth / 2;
  const startY = y - bodyHeight / 2;
  const tipStartX = startX + bodyWidth;
  const fillProps = fill ? { fill, opacity: 0.72 } : {};

  return (
    <Group>
      <Rect
        x={startX}
        y={startY}
        width={bodyWidth}
        height={bodyHeight}
        stroke={stroke}
        strokeWidth={3}
        fillEnabled={!!fill}
        {...fillProps}
      />
      <Line
        points={[
          tipStartX, startY,
          tipStartX + tipWidth, y,
          tipStartX, startY + bodyHeight,
        ]}
        closed
        stroke={stroke}
        strokeWidth={3}
        fillEnabled={!!fill}
        {...fillProps}
      />
      {label && (
        <Text
          text={label}
          x={startX}
          y={startY}
          width={bodyWidth}
          height={bodyHeight}
          align="center"
          verticalAlign="middle"
          fontSize={Math.max(10, bodyHeight * 0.58)}
          fill={fill ? '#071000' : stroke}
          fontFamily="monospace"
          fontStyle="bold"
        />
      )}
    </Group>
  );
};

interface FanThreatPosition {
  x: number;
  y: number;
  rank: number;
  angle: number;
  radius: number;
}

interface TobiiPromptPosition {
  left: number;
  top: number;
  right: number;
  bottom: number;
  gazeCoordinateSpace: 'physical_pixel' | 'display_area_normalized';
}

interface SaTobiiDebugBbox {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

const FAN_START_ANGLE = -132;
const FAN_END_ANGLE = -48;
const FAN_ANGLE_SPAN = FAN_END_ANGLE - FAN_START_ANGLE;
const FAN_EDGE_COLOR = '#ffffff';
const ATTACK_SOURCES = ['雷达', '友机', '装订'] as const;

const degToRad = (angle: number) => (angle * Math.PI) / 180;
const clamp01 = (value: number) => Math.max(0, Math.min(1, value));

const stableHash = (value: string): number => {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
  }
  return hash;
};

const formatClockTime = (timestamp?: number, fallbackKey = ''): string => {
  if (typeof timestamp === 'number' && Number.isFinite(timestamp) && timestamp > 0) {
    return new Date(timestamp).toLocaleTimeString('zh-CN', { hour12: false });
  }

  const hash = stableHash(fallbackKey || 'sa-threat');
  const hour = String(hash % 24).padStart(2, '0');
  const minute = String(Math.floor(hash / 24) % 60).padStart(2, '0');
  const second = String(Math.floor(hash / 1440) % 60).padStart(2, '0');
  return `${hour}:${minute}:${second}`;
};

const getStableAttackSource = (threat: any): string => {
  if (ATTACK_SOURCES.includes(threat?.attackSource)) return threat.attackSource;
  if (ATTACK_SOURCES.includes(threat?.attack_source)) return threat.attack_source;
  return ATTACK_SOURCES[stableHash(String(threat?.id ?? threat?.label ?? 'attack')) % ATTACK_SOURCES.length];
};

const SAPage: React.FC<SAPageProps> = observer(({ width = 900, height = 900, onAddMessage, onClearMessages, userId: originalUserId, onResetSA, onThreatListUpdate, onShowDetailedInfoChange, onResultConfirmed, onTrustDecisionUpdate, onTrustActionsUpdate }) => {
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

  const { connected, radarData, error, sendMessage, sendResetSA, repetitionInfos, setEnhancedThreats, enhancedThreats, serverRadarConfig, useEnhancedProtocol, mainPos, button1, button2, joystickEnabled, startSaTobiiRound, endSaTobiiRound } = useRadarData();
  const saCanvasRef = useRef<HTMLDivElement | null>(null);
  const endSaTobiiRoundRef = useRef(endSaTobiiRound);// 存储 endSaTobiiRound 函数的引用
  const getHighestThreatPromptPositionRef = useRef<(() => TobiiPromptPosition | null) | null>(null);
  const getSaTobiiPromptPositionRef = useRef<(() => TobiiPromptPosition | null) | null>(null);
  const aiSelectedThreatRef = useRef<any | null>(null);
  const attentionIntervalRef = useRef<number | null>(null);
  const attentionTimeoutRef = useRef<number | null>(null);
  const [highestThreatAttentionVisible, setHighestThreatAttentionVisible] = useState(false);
  const [saTobiiDebugBbox, setSaTobiiDebugBbox] = useState<SaTobiiDebugBbox | null>(null);
  const stopAutoStartSaTobiiRef = useRef<boolean>(false);
  const lastHighestThreatIdRef = useRef<string | null>(null);
  const isSaTobiiBboxDebugEnabled = useMemo(() => {
    if (typeof window === 'undefined') return false;
    const params = new URLSearchParams(window.location.search);
    return (
      params.get('debugSaTobiiBbox') === '1' ||
      window.localStorage.getItem('debugSaTobiiBbox') === '1'
    );
  }, []);

  // 计算当前难度和AI状态
  const currentDifficulty = useMemo(() => {
    const saRepetitionInfo = repetitionInfos['SA_THREAT_RESPONSE'];
    return saRepetitionInfo && typeof saRepetitionInfo !== 'string' ? (saRepetitionInfo as any).difficulty : undefined;
  }, [repetitionInfos]);

  const saRepetitionInfo = repetitionInfos['SA_THREAT_RESPONSE'];
  const isSAAllCompleted = saRepetitionInfo === 'ALL_COMPLETED';
  const hasReachedSAOverallTotal = useMemo(() => {
    if (!saRepetitionInfo || typeof saRepetitionInfo === 'string') return false;
    const current = Number((saRepetitionInfo as any).current ?? 0);
    const total = Number((saRepetitionInfo as any).total ?? 0);
    const scenarioIndex = Number((saRepetitionInfo as any).scenario_index ?? 1);
    const scenarioTotal = Number((saRepetitionInfo as any).scenario_total ?? 1);
    return total > 0 && current >= total && scenarioIndex >= scenarioTotal;
  }, [saRepetitionInfo]);
  const completedSATaskKeysRef = useRef<Set<string>>(new Set());
  const getCurrentSATaskId = useCallback(() => {
    if (saRepetitionInfo && typeof saRepetitionInfo !== 'string') {
      const taskId = (saRepetitionInfo as any).task_id;
      if (taskId !== undefined && taskId !== null) {
        return taskId;
      }
    }
    return radarStore.taskId;
  }, [saRepetitionInfo, radarStore.taskId]);

  const getCurrentSATaskKey = useCallback(() => {
    const taskId = getCurrentSATaskId();
    if (taskId !== null && taskId !== undefined) {
      return String(taskId);
    }
    if (!saRepetitionInfo || typeof saRepetitionInfo === 'string') {
      return null;
    }
    const ri = saRepetitionInfo as any;
    return [
      'pending-sa',
      userId ?? '',
      ri.current ?? '',
      ri.total ?? '',
      ri.scenario_index ?? '',
      ri.scenario_total ?? '',
      ri.is_ai_active ? 'ai' : 'manual',
      ri.is_practice ? 'practice' : 'formal',
    ].join(':');
  }, [saRepetitionInfo, userId, getCurrentSATaskId]);

  const isAIActive = useMemo(() => {
    const saRepetitionInfo = repetitionInfos['SA_THREAT_RESPONSE'];
    return saRepetitionInfo && typeof saRepetitionInfo !== 'string' ? !!(saRepetitionInfo as any).is_ai_active : false;
  }, [repetitionInfos]);



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
  const fanGeometry = useMemo(() => {
    const apexX = config.centerX;
    const apexY = config.centerY - 50;
    const outerRadius = Math.min(width, height) * 0.48;
    const innerRadius = outerRadius * 0.62;
    const pointAt = (radius: number, angle: number) => ({
      x: apexX + radius * Math.cos(degToRad(angle)),
      y: apexY + radius * Math.sin(degToRad(angle)),
    });

    return {
      apexX,
      apexY,
      outerRadius,
      innerRadius,
      leftOuter: pointAt(outerRadius, FAN_START_ANGLE),
      rightOuter: pointAt(outerRadius, FAN_END_ANGLE),
      labelPoint: pointAt(outerRadius + 26, FAN_START_ANGLE + FAN_ANGLE_SPAN / 2),
    };
  }, [config.centerX, height, width]);
  const radius2 = bottomLineY - config.centerY; // 使第二个圆与底部线相切
  const radius3 = radius2 * 1.7; // 第三个圆的半径，原来是1.5倍，现在增大到1.6倍
  
  // 计算弧线角度
  const arcStartAngle = 210; // 开始角度 (210度)
  const arcEndAngle = 330;   // 结束角度 (330度)
  



  // 随机旋转角度（0~360度）
  const [rotation] = React.useState(() => Math.random() * 360);

  // 添加动态旋转角度状态
  const [dynamicRotation, setDynamicRotation] = React.useState(0);
  const fanScanGeometry = useMemo(() => {
    const startAngle = FAN_START_ANGLE + dynamicRotation;
    const endAngle = FAN_END_ANGLE + dynamicRotation;
    const pointAt = (radius: number, angle: number) => ({
      x: fanGeometry.apexX + radius * Math.cos(degToRad(angle)),
      y: fanGeometry.apexY + radius * Math.sin(degToRad(angle)),
    });

    return {
      ...fanGeometry,
      startAngle,
      endAngle,
      leftOuter: pointAt(fanGeometry.outerRadius, startAngle),
      rightOuter: pointAt(fanGeometry.outerRadius, endAngle),
      centerOuter: pointAt(fanGeometry.outerRadius, startAngle + FAN_ANGLE_SPAN / 2),
      labelPoint: pointAt(fanGeometry.outerRadius + 26, startAngle + FAN_ANGLE_SPAN / 2),
    };
  }, [dynamicRotation, fanGeometry]);
  const fanSweepGeometry = useMemo(() => {
    const centerAngle = fanScanGeometry.startAngle + FAN_ANGLE_SPAN / 2;
    const sweepWidth = 7;
    const pointAt = (radius: number, angle: number) => ({
      x: fanScanGeometry.apexX + radius * Math.cos(degToRad(angle)),
      y: fanScanGeometry.apexY + radius * Math.sin(degToRad(angle)),
    });
    const makeWedge = (angle: number, width: number) => ({
      left: pointAt(fanScanGeometry.outerRadius, angle - width / 2),
      center: pointAt(fanScanGeometry.outerRadius, angle),
      right: pointAt(fanScanGeometry.outerRadius, angle + width / 2),
    });

    return {
      beam: makeWedge(centerAngle, sweepWidth),
      trail: [1, 2, 3, 4, 5].map(index => ({
        ...makeWedge(centerAngle - index * 6, sweepWidth + index * 2),
        opacity: 0.18 / index,
      })),
      pulse: 0.32 + 0.12 * Math.sin(degToRad(dynamicRotation * 8)),
    };
  }, [dynamicRotation, fanScanGeometry]);

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
  const leftButtons = Array(5).fill(0).map((_, i) => i === 1 ? 'Next' : `T${i + 1}`);
  const rightButtons = Array(5).fill(0).map((_, i) => `R${i + 1}`);
  
  // 按钮点击处理函数
  const handleButtonClick = (label: string) => {
    console.log(`按钮 ${label} 被点击`);
    
    
    // 当点击第3个按钮（查看结果）时，显示选择结果
    if (label === '查看结果') {
      if (threatTrustDecision.blockedOneClick) {
        onAddMessage?.('warning', `信任调控：${threatTrustDecision.primaryMessage}，请先查看证据或人工确认`);
        return;
      }
      if (isSAAllCompleted) {
        console.log('[SAPage] SA result ignored because task is already ALL_COMPLETED.');
        onResultConfirmed?.();
        return;
      }

      const taskKey = getCurrentSATaskKey();
      const hasAnswer = !!userSelection;
      if (hasAnswer && taskKey && completedSATaskKeysRef.current.has(taskKey)) {
        console.log('[SAPage] SA result ignored because current task was already confirmed:', taskKey);
        if (hasReachedSAOverallTotal || isSAAllCompleted) {
          onResultConfirmed?.();
        }
        return;
      }

      if (hasAnswer) {
        if (taskKey) {
          completedSATaskKeysRef.current.add(taskKey);
        }
        const currentTaskId = getCurrentSATaskId();
        sendMessage?.({
          type: 'task_result_confirmed',
          task_type: 'SA_THREAT_RESPONSE',
          task_id: currentTaskId,
          timestamp: Date.now(),
          user_id: userId,
          event_owner: 'manual',
          extra: buildThreatTrustLogExtra(),
        });
        recordResultConfirmed(userSelection?.threat?.id);
      } else {
        console.log('[SAPage] SA result viewed without a selection; current task is not marked completed.');
      }

      stopAutoStartSaTobiiRef.current = true;
      const promptPosition = getSaTobiiPromptPositionRef.current?.();
      console.log('gazerelation:查看结果按钮点击了,发送结束Tobii请求', promptPosition);
      beginSATobiiServe.current = false;
      endSaTobiiRound(promptPosition || undefined);
      
      // 启用威胁列表详细信息显示（分数和距离）
      if (onShowDetailedInfoChange) {
        onShowDetailedInfoChange(true);
      }
      
      // // 获取正确的威胁标签
      // const getThreatLabel = (threat: any): string => {
      //   if (threat.type === 'MissileUp') return '上升导弹';
      //   if (threat.type === 'MissileDown') return '下降导弹';
      //   return threat.label || '未知威胁';
      // };

      // 添加重复次数信息到日志
      const saRepetitionInfo = repetitionInfos['SA_THREAT_RESPONSE'];
      console.log('DEBUG saRepetitionInfo', saRepetitionInfo)
      if (saRepetitionInfo && typeof saRepetitionInfo !== 'string') {
        setShowTaskComplete(true);
      }

      // // 生成威胁排序日志（简化版本，详细信息在威胁列表中查看）
      if (onAddMessage) {
        // onAddMessage('sa_threat', '=== 威胁排序完成，详细信息请查看威胁列表 ===');
        
        // threatsWithScore.forEach((threatInfo, index) => {
        //   const threatLabel = getThreatLabel(threatInfo.threat);
        //   const scoreText = `排名${index + 1}: ${threatLabel} - 得分: ${threatInfo.score.toFixed(2)}${threatInfo.isMissile ? ' (导弹)' : ''}`;
        //   onAddMessage('sa_threat', scoreText);
        // });
        onAddMessage('sa_threat',  userSelection?.threat?.label);
        
        onAddMessage('sa_threat',  userSelection?.isCorrect === false ? '错误' : userSelection?.isCorrect === true ? '正确' : '未选择');
      }

      if (userSelection) {
        const { isCorrect } = userSelection;
        setResult(isCorrect);
      } else {
        setResult(undefined);
      }
      
   
      
    
      // 将正确答案也添加到威胁列表中，确保显示红色边框
      const highestPriorityThreat = getCurrentHighestPriorityThreat();
      if (highestPriorityThreat) {
        const getOriginalPriority = (threat: any): 'high' | 'medium' | 'low' => {
          if (threat.type?.toLowerCase().includes('missile')) return 'high';
          if (threat.type?.includes('Primary') || threat.id?.includes('Primary')) return 'high';
          return 'medium';
        };
        if (useEnhancedProtocol) {
          setEnhancedThreats(prev => {
            const newList = [...prev.filter(t => t.id !== highestPriorityThreat.id)];
            const one = prev.find(t => t.id === highestPriorityThreat.id);
            newList.unshift({...one});
            return newList;
          })
        } else {
          setThreatList(prev => {
            const newList = [...prev.filter(t => t.id !== highestPriorityThreat.id)];
            // 将正确答案添加到列表第一位
            newList.unshift({
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
      // Keep the selected target solid while the result dialog is visible.
    }
  };

  // 计算按钮容器尺寸
  const sideButtonWidth = 48;
  const sideButtonGap = 16;
  const totalDisplayWidth = width + (sideButtonWidth + sideButtonGap) * 2;
  const topContainerWidth = width; // 使顶部容器宽度与雷达宽度相同
  const sideContainerHeight = height * 0.8; // 侧边容器高度与雷达高度的80%相同

  // 威胁数据状态
  const [saThreats, setSaThreats] = useState(radarData?.saThreats ?? []);
  const [missiles, setMissiles] = useState<MissileData[]>([]);
  const [threatList, setThreatList] = useState<ThreatData[]>([]);
  
  // 增强威胁数据状态现在从useRadarData获取
  


  // 添加refs控制日志写入
  const hasInitLogRef = useRef(false);
  const lastEmergencyRef = useRef<string | null>(null);
  const lastThreatsLengthRef = useRef<number>(0);
  // 记录最近一次SAEmergency的接收时间戳
  const lastEmergencyReceiveTimestampRef = useRef<number | null>(null);

  // 添加任务结束弹窗状态
  const [showTaskComplete, setShowTaskComplete] = useState(false);
  const [isCorrect, setResult] = useState<boolean |undefined>();
  
  // 添加用户选择状态（但不立即显示结果）
  const [userSelection, setUserSelection] = useState<{threat: any, isCorrect: boolean} | null>(null);
  
    // 添加一个状态，用于判断是否已经进行过选择
  const hasSelectionBeenMade = useMemo(() => userSelection?.threat, [userSelection]);

  // 添加状态控制是否显示威胁列表的详细信息（得分和距离）


  // // 添加接管按钮处理函数
  // const handleTakeControl = useCallback(() => {
  //   console.log('[SA页面] 用户手动接管控制');
  //   // 禁用AI控制
  //   // agentStore.setAIActive(false);
    
  //   // 发送接管消息到服务器
  //   if (sendMessage) {
  //     sendMessage({
  //       type: 'user_take_control',
  //       timestamp: Date.now(),
  //       user_id: userId || 'current_user',
  //       page: 'SA' // 标记是SA页面的接管
  //     });
  //   }
    
  //   console.log('✅ [SA页面] 用户已接管威胁排序控制');
  // }, [sendMessage, userId]);

  // // 添加F10快捷键监听
  // useEffect(() => {
  //   const handleKeyPress = (event: KeyboardEvent) => {
  //     if (event.key === 'F10') {
  //       event.preventDefault();
  //       handleTakeControl();
  //     }
  //   };

  //   window.addEventListener('keydown', handleKeyPress);
  //   return () => {
  //     window.removeEventListener('keydown', handleKeyPress);
  //   };
  // }, [handleTakeControl]);

  // 摇杆光标位置（mainPos 归一化 -1~+1 映射到画布坐标）
  const joystickCursorPos = React.useMemo(() => {
    if (!joystickEnabled || !mainPos) return null;
    const x = ((mainPos.x + 1) / 2) * width;
    const y = ((mainPos.y + 1) / 2) * height;
    return { x, y };
  }, [mainPos, joystickEnabled, width, height]);

  // 摇杆按钮上升沿检测 ref
  const prevButton1Ref = React.useRef(false);
  const prevButton2Ref = React.useRef(false);

  // 处理重置SA
  const handleResetSA = useCallback(() => {
    console.log('====== SA系统重置 ======');
    
    // 核心修复：重置 MobX store 中的临机事件状态
    radarStore.resetSAEmergency();

    // 清空系统日志
    if (typeof onClearMessages === 'function') {
      onClearMessages();
    }

    // 清除所有本地状态
    setMissiles([]);
    setThreatList([]);
    setSaThreats([]);
    setShowTaskComplete(false); // 关闭任务完成弹窗
    setResult(undefined); // 清空已完成威胁
    setUserSelection(null); // 清空用户选择
    aiSelectedThreatRef.current = null;
    setDynamicRotation(0); // 重置仪表盘旋转
    // 通知父组件重置详细信息显示状态
    if (onShowDetailedInfoChange) {
      onShowDetailedInfoChange(false);
    }
    
    // 重置控制标志
    if (onResetSA) {
      onResetSA();
    }
    
    // 记录重置日志（在清空日志后重新记录）
    if (typeof onAddMessage === 'function') {
      onAddMessage('sa_init', 'SA系统已重置，所有威胁和状态已清空');
    }
    
    console.log('✅ SA系统重置完成');
  }, [sendResetSA, onAddMessage, onClearMessages, onResetSA, onShowDetailedInfoChange]);

  // 增强威胁协议数据现在由useRadarData管理，这里不需要再监听

  // 监听enhancedThreats变化（调试用）
  useEffect(() => {
    console.log('【SAPage】enhancedThreats 变化:', enhancedThreats.length, enhancedThreats);
    console.log('【SAPage】useEnhancedProtocol 变化:', useEnhancedProtocol);
  }, [enhancedThreats, useEnhancedProtocol]);

  // 主动同步saThreats（传统协议）
  useEffect(() => {
    console.log('【SAPage】radarData?.saThreats changed:', radarData?.saThreats);
    if (radarData?.saThreats && !useEnhancedProtocol) {
      setSaThreats(radarData.saThreats);
    }
  }, [radarData?.saThreats, useEnhancedProtocol]);

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
      
      // 检测到服务器重置信号，重置内部ref变量
      if (hasInitLogRef.current) {
        console.log('【SAPage】检测到服务器重置，重置内部ref变量');
        hasInitLogRef.current = false;
        lastThreatsLengthRef.current = 0;
        lastEmergencyRef.current = null;
        lastEmergencyReceiveTimestampRef.current = null;
        
        // 重置其他状态
        setMissiles([]);
        setShowTaskComplete(false); // 关闭任务完成弹窗
        setResult(undefined); // 清空已完成威胁
        setUserSelection(null); // 清空用户选择
        aiSelectedThreatRef.current = null;
        setDynamicRotation(0); // 重置仪表盘旋转
        // 通知父组件重置详细信息显示状态
        if (onShowDetailedInfoChange) {
          onShowDetailedInfoChange(false);
        }
      }
    }
  }, [saThreats, onAddMessage, onShowDetailedInfoChange]);

  // 监听紧急事件变化 - 支持增强协议
  useEffect(() => {
    if (radarData?.emergency) {
      const eventId = JSON.stringify(radarData.emergency);
      if (lastEmergencyRef.current !== eventId) {
        const data = radarData.emergency;
        // 记录前端接收SAEmergency的本地时间戳
        const receiveTimestamp = Date.now();
        lastEmergencyReceiveTimestampRef.current = receiveTimestamp;
        
        if (data.event === 'missile') {
          audioManager.play(data.missileType === 'MissileUp' ? 'missileUp' : 'missileDown');
          console.log(`🚀 增强导弹data: (${data.type}, ${data.missile_threat})`);
          // 检查是否是增强协议的导弹事件
          if (data.type === 'SAEmergency' && data.missile_threat) {
            // 使用增强协议：直接使用服务端提供的导弹数据
            console.log('【SAPage】收到增强导弹事件:', data.missile_threat);
            
            const enhancedMissile: MissileData = {
              id: data.missile_threat.id,
              type: data.missile_threat.missile_type as 'MissileUp' | 'MissileDown',
              x: data.missile_threat.position.x,
              y: data.missile_threat.position.y,
              score: data.missile_threat.score,
              label: data.missile_threat.label,
              distance_from_center: data.missile_threat.distance_from_center,
              creation_timestamp: data.missile_threat.creation_timestamp,
            };
            
            setMissiles(prev => [...prev, enhancedMissile]);
            console.log(`🚀 增强导弹位置: (${enhancedMissile.x}, ${enhancedMissile.y})`);
          } else {
            // 传统协议：前端生成导弹位置（向后兼容）
            console.log('【SAPage】使用传统导弹生成逻辑');
            
            // 简化的导弹位置生成
            const angle = Math.random() * Math.PI * 2;
            const r = radius2 + Math.random() * (radius3 - radius2) * 0.8;
            const effectiveCenterY = config.centerY - 50;
            
            const rawX = config.centerX + r * Math.cos(angle);
            const rawY = effectiveCenterY + r * Math.sin(angle);
            
            const missileSize = 30;
            const x = Math.max(missileSize, Math.min(width - missileSize, rawX));
            const y = Math.max(missileSize, Math.min(height - missileSize, rawY));
            
            const missileType: 'MissileUp' | 'MissileDown' = data.missileType === 'MissileUp' ? 'MissileUp' : 'MissileDown';
            const newMissile: MissileData = {
              id: Date.now().toString(),
              type: missileType,
              x,
              y,
              distance_from_center: 0,
              score: 1.0,
              label: missileType,
            };
            setMissiles(prev => [...prev, newMissile]);
            console.log(`🚀 传统导弹位置: (${x}, ${y})`);
          }
          
          if (onAddMessage) {
            console.log('Writing missile warning log...');
            onAddMessage('sa_missile', `警告！导弹来袭！类型：${data.missileType === 'MissileUp' ? '上升导弹' : '下降导弹'}`);
          }
        } 
        else if (data.event === 'upgrade') {
          audioManager.play('threatUpgrade');
          
          // 检查是否是增强协议的升级事件
          if (data.type === 'SAEmergency' && data.updated_threats) {
            // 使用增强协议：增强威胁数据由useRadarData管理
            console.log('【SAPage】收到增强升级事件:', data.updated_threats);
            console.log('gazerelation:4',data.updated_threats)
            // 注意：增强威胁数据的更新现在由useRadarData处理
          } else if (data.saThreats) {
            // 传统协议：更新saThreats
            setSaThreats(data.saThreats);
          }
          
          if (onAddMessage) {
            console.log('Writing threat upgrade log...');
            console.log('gazerelation:5',data.updated_threats)
            onAddMessage('sa_emergency', '收到临机事件：威胁升级，已有威胁提升为一级');
          }
        }
        beginSATobiiServe.current = true;
        console.log(`[gazerelation] isAIActive: ${agentStore.isAIActive}`);
        lastEmergencyRef.current = eventId;
      }
    }
  }, [radarData?.emergency, radius2, radius3, config.centerX, config.centerY, onAddMessage, sendMessage, width, height]);



  // 简化的位置获取逻辑 - 仅用于传统协议威胁
  const threatPositions = React.useMemo(() => {
    // 只为传统协议的威胁计算位置
    console.log('【SAPage】计算传统协议威胁位置，威胁数量:', saThreats.length);
    
    return saThreats.map((threat: any, index: number) => {
      // 简化的位置分布：均匀分布在圆圈中
      const angle = (index / saThreats.length) * 2 * Math.PI;
      const r = radius2 + (index % 2) * 50; // 交替分布在内外圈
      const x = config.centerX + r * Math.cos(angle);
      const y = (config.centerY - 50) + r * Math.sin(angle);
      
      return {
        x: Math.max(ICON_SIZE, Math.min(width - ICON_SIZE, x)),
        y: Math.max(ICON_SIZE, Math.min(height - ICON_SIZE, y))
      };
    });
  }, [saThreats, config.centerX, config.centerY, radius2, width, height]);

  // 英文类型转中文
  const TYPE_MAP: Record<string, string> = {
    PrimaryAir: '一级空中威胁',
    SecondaryAir: '二级空中威胁',
    PrimaryAntiAircraftArtillery: '一级防空炮',
    SecondaryAntiAircraftArtillery: '二级防空炮',
    PrimaryNaval: '一级水面威胁',
    SecondaryNaval: '二级水面威胁',
    MissileUp: '上升导弹',
    MissileDown: '下降导弹',
    '上升导弹': '上升导弹',
    '下降导弹': '下降导弹',
  };

  // 为包含分数的威胁定义接口
  interface ThreatWithScore {
    threat: any;
    score: number;
    isMissile: boolean;
    originalIndex: number; // 新增：用于打破平局的原始索引
  }

    // 简化的威胁分数和排序逻辑 - 优先使用服务端数据
  const threatsWithScore = useMemo(() => {
    if (useEnhancedProtocol) {
      // 使用增强协议：直接使用服务端计算的分数和排序
      console.log('【SAPage】使用服务端优先级数据，威胁数量:', enhancedThreats.length);
      
      const allEnhancedThreats: ThreatWithScore[] = [];
      if (enhancedThreats.length > 0) {
        // 处理所有增强威胁（包括导弹和常规威胁）
        enhancedThreats.forEach((enhancedThreat, index) => {
          allEnhancedThreats.push({
            threat: {
              id: enhancedThreat.id,
              type: enhancedThreat.type,
              label: enhancedThreat.label,
              // 如果是导弹，转换为MissileData格式
              ...(enhancedThreat.is_missile ? {
                x: enhancedThreat.position.x,
                y: enhancedThreat.position.y
              } : {})
            },
            score: enhancedThreat.score,
            isMissile: enhancedThreat.is_missile,
            originalIndex: index
          });
        });
        
        console.log('【SAPage】增强威胁评分详情:', allEnhancedThreats.map(t => ({
          id: t.threat.id,
          type: t.threat.type,
          score: t.score?.toFixed(2),
          isMissile: t.isMissile
        })));
      }
      if (missiles.length > 0) {
        missiles.forEach((missile, index) => {
          allEnhancedThreats.push({
            threat: {
              id: missile.id,
              type: missile.type,
              label: missile.label,
            },
            score: missile.score,
            isMissile: true,
            originalIndex: index,
          })
        }
        );
      }
      return allEnhancedThreats.sort((a, b) => {
        // 威胁已经在服务端排序，但我们保持排序逻辑以防万一
        const scoreDiff = b.score - a.score;
        if (Math.abs(scoreDiff) > 1e-9) {
          return scoreDiff;
        }
        if (a.isMissile !== b.isMissile) {
          return a.isMissile ? -1 : 1;
        }
        return a.originalIndex - b.originalIndex;
      });
    } else {
      // 传统协议：使用简化的前端计算（向后兼容）
      console.log('【SAPage】使用传统协议计算优先级');
      
      const getTypeWeight = (type: string): number => {
        if (type.toLowerCase().includes('missile')) return 245;
        if (type.startsWith('Primary')) return 240;
        if (type.startsWith('Secondary')) return 200;
        return 80;
      };

      const allThreats: ThreatWithScore[] = [];
      
      // 添加导弹威胁
      missiles.forEach((missile, index) => {
        allThreats.push({
          threat: missile,
          score: 1.0, // 导弹总是最高分数
          isMissile: true,
          originalIndex: index
        });
      });

      // 添加常规威胁
      saThreats.forEach((threat: any, index: number) => {
        const pos = threatPositions[index];
        if (pos) {
          // 简化分数计算
          const weight = getTypeWeight(threat.type);
          const score = weight / 1000; // 简化计算
          
          allThreats.push({
            threat,
            score: Math.min(score, 0.9), 
            isMissile: false,
            originalIndex: index
          });
        }
      });

      return allThreats.sort((a, b) => {
        const scoreDiff = b.score - a.score;
        if (Math.abs(scoreDiff) > 1e-9) {
          return scoreDiff;
        }
        if (a.isMissile !== b.isMissile) {
          return a.isMissile ? -1 : 1;
        }
        return a.originalIndex - b.originalIndex;
      });
    }
  }, [useEnhancedProtocol, enhancedThreats, missiles, saThreats, threatPositions]);

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
      console.log("gazerelation:2",bestThreatInfo.threat)
      // console.log("gazerelation:",threatsWithScore)
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
  const selectedThreatId = useMemo(() => userSelection?.threat?.id, [userSelection]);
  const trustThreatInputs = useMemo(() => {
    return threatsWithScore.map(item => ({
      id: item.threat.id,
      type: item.threat.type,
      label: item.threat.label,
      score: item.score,
      is_missile: item.isMissile,
      priority: item.isMissile || item.threat.type?.includes('Primary') ? 'high' : 'medium',
      source: item.threat.label,
    }));
  }, [threatsWithScore]);
  const {
    threatTrustDecision,
    recordThreatSelection,
    recordResultConfirmed,
    markEvidenceViewed: markThreatEvidenceViewed,
    markManualReviewDone: markThreatManualReviewDone,
    buildLogExtra: buildThreatTrustLogExtra,
  } = useThreatTrustCalibration({
    config: agentStore.trustCalibrationConfig,
    threats: trustThreatInputs,
    generationTimestamp: radarData?.timestamp,
    taskKey: `${userId || ''}:${lastEmergencyReceiveTimestampRef.current || ''}`,
    participantKey: userId || null,
    groundTruth: { correctId: highestPriorityThreat?.id ?? null },
  });
  useEffect(() => {
    onTrustDecisionUpdate?.(threatTrustDecision);
  }, [onTrustDecisionUpdate, threatTrustDecision]);

  useEffect(() => {
    onTrustActionsUpdate?.({
      markEvidenceViewed: markThreatEvidenceViewed,
      markManualReviewDone: markThreatManualReviewDone,
    });
    return () => onTrustActionsUpdate?.(null);
  }, [markThreatEvidenceViewed, markThreatManualReviewDone, onTrustActionsUpdate]);

  const eyeFeedbackThreatId = agentStore.isAIActive ? aiSelectedThreatRef.current?.id : null;
  const fanThreatPositions = useMemo(() => {
    const positions = new Map<string, FanThreatPosition>();
    const clampPosition = (id: string, rawX: number, rawY: number) => {
      const x = Math.max(ICON_SIZE, Math.min(width - ICON_SIZE, rawX));
      const y = Math.max(ICON_SIZE, Math.min(height - ICON_SIZE, rawY));
      const dx = x - fanScanGeometry.apexX;
      const dy = y - fanScanGeometry.apexY;
      const angle = Math.atan2(dy, dx) * 180 / Math.PI;
      const radius = Math.sqrt(dx * dx + dy * dy);

      positions.set(id, {
        x,
        y,
        rank: threatIdToSortedIndexMap.get(id) ?? 0,
        angle,
        radius,
      });
    };

    if (useEnhancedProtocol && enhancedThreats.length > 0) {
      enhancedThreats.forEach(threat => {
        if (threat.position) {
          clampPosition(threat.id, threat.position.x, threat.position.y);
        }
      });
    } else {
      saThreats.forEach((threat: any, index: number) => {
        const position = threatPositions[index];
        if (position) {
          clampPosition(threat.id, position.x, position.y);
        }
      });
    }

    missiles.forEach(missile => {
      clampPosition(missile.id, missile.x, missile.y);
    });

    return positions;
  }, [enhancedThreats, fanScanGeometry.apexX, fanScanGeometry.apexY, height, missiles, saThreats, threatIdToSortedIndexMap, threatPositions, useEnhancedProtocol, width]);
  const isPointInFanScan = useCallback((position: { x: number; y: number }) => {
    const dx = position.x - fanScanGeometry.apexX;
    const dy = position.y - fanScanGeometry.apexY;
    const radius = Math.sqrt(dx * dx + dy * dy);
    if (radius > fanScanGeometry.outerRadius) return false;

    const angle = (Math.atan2(dy, dx) * 180 / Math.PI + 360) % 360;
    const start = (fanScanGeometry.startAngle + 360) % 360;
    const delta = (angle - start + 360) % 360;
    return delta <= FAN_ANGLE_SPAN;
  }, [fanScanGeometry.apexX, fanScanGeometry.apexY, fanScanGeometry.outerRadius, fanScanGeometry.startAngle]);
  //gazerelation: 判断是否在增强逻辑后发送
  const beginSATobiiServe = useRef(false);

  const triggerHighestThreatAttention = useCallback((durationMs: number = 3000) => {
    setHighestThreatAttentionVisible(true);
    if (attentionIntervalRef.current) {
      window.clearInterval(attentionIntervalRef.current);
    }
    if (attentionTimeoutRef.current) {
      window.clearTimeout(attentionTimeoutRef.current);
    }

    attentionIntervalRef.current = window.setInterval(() => {
      setHighestThreatAttentionVisible(prev => !prev);
    }, 260);

    attentionTimeoutRef.current = window.setTimeout(() => {
      if (attentionIntervalRef.current) {
        window.clearInterval(attentionIntervalRef.current);
        attentionIntervalRef.current = null;
      }
      setHighestThreatAttentionVisible(false);
      attentionTimeoutRef.current = null;
    }, durationMs);
  }, []);

  const getThreatPromptPosition = useCallback((threat: any): TobiiPromptPosition | null => {
    if (!threat) return null;
    const containerRect = saCanvasRef.current?.getBoundingClientRect();
    if (!containerRect) return null;
    let centerX: number | null = null;
    let centerY: number | null = null;
    let boxSize = ICON_SIZE;
    const isMissileThreat =
      Boolean(threat.isMissile) ||
      threat.type === 'MissileUp' ||
      threat.type === 'MissileDown' ||
      String(threat.type || '').toLowerCase().includes('missile');
    const fanPosition = fanThreatPositions.get(threat.id);
    if (fanPosition) {
      centerX = fanPosition.x;
      centerY = fanPosition.y;
      boxSize = isMissileThreat ? 34 : ICON_SIZE;
    }

    if (centerX === null && centerY === null && isMissileThreat) {
      const missile = missiles.find(m => m.id === threat.id);
      if (missile) {
        centerX = missile.x;
        centerY = missile.y;
        boxSize = 34;
      }
    } else if (centerX === null && centerY === null && useEnhancedProtocol) {
      const enhancedThreat = enhancedThreats.find(
        t => !t.is_missile && t.id === threat.id
      );
      if (enhancedThreat?.position) {
        centerX = enhancedThreat.position.x;
        centerY = enhancedThreat.position.y;
      }
    } else if (centerX === null && centerY === null) {
      const threatIndex = saThreats.findIndex((t: any) => t.id === threat.id);
      if (threatIndex >= 0) {
        const pos = threatPositions[threatIndex];
        if (pos) {
          centerX = pos.x;
          centerY = pos.y;
        }
      }
    }

    if (centerX === null || centerY === null) return null;
    const viewportWidth = typeof window !== 'undefined' ? Math.max(1, window.innerWidth || 1) : 1;
    const viewportHeight = typeof window !== 'undefined' ? Math.max(1, window.innerHeight || 1) : 1;
    const scaleX = containerRect.width / Math.max(1, width);
    const scaleY = containerRect.height / Math.max(1, height);
    const viewportCenterX = containerRect.left + centerX * scaleX;
    const viewportCenterY = containerRect.top + centerY * scaleY;
    const halfWidth = (boxSize * scaleX) / 2;
    const halfHeight = (boxSize * scaleY) / 2;
    const normalizedBbox = {
      left: clamp01((viewportCenterX - halfWidth) / viewportWidth),
      top: clamp01((viewportCenterY - halfHeight) / viewportHeight),
      right: clamp01((viewportCenterX + halfWidth) / viewportWidth),
      bottom: clamp01((viewportCenterY + halfHeight) / viewportHeight),
    };

    if (isSaTobiiBboxDebugEnabled) {
      setSaTobiiDebugBbox(normalizedBbox);
    }

    console.log('gazerelation:sa:normalized-bbox', {
      containerRect: {
        left: containerRect.left,
        top: containerRect.top,
        width: containerRect.width,
        height: containerRect.height,
      },
      centerX,
      centerY,
      boxSize,
      scaleX,
      scaleY,
      viewportWidth,
      viewportHeight,
      ...normalizedBbox,
    });

    return {
      ...normalizedBbox,
      gazeCoordinateSpace: 'display_area_normalized',
    };
  }, [
    fanThreatPositions,
    missiles,
    useEnhancedProtocol,
    enhancedThreats,
    saThreats,
    threatPositions,
    width,
    height,
    isSaTobiiBboxDebugEnabled,
  ]);

  const getHighestThreatPromptPosition = useCallback((): TobiiPromptPosition | null => {
    return getThreatPromptPosition(highestPriorityThreat);
  }, [getThreatPromptPosition, highestPriorityThreat]);

  const getSaTobiiPromptPosition = useCallback((): TobiiPromptPosition | null => {
    if (agentStore.isAIActive && aiSelectedThreatRef.current) {
      return getThreatPromptPosition(aiSelectedThreatRef.current);
    }
    return getHighestThreatPromptPosition();
  }, [getHighestThreatPromptPosition, getThreatPromptPosition]);

  useEffect(() => {
    const handleSaAttentionEvent = (event: Event) => {
      if (!agentStore.isAIActive || !aiSelectedThreatRef.current) return;
      const customEvent = event as CustomEvent<{ durationMs?: number }>;
      const durationMs = Number(customEvent?.detail?.durationMs) || 3000;
      triggerHighestThreatAttention(durationMs);
    };

    window.addEventListener('sa-highest-threat-attention', handleSaAttentionEvent as EventListener);
    return () => {
      window.removeEventListener('sa-highest-threat-attention', handleSaAttentionEvent as EventListener);
    };
  }, [triggerHighestThreatAttention]);

  useEffect(() => {
    const currentHighestThreatId = highestPriorityThreat?.id || null;
    if (currentHighestThreatId !== lastHighestThreatIdRef.current) {
      // 进入新一轮威胁（或清空）时，允许重新自动开启Tobii回合
      stopAutoStartSaTobiiRef.current = false;
      setSaTobiiDebugBbox(null);
      if (aiSelectedThreatRef.current?.id !== currentHighestThreatId) {
        aiSelectedThreatRef.current = null;
      }
      lastHighestThreatIdRef.current = currentHighestThreatId;
    }
  }, [highestPriorityThreat?.id]);

  useEffect(() => {
    endSaTobiiRoundRef.current = endSaTobiiRound;
  }, [endSaTobiiRound]);

  useEffect(() => {
    getHighestThreatPromptPositionRef.current = getHighestThreatPromptPosition;
    getSaTobiiPromptPositionRef.current = getSaTobiiPromptPosition;
  }, [getHighestThreatPromptPosition, getSaTobiiPromptPosition]);


  // gazerelation: 监听页面卸载事件刷新，尝试结束 SA Tobii 回合
  useEffect(() => {
    const handleBeforeUnload = () => {
      // 尝试结束 SA Tobii 回合
      const promptPosition = getSaTobiiPromptPositionRef.current?.();
      endSaTobiiRoundRef.current(promptPosition || undefined);
    };

    // 监听页面卸载事件
    window.addEventListener('beforeunload', handleBeforeUnload);
    
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, []);
  useEffect(() => {
    return () => {
      const promptPosition = getSaTobiiPromptPositionRef.current?.();
      console.log('gazerelation:生命周期结束，发送结束Tobii请求', promptPosition);
      endSaTobiiRoundRef.current(promptPosition || undefined);
      if (attentionIntervalRef.current) {
        window.clearInterval(attentionIntervalRef.current);
      }
      if (attentionTimeoutRef.current) {
        window.clearTimeout(attentionTimeoutRef.current);
      }
    };
  }, []);


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
    if (useEnhancedProtocol) {
      setEnhancedThreats(prev => {
        const newList = [...prev.filter(t => t.id !== threat.id)];
        const one = prev.find(t => t.id === threat.id);
        if (one) {
          newList.unshift({...one});
        }
        return newList;
      })
    } else {
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
    }

    // 存储用户选择，但不立即显示弹窗
    setUserSelection({
      threat,
      isCorrect: !!isClickedHighestPriority
    });
    recordThreatSelection(threat.id, eventOwner === 'AI' ? 'AI' : 'manual');

    if (eventOwner === 'AI') {
      aiSelectedThreatRef.current = threat;
      if (agentStore.isAIActive && beginSATobiiServe.current && !stopAutoStartSaTobiiRef.current) {
        const promptPosition = getThreatPromptPosition(threat);
        if (promptPosition) {
          startSaTobiiRound(promptPosition);
          beginSATobiiServe.current = false;
          console.log('gazerelation:startSaTobiiRound AI selected target', promptPosition);
        }
      }
    }

    // 注意：不在这里启用详细信息显示，只有点击"查看结果"时才显示分数
    // if (onShowDetailedInfoChange) {
    //   onShowDetailedInfoChange(true);
    // }
    
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
        extra: buildThreatTrustLogExtra(),
      });
    }
    
    // 确保威胁处理日志写入
    if (onAddMessage) {
      const actor = eventOwner === 'AI' ? '[AI]' : '[用户]';
      const priorityText = originalPriority === 'high' ? '高' : originalPriority === 'medium' ? '中' : '低';
      onAddMessage('sa_threat', `${actor} 选择威胁：${threatLabel}，优先级：${priorityText}，等待确认`);
    }
  }, [getCurrentHighestPriorityThreat, getThreatPromptPosition, onAddMessage, sendMessage, startSaTobiiRound, userId, lastEmergencyReceiveTimestampRef, recordThreatSelection, buildThreatTrustLogExtra]);

  // 渲染导弹
  const renderMissiles = () => {
    return missiles.map(missile => {
      const Icon = missile.type === 'MissileUp' ? MissileUpIcon : MissileDownIcon;
      const isSelected = missile.id === selectedThreatId;
      const isHighestPriority = missile.id === highestPriorityThreat?.id;
      const shouldAttentionBlink = missile.id === eyeFeedbackThreatId && highestThreatAttentionVisible;
      const position = fanThreatPositions.get(missile.id) || { x: missile.x, y: missile.y };
      const isScanned = isPointInFanScan(position);
      const showRecommendationFrame = !showTaskComplete && shouldAttentionBlink;
      const showCorrectAnswerFrame = showTaskComplete && isHighestPriority;
      const showIncorrectSelectionFrame = showTaskComplete && isSelected && !isHighestPriority;
      const isTrustTop = threatTrustDecision.enabled && missile.id === threatTrustDecision.topThreatId;
      const isTrustSecond = threatTrustDecision.enabled && missile.id === threatTrustDecision.secondThreatId;
      const trustStroke = threatTrustDecision.controlLevel === 'review' ? '#ff9a2e' : '#1ca8ff';

      return (
        <Group key={missile.id} opacity={isScanned || isSelected ? 1 : 0.36} onClick={() => handleThreatIconClick(missile, 'manual')}>
          {(isTrustTop || (threatTrustDecision.rankingUnstable && isTrustSecond)) && (
            <Rect
              x={position.x - 26}
              y={position.y - 31}
              width={52}
              height={62}
              stroke={trustStroke}
              strokeWidth={2}
              dash={[6, 4]}
              cornerRadius={6}
            />
          )}
          {threatTrustDecision.rankingUnstable && isTrustSecond && (
            <Text
              x={position.x + 24}
              y={position.y - 30}
              text="~"
              fontSize={22}
              fill="#ffb45c"
              fontFamily="monospace"
            />
          )}
          {showRecommendationFrame && (
            <Rect
              x={position.x - 26}
              y={position.y - 31}
              width={52}
              height={62}
              stroke={RECOMMENDATION_COLOR}
              strokeWidth={3}
              dash={[4, 4]}
              cornerRadius={6}
            />
          )}
          {/* 用户选择的答案边框（黄色） */}
          {showIncorrectSelectionFrame && (
            <Rect
              x={position.x - 20}
              y={position.y - 25}
              width={30 + 10} // missile icon size is 30
              height={30 + 20}
              stroke={SELECTED_FILL_COLOR}
              strokeWidth={2}
              cornerRadius={5}
            />
          )}
          {/* 正确答案边框（红色） */}
          {showCorrectAnswerFrame && (
            <Rect
              x={position.x - 22}
              y={position.y - 27}
              width={30 + 14} // 稍微大一点以区分
              height={30 + 24}
              stroke={CORRECT_ANSWER_COLOR}
              strokeWidth={3}
              cornerRadius={5}
            />
          )}
          <Icon
            x={position.x}
            y={position.y}
            size={30}
            color={PRIMARY_THREAT_COLOR}
            strokeWidth={3}
            fillColor={isSelected ? PRIMARY_THREAT_COLOR : undefined}
            fillOpacity={0.72}
          />
          {/* 导弹图标中心点标记 - 黄色小圆点 */}
          <Circle
            x={position.x} // 导弹图标大小是30，所以中心点是 + 15
            y={position.y}
            radius={3}
            fill="#ffff00"
            stroke="#000000"
            strokeWidth={1}
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
    console.log(`[gazerelation] AI选择最有目标中`);
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

  // 摇杆 button1：选择光标附近最近的目标（弹窗期间屏蔽）
  React.useEffect(() => {
    if (button1 && !prevButton1Ref.current && joystickEnabled && joystickCursorPos && !showTaskComplete) {
      console.log('[SAPage] Button1按下，查找光标附近目标');

      // 构建带位置的威胁列表（与渲染逻辑一致）
      let allThreats: { threat: any; pos: { x: number; y: number } }[] = [];

      if (useEnhancedProtocol && enhancedThreats.length > 0) {
        enhancedThreats
          .filter(et => !et.is_missile)
          .forEach(et => {
            if (et.position) {
              allThreats.push({
                threat: { id: et.id, type: et.type, label: et.label, position: et.position, _enhanced: et },
                pos: et.position
              });
            }
          });
      } else {
        saThreats.forEach((threat: any, idx: number) => {
          const pos = threatPositions[idx];
          if (pos) {
            allThreats.push({ threat, pos });
          }
        });
      }

      // 加入导弹
      missiles.forEach(missile => {
        allThreats.push({ threat: missile, pos: { x: missile.x, y: missile.y } });
      });
      const fanThreats: { threat: any; pos: { x: number; y: number } }[] = [];
      threatsWithScore.forEach(({ threat }) => {
        const pos = fanThreatPositions.get(threat.id);
        if (pos) {
          fanThreats.push({ threat, pos });
        }
      });
      allThreats = fanThreats;

      // 找最近目标
      let closest: any = null;
      let minDist = 40;
      allThreats.forEach(({ threat, pos }) => {
        const dist = Math.sqrt(
          Math.pow(pos.x - joystickCursorPos.x, 2) +
          Math.pow(pos.y - joystickCursorPos.y, 2)
        );
        if (dist < minDist) {
          minDist = dist;
          closest = threat;
        }
      });

      if (closest) {
        console.log('[SAPage] 摇杆选中目标:', closest.id, '距离:', minDist.toFixed(1));
        handleThreatIconClick(closest, 'manual');
      } else {
        console.log('[SAPage] 光标附近未找到目标');
      }
    }
    prevButton1Ref.current = button1;
  }, [button1, joystickEnabled, joystickCursorPos, enhancedThreats, saThreats, threatPositions, missiles, useEnhancedProtocol, handleThreatIconClick, showTaskComplete, isCorrect, setShowTaskComplete, handleResetSA, threatsWithScore, fanThreatPositions]);

  // 摇杆 button2：弹窗期间触发确认，否则触发"查看结果"
  React.useEffect(() => {
    if (button2 && !prevButton2Ref.current && joystickEnabled) {
      if (showTaskComplete) {
        console.log('[SAPage] Button2按下，确认任务评估弹窗');
        if (isCorrect === true || isCorrect === false) {
          setShowTaskComplete(false);
          if (hasReachedSAOverallTotal || isSAAllCompleted) {
            onResultConfirmed?.();
            prevButton2Ref.current = button2;
            return;
          }
          // 推进 SA 任务次数：发 ResetSA 让服务端返回下一个 sa_task_updated。
          handleResetSA();
        } else {
          handleResetSA();
        }
      } else {
        console.log('[SAPage] Button2按下，触发查看结果');
        handleButtonClick('查看结果');
      }
    }
    prevButton2Ref.current = button2;
  }, [button2, joystickEnabled, showTaskComplete, isCorrect, setShowTaskComplete, handleResetSA, onResultConfirmed, hasReachedSAOverallTotal, isSAAllCompleted]);

  // const [isStarted, setIsStarted] = useState(false);
  // const [antennaAdjustmentRequired, setAntennaAdjustmentRequired] = useState(false);
  // const [targetAntennaElevation, setTargetAntennaElevation] = useState<number | null>(null);
  // const [confirmAntennaAdjustmentHandled, setConfirmAntennaAdjustmentHandled] = useState(false);

  // useEffect(() => {
  //   console.log('[AI Radar Antenna Effect Check]', {
  //     isAIActive: agentStore.isAIActive,
  //     isStarted,
  //     antennaAdjustmentRequired,
  //     targetAntennaElevation,
  //   });
  //   if (
  //     agentStore.isAIActive &&
  //     isStarted &&
  //     antennaAdjustmentRequired &&
  //     targetAntennaElevation !== null
  //   ) {
  //     console.log(`[AI Radar] Antenna adjustment required. Target elevation: ${targetAntennaElevation}. AI is taking action.`);
      
  //     // Pass 'ai' as source and the sendMessage callback
  //     radarStore.setCurrentAntennaElevation(targetAntennaElevation, 'ai', sendMessage);
      
    
  //     console.log(`[AI Radar] Antenna elevation automatically set to ${targetAntennaElevation} by AI and requirement cleared.`);
  //   }
  // }, [
  //   agentStore.isAIActive,
  //   isStarted,
  //   antennaAdjustmentRequired,
  //   targetAntennaElevation,
  //   sendMessage,
  //   confirmAntennaAdjustmentHandled,
  //   radarStore
  // ]);

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

  // const handleConfirmAndReset = () => {
  //   if (onResetSA) {
  //     onResetSA();
  //   }
  //   setShowTaskComplete(false);
  // };

  // 计算威胁数据并传递给父组件
  React.useEffect(() => {
    if (!onThreatListUpdate) return;
    
    const effectiveCenterY = config.centerY - 50;
    
    // 计算威胁距离和得分的函数 - 支持增强协议
    const calculateThreatInfo = (threat: any, threatIndex: number) => {
      let distance = 0;
      let score = 0;
      
      // 如果威胁对象已经包含增强数据（从_enhanced字段获取）
      if (threat._enhanced) {
        console.log('【威胁计算】使用增强威胁数据:', threat.id, 
                   '距离:', threat._enhanced.distance_from_center?.toFixed(1), 
                   '得分:', threat._enhanced.score?.toFixed(2));
        distance = threat._enhanced.distance_from_center || 0;
        score = threat._enhanced.score || 0;
        return { distance, score };
      }
      
      // 如果威胁对象预设了距离信息（从saThreatsToUse转换而来）
      if (threat.distance !== undefined && threat.distance > 0) {
        console.log('【威胁计算】使用预设距离:', threat.id, '距离:', threat.distance?.toFixed(1));
        distance = threat.distance || 0;
        // 根据威胁类型和距离计算分数
        const getTypeWeight = (type: string): number => {
          if (type.toLowerCase().includes('missile')) return 245;
          if (type.startsWith('Primary')) return 240;
          if (type.startsWith('Secondary')) return 200;
          return 80;
        };
        const weight = getTypeWeight(threat.type || '');
        score = distance > 0 ? weight / Math.max(distance, 1) : 0;
        console.log('【威胁计算】计算得分:', threat.id, '得分:', score?.toFixed(2));
        return { distance, score };
      }
      
      // 传统协议：计算距离和分数
      const getTypeWeight = (type: string): number => {
        if (type.toLowerCase().includes('missile')) return 245;
        if (type.startsWith('Primary')) return 240;
        if (type.startsWith('Secondary')) return 200;
        return 80;
      };
      
      const isMissile = threat.type === 'MissileUp' || threat.type === 'MissileDown';
      
      if (isMissile) {
        const missile = missiles.find(m => m.id === threat.id);
        if (missile) {
          const missileCenterX = missile.x || 0;
          const missileCenterY = missile.y || 0;
          distance = Math.sqrt(Math.pow(missileCenterX - config.centerX, 2) + Math.pow(missileCenterY - effectiveCenterY, 2));
          const weight = getTypeWeight('missile');
          score = distance > 0 ? weight / Math.max(distance, 1) : weight;
          console.log('【威胁计算】传统导弹:', threat.id, '距离:', distance?.toFixed(1), '得分:', score?.toFixed(2));
        } else {
          // 如果找不到导弹数据，使用默认值
          distance = 100;
          score = getTypeWeight('missile') / 100;
          console.log('【威胁计算】传统导弹(默认):', threat.id, '距离:', distance, '得分:', score?.toFixed(2));
        }
      } else {
        const saIndex = saThreats.findIndex((st: any) => st.id === threat.id);
        if (saIndex >= 0 && threatPositions[saIndex]) {
          const pos = threatPositions[saIndex];
          const threatCenterX = (pos.x || 0) + ICON_SIZE / 2;
          const threatCenterY = (pos.y || 0) + ICON_SIZE / 2;
          distance = Math.sqrt(Math.pow(threatCenterX - config.centerX, 2) + Math.pow(threatCenterY - effectiveCenterY, 2));
          const weight = getTypeWeight(threat.type || '');
          score = distance > 0 ? weight / Math.max(distance, 1) : weight / 100;
          console.log('【威胁计算】传统威胁:', threat.id, '距离:', distance?.toFixed(1), '得分:', score?.toFixed(2));
        } else {
          // 如果找不到位置数据，使用默认值
          distance = 150;
          const weight = getTypeWeight(threat.type || '');
          score = weight / 150;
          console.log('【威胁计算】传统威胁(默认):', threat.id, '距离:', distance, '得分:', score?.toFixed(2));
        }
      }
      
      return { distance, score };
    };
    
    // 合并所有威胁数据 - 支持增强协议
    let saThreatsToUse: any[] = [];
    
    if (useEnhancedProtocol && enhancedThreats.length > 0) {
      // 使用增强协议：将enhancedThreats转换为统一格式
      console.log('【威胁列表】使用增强协议威胁数据，数量:', enhancedThreats.length);
      saThreatsToUse = enhancedThreats
        .filter(et => !et.is_missile) // 过滤掉导弹，它们单独处理
        .map(et => ({
          id: et.id,
          type: et.type,
          label: et.label,
          source: et.label,
          distance: et.distance_from_center,
          heading: 0, // 增强威胁数据中没有航向信息
          priority: et.priority,
          // 保留增强数据
          _enhanced: et
        }));
        console.log('【威胁列表】使用增强协议威胁数据 11111', saThreatsToUse)
    } else {
      // 使用传统协议
      console.log('【威胁列表】使用传统协议威胁数据，数量:', saThreats.length);
      saThreatsToUse = saThreats;
    }
    // 重要修复：威胁值计算基于原始数据，不受用户交互影响
    console.log('【威胁计算】基于原始数据计算，saThreats:', saThreats.length, 'missiles:', missiles.length, 'enhancedThreats:', enhancedThreats.length);
    
    // 所有威胁基于原始数据源，不包含用户交互产生的threatList
    const allBaseThreats = [
      ...saThreatsToUse,
      ...missiles.map((missile: any) => {
        console.log('【威胁计算】添加导弹威胁:', missile.id, missile.type, missile.distance_from_center, missile.score);
        return {
          id: missile.id,
          type: missile.type,
          label: missile.label,
          source: missile.label,
          distance: missile.distance_from_center,
          heading: 0,
          priority: 'high' as const,
          _enhanced: missile,
        };
      }),
    ];
    
    // 合并用户选择的威胁（仅用于显示顺序，不影响计算）
    const allThreats = [
      ...threatList, // 用户选择的威胁在前
      ...allBaseThreats.filter((baseThreat: any) => !threatList.some(t => t.id === baseThreat.id)) // 剩余威胁在后
    ].map((threat, index) => {
      const { distance, score } = calculateThreatInfo(threat, index);
      const displayType = TYPE_MAP[threat.type] || threat.type || '未知威胁';
      const target = threat.target || threat.label || threat.source || '未知目标';
      const creationTimestamp = Number(threat.creation_timestamp ?? threat._enhanced?.creation_timestamp);
      
      // 创建符合 ThreatData 接口的干净对象
      const cleanThreatData = {
        id: threat.id,
        type: threat.type,
        label: target,
        target,
        rank: index + 1,
        index: index + 1,
        distance: distance || 0,
        score: score || 0,
        displayType,
        time: formatClockTime(creationTimestamp, String(threat.id ?? target)),
        priorityLevel: (threat.priority === 'high' || threat.type?.includes('Primary')) ? '高' : 
                      (threat.priority === 'medium' || threat.type?.includes('Secondary')) ? '中' : '低',
        priorityColor: (threat.priority === 'high' || threat.type?.includes('Primary')) ? '#ff0000' : 
                      (threat.priority === 'medium' || threat.type?.includes('Secondary')) ? '#ffff00' : '#00ffff'
      };
      
      return cleanThreatData;
    });
    const attackRows = allThreats.map((threat, index) => ({
      id: `attack-${threat.id}`,
      number: `A-${String(index + 1).padStart(2, '0')}`,
      type: threat.displayType || threat.type || '未知类型',
      distance: threat.distance,
      source: getStableAttackSource(threat),
    }));
    
    console.log('【威胁列表】最终威胁列表数量:', allThreats.length);
    if (allThreats.length > 0) {
      console.log('【威胁列表】威胁详情:', allThreats.map(t => ({
        id: t.id, 
        rank: t.rank,
        displayType: t.displayType,
        distance: t.distance, 
        time: t.time,
        score: t.score?.toFixed(2),
        priority: t.priorityLevel
      })));
    }
    
    onThreatListUpdate({ threats: allThreats, attacks: attackRows });
  }, [saThreats, missiles, threatPositions, config.centerX, config.centerY, onThreatListUpdate, 
      useEnhancedProtocol, enhancedThreats, threatList]); // 保持threatList以确保显示顺序更新

  return (
    <div className="font-mono flex flex-col items-center relative" style={{ width: totalDisplayWidth, minWidth: totalDisplayWidth, padding: '8px 0 0' }}>
     

      <div className="flex flex-col items-center" style={{ width: totalDisplayWidth }}>
        {/* 顶部按钮 - 使用justify-between均匀分布 */}
        <div 
          className="flex justify-between mb-2" 
          style={{ width: topContainerWidth, padding: '0 20px', position: 'relative', zIndex: 20 }}
        >
          {topButtons.map(label => (
            <Button key={label} label={label} onClick={() => handleButtonClick(label)} disabled={label === '查看结果' && agentStore.isAIActive && userSelection?.threat === undefined}/>
          ))}
        </div>
        
        <div className="flex" style={{ width: totalDisplayWidth }}>
          {/* 左侧按钮 - 使用flex-col和justify-between均匀分布 */}
          <div 
            className="flex flex-col justify-between mr-4 mt-12" 
            style={{ width: sideButtonWidth, flex: `0 0 ${sideButtonWidth}px`, height: sideContainerHeight, position: 'relative', zIndex: 20 }}
          >
            {leftButtons.map((label, idx) => (
              <div key={label} className="relative">
                <Button
                  label={label}
                  onClick={idx === 1 ? (onResetSA || handleResetSA) : () => handleButtonClick(label)}
                />
              
              </div>
            ))}
          </div>
          
          {/* 雷达显示 - 仅包含雷达相关元素 */}
          <div className="sa-page bg-black relative" style={{ width, height }} ref={saCanvasRef}>
            {isSaTobiiBboxDebugEnabled && saTobiiDebugBbox && (
              <div
                aria-hidden="true"
                style={{
                  position: 'fixed',
                  left: `${saTobiiDebugBbox.left * 100}vw`,
                  top: `${saTobiiDebugBbox.top * 100}vh`,
                  width: `${Math.max(0, saTobiiDebugBbox.right - saTobiiDebugBbox.left) * 100}vw`,
                  height: `${Math.max(0, saTobiiDebugBbox.bottom - saTobiiDebugBbox.top) * 100}vh`,
                  border: '2px solid rgba(255, 64, 64, 0.95)',
                  background: 'rgba(255, 64, 64, 0.12)',
                  boxShadow: '0 0 0 1px rgba(0, 0, 0, 0.8), 0 0 12px rgba(255, 64, 64, 0.45)',
                  pointerEvents: 'none',
                  zIndex: 9999,
                }}
              />
            )}
        
            
            <Stage width={width} height={height}>
              <Layer>
                <Group>
                  <Circle
                    x={fanScanGeometry.apexX}
                    y={fanScanGeometry.apexY}
                    radius={fanScanGeometry.outerRadius}
                    fill="rgba(0, 42, 12, 0.035)"
                    stroke={config.lineColor}
                    strokeWidth={1}
                    opacity={0.72}
                  />
                  {[0.35, 0.62].map((ratio, index) => (
                    <Circle
                      key={`fan-base-ring-${index}`}
                      x={fanScanGeometry.apexX}
                      y={fanScanGeometry.apexY}
                      radius={fanScanGeometry.outerRadius * ratio}
                      stroke={config.lineColor}
                      strokeWidth={1}
                      opacity={0.28}
                    />
                  ))}
                </Group>
                <Group>
                  <Line
                    points={[
                      fanScanGeometry.apexX, fanScanGeometry.apexY,
                      fanScanGeometry.leftOuter.x, fanScanGeometry.leftOuter.y,
                      fanScanGeometry.rightOuter.x, fanScanGeometry.rightOuter.y,
                    ]}
                    closed
                    fill="rgba(0, 60, 18, 0.035)"
                  />
                  {fanSweepGeometry.trail.map((trail, trailIndex) => (
                    <Line
                      key={`fan-sweep-trail-${trailIndex}`}
                      points={[
                        fanScanGeometry.apexX, fanScanGeometry.apexY,
                        trail.left.x, trail.left.y,
                        trail.center.x, trail.center.y,
                        trail.right.x, trail.right.y,
                      ]}
                      closed
                      fill="#00ff66"
                      opacity={trail.opacity}
                    />
                  ))}
                  <Line
                    points={[
                      fanScanGeometry.apexX, fanScanGeometry.apexY,
                      fanSweepGeometry.beam.left.x, fanSweepGeometry.beam.left.y,
                      fanSweepGeometry.beam.center.x, fanSweepGeometry.beam.center.y,
                      fanSweepGeometry.beam.right.x, fanSweepGeometry.beam.right.y,
                    ]}
                    closed
                    fill="#00ff66"
                    opacity={fanSweepGeometry.pulse}
                    shadowColor="#00ff66"
                    shadowBlur={24}
                  />
                  {[0.35, 0.55, 0.75, 0.95].map((ratio, sweepIndex) => (
                    <Arc
                      key={`fan-sweep-range-${sweepIndex}`}
                      x={fanScanGeometry.apexX}
                      y={fanScanGeometry.apexY}
                      radius={fanScanGeometry.outerRadius * ratio}
                      angle={FAN_ANGLE_SPAN}
                      rotation={fanScanGeometry.startAngle}
                      stroke="#00ff66"
                      strokeWidth={1}
                      opacity={0.16 + sweepIndex * 0.03}
                    />
                  ))}
                  <Arc
                    x={fanScanGeometry.apexX}
                    y={fanScanGeometry.apexY}
                    radius={fanScanGeometry.outerRadius}
                    angle={FAN_ANGLE_SPAN}
                    rotation={fanScanGeometry.startAngle}
                    stroke={FAN_EDGE_COLOR}
                    strokeWidth={2}
                  />
                  <Arc
                    x={fanScanGeometry.apexX}
                    y={fanScanGeometry.apexY}
                    radius={fanScanGeometry.innerRadius}
                    angle={FAN_ANGLE_SPAN}
                    rotation={fanScanGeometry.startAngle}
                    stroke={FAN_EDGE_COLOR}
                    strokeWidth={1}
                  />
                  <Line
                    points={[fanScanGeometry.apexX, fanScanGeometry.apexY, fanScanGeometry.leftOuter.x, fanScanGeometry.leftOuter.y]}
                    stroke={FAN_EDGE_COLOR}
                    strokeWidth={2}
                  />
                  <Line
                    points={[fanScanGeometry.apexX, fanScanGeometry.apexY, fanScanGeometry.rightOuter.x, fanScanGeometry.rightOuter.y]}
                    stroke={FAN_EDGE_COLOR}
                    strokeWidth={2}
                  />
                  <Line
                    points={[fanScanGeometry.apexX, fanScanGeometry.apexY, fanScanGeometry.centerOuter.x, fanScanGeometry.centerOuter.y]}
                    stroke={config.lineColor}
                    strokeWidth={1}
                    dash={[10, 8]}
                    opacity={0.55}
                  />
                  <Circle
                    x={fanScanGeometry.apexX}
                    y={fanScanGeometry.apexY}
                    radius={4}
                    fill={config.lineColor}
                  />
                  <Text
                    x={fanScanGeometry.labelPoint.x - 20}
                    y={fanScanGeometry.labelPoint.y - 20}
                    text="T0"
                    fill={config.lineColor}
                    fontSize={30}
                    fontFamily="monospace"
                    fontStyle="bold"
                  />
                </Group>
                <Group visible={false}>
                {/* 第一个圆（中心圆） */}
                <Circle
                  x={config.centerX }
                  y={config.centerY - 50 }
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
                </Group>
                
                {/* 底部横线 */}
                <Line
                  points={[0, bottomLineY, width, bottomLineY]}
                  stroke="#00aa44"
                  strokeWidth={1}
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

                {/* 威胁图标渲染 - 支持增强协议和传统协议 */}
                {(() => {
                  // 使用与威胁列表相同的数据源逻辑
                  let threatsToRender: any[] = [];
                  
                  if (useEnhancedProtocol && enhancedThreats.length > 0) {
                    // 使用增强协议：将enhancedThreats转换为统一格式
                    threatsToRender = enhancedThreats
                      .filter(et => !et.is_missile) // 过滤掉导弹，它们单独处理
                      .map(et => ({
                        id: et.id,
                        type: et.type,
                        label: et.label,
                        // 添加位置信息供渲染使用
                        position: et.position,
                        // 保留增强数据
                        _enhanced: et
                      }));
                  } else {
                    // 使用传统协议
                    threatsToRender = saThreats;
                  }
                  
                  // console.log('【SAPage威胁渲染】实际渲染的威胁数量:', threatsToRender.length);
                  // console.log('【SAPage威胁渲染】威胁详情:', threatsToRender.map(t => ({
                  //   id: t.id, 
                  //   type: t.type, 
                  //   hasPosition: !!t.position,
                  //   hasEnhanced: !!t._enhanced
                  // })));
                  
                  return threatsToRender;
                })().map((threat: any, idx: number) => {
                  const threatStrokeColor = getThreatStrokeColor(threat.type, threat.priority);
                  const IconComp = StandardThreatIcon;
                  
                  // 添加调试信息
                  if (!IconComp) {
                    // console.warn(`⚠️ 未找到威胁类型 "${threat.type}" 对应的图标组件`);
                    // console.log('可用的图标类型:', Object.keys(ICON_MAP));
                    // console.log('当前威胁数据:', threat);
                    return null;
                  }
                  
                  const isSelected = threat.id === selectedThreatId;
                  const isHighestPriority = threat.id === highestPriorityThreat?.id;
                  const shouldAttentionBlink = threat.id === eyeFeedbackThreatId && highestThreatAttentionVisible;
                  const isTrustTop = threatTrustDecision.enabled && threat.id === threatTrustDecision.topThreatId;
                  const isTrustSecond = threatTrustDecision.enabled && threat.id === threatTrustDecision.secondThreatId;
                  const trustStroke = threatTrustDecision.controlLevel === 'review' ? '#ff9a2e' : '#1ca8ff';
                  
                  // 获取位置数据
                  const position = fanThreatPositions.get(threat.id) || (threat.position // 如果威胁对象有position字段，直接使用
                    ? threat.position 
                    : threatPositions[idx]); // 否则使用计算的位置
                  
                  if (!position) {
                    console.warn(`⚠️ 威胁 ${threat.id} 没有位置数据`);
                    return null;
                  }
                  
                  const isScanned = isPointInFanScan(position);
                  const showRecommendationFrame = !showTaskComplete && shouldAttentionBlink;
                  const showCorrectAnswerFrame = showTaskComplete && isHighestPriority;
                  const showIncorrectSelectionFrame = showTaskComplete && isSelected && !isHighestPriority;
                  return (
                    <Group key={threat.id} opacity={isScanned || isSelected ? 1 : 0.36} onClick={() => handleThreatIconClick(threat, 'manual')}>
                      {(isTrustTop || (threatTrustDecision.rankingUnstable && isTrustSecond)) && (
                        <Rect
                          x={position.x  - ICON_SIZE / 2 - 11}
                          y={position.y  - ICON_SIZE / 2 - 11}
                          width={ICON_SIZE + 22}
                          height={ICON_SIZE + 22}
                          stroke={trustStroke}
                          strokeWidth={2}
                          dash={[6, 4]}
                          cornerRadius={6}
                        />
                      )}
                      {threatTrustDecision.rankingUnstable && isTrustSecond && (
                        <Text
                          x={position.x + ICON_SIZE / 2 + 8}
                          y={position.y - ICON_SIZE / 2 - 12}
                          text="~"
                          fontSize={22}
                          fill="#ffb45c"
                          fontFamily="monospace"
                        />
                      )}
                      {showRecommendationFrame && (
                        <Rect
                          x={position.x  - ICON_SIZE / 2 - 12}
                          y={position.y  - ICON_SIZE / 2 - 12}
                          width={ICON_SIZE + 24}
                          height={ICON_SIZE + 24}
                          stroke={RECOMMENDATION_COLOR}
                          strokeWidth={3}
                          dash={[4, 4]}
                          cornerRadius={8}
                        />
                      )}
                      {/* 用户选择的答案边框（黄色/绿色） */}
                      {showIncorrectSelectionFrame && (
                        <Rect
                          x={position.x  - ICON_SIZE / 2 - 5}
                          y={position.y  - ICON_SIZE / 2 - 5}
                          width={ICON_SIZE + 10}
                          height={ICON_SIZE + 10}
                          stroke={SELECTED_FILL_COLOR}
                          strokeWidth={2}
                          cornerRadius={5}
                        />
                      )}
                      {/* 正确答案边框（红色） */}
                      {showCorrectAnswerFrame && (
                        <Rect
                          x={position.x  - ICON_SIZE / 2 - 7}
                          y={position.y  - ICON_SIZE / 2 - 7}
                          width={ICON_SIZE + 14}
                          height={ICON_SIZE + 14}
                          stroke={CORRECT_ANSWER_COLOR}
                          strokeWidth={3}
                          cornerRadius={5}
                        />
                      )}
                      <IconComp
                        x={position.x}
                        y={position.y}
                        size={ICON_SIZE}
                        stroke={threatStrokeColor}
                        fill={isSelected ? SELECTED_FILL_COLOR : undefined}
                        label={threat.label}
                      />
                      {/* 威胁图标中心点标记 - 黄色小圆点 */}
                      <Circle
                        x={position.x}
                        y={position.y}
                        radius={3}
                        fill="#ffff00"
                        stroke="#000000"
                        strokeWidth={1}
                      />
                      <Text
                        x={position.x  - ICON_SIZE / 2 + ICON_SIZE + 5}
                        y={position.y  - ICON_SIZE / 2 + ICON_SIZE / 2 - 8}
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

                {/* 摇杆光标 */}
                {joystickCursorPos && (
                  <Group>
                    <Line
                      points={[joystickCursorPos.x - 15, joystickCursorPos.y, joystickCursorPos.x + 15, joystickCursorPos.y]}
                      stroke="#ffffff"
                      strokeWidth={2}
                    />
                    <Line
                      points={[joystickCursorPos.x, joystickCursorPos.y - 15, joystickCursorPos.x, joystickCursorPos.y + 15]}
                      stroke="#ffffff"
                      strokeWidth={2}
                    />
                  </Group>
                )}

              </Layer>
            </Stage>
          </div>
          
          {/* 右侧按钮 - 使用flex-col和justify-between均匀分布 */}
          <div 
            className="flex flex-col justify-between ml-4 mt-12" 
            style={{ width: sideButtonWidth, flex: `0 0 ${sideButtonWidth}px`, height: sideContainerHeight, position: 'relative', zIndex: 20 }}
          >
            {/* 音频控制按钮 - 状态直接来自 agentStore */}
            
            
            {rightButtons.map(label => (
              <Button key={label} label={label} onClick={() => handleButtonClick(label)} />
            ))}
          </div>
        </div>
      </div>
      

      
      {showTaskComplete && (
        <div style={{
            position: 'fixed',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            zIndex: 100,
            pointerEvents: 'auto',
        }}>
          <div style={{
              background: 'rgba(1,12,4,0.97)',
              padding: '28px 36px',
              border: '1px solid #0d4020',
              borderLeft: `3px solid ${isCorrect === true ? '#00cc55' : isCorrect === false ? '#cc3333' : '#556655'}`,
              borderRadius: '4px',
              textAlign: 'center',
              boxShadow: '0 0 30px rgba(0,0,0,0.8), 0 0 20px rgba(0,180,70,0.08)',
              fontFamily: "'Share Tech Mono', monospace",
              minWidth: '280px',
          }}>
            <div style={{
              fontSize: '12px',
              letterSpacing: '0.25em',
              color: '#4aaa60',
              textTransform: 'uppercase',
              marginBottom: '14px',
            }}>
              ── 任务评估 ──
            </div>
            <p style={{
              margin: '0 0 10px 0',
              fontSize: '18px',
              letterSpacing: '0.12em',
              color: isCorrect === true ? '#00cc55' : isCorrect === false ? '#cc4444' : '#667766',
            }}>
              {isCorrect === true ? '✓ 判断正确' : isCorrect === false ? '✗ 判断错误' : '— 未作选择'}
            </p>
            <p style={{
              margin: '0 0 20px 0',
              fontSize: '13px',
              color: '#55aa66',
              letterSpacing: '0.06em',
            }}>
              {isCorrect === true || isCorrect === false ? '当前任务已结束，可关闭窗口' : '请重新完成当前任务'}
            </p>
            <button
              onClick={isCorrect === true || isCorrect === false ? () => {
                setShowTaskComplete(false);
                if (hasReachedSAOverallTotal || isSAAllCompleted) {
                  onResultConfirmed?.();
                  return;
                }
                // 推进 SA 任务次数：发 ResetSA 让服务端返回下一个 sa_task_updated。
                handleResetSA();
              } : handleResetSA}
              style={{
                fontFamily: "'Share Tech Mono', monospace",
                fontSize: '13px',
                letterSpacing: '0.15em',
                background: 'rgba(0,30,12,0.6)',
                border: '1px solid #0d4020',
                color: '#00aa44',
                padding: '8px 28px',
                cursor: 'pointer',
                borderRadius: '3px',
                transition: 'background 0.15s',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = 'rgba(0,50,20,0.8)'; }}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = 'rgba(0,30,12,0.6)'; }}
            >
              确认
            </button>
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
  opacity?: number;
}

const Arc: React.FC<ArcProps> = ({ x, y, radius, angle, rotation = 0, stroke, strokeWidth, opacity = 1 }) => {
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
      opacity={opacity}
      lineCap="round"
    />
  );
};

export default SAPage;
