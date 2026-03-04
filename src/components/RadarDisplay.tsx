import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Stage, Layer, Group, Line } from 'react-konva';
import { observer } from 'mobx-react-lite';
import { renderMainFrame, renderText } from './RadarRenderers';
import { RadarTarget } from '../hooks/useRadarData';
import ScanLine from './ScanLine';
import ConnectionStatus from './ConnectionStatus';
import VelocityVector from './VelocityVector';
import HorizonHUD from './HorizonHUD';
import { UnknownTargetManager } from './UnknownTargetManager';
import radarStore from '../stores/RadarStore';
import { isLastRepetition, formatRepetitionText } from '../utils/repetitionUtils';
import useRadarData from '../hooks/useRadarData';
import agentStore from '../stores/AgentStore';
import ScenarioCompletionModal from './ScenarioCompletionModal';
import audioManager from '../managers/AudioManager';
import { useDifficultyChangeDetection } from '../utils/difficultyUtils';
import DifficultyChangeModal from './DifficultyChangeModal';

// 扫描控制参数类型
export interface ScanControlParams {
  // 扫描速度系数，控制扫描的快慢，值越大扫描越快
  scanSpeed?: number; // 默认值：1.0，大于0
  // 以下参数保留，但在新的扫描实现中不再使用
  sinCoefficient?: number;
  amplitudeScale?: number;
  useSineMapping?: boolean;
}

// 雷达扫描模式类型
export interface ScanModeType {
  name: string;
  scanAngle: number; // 扫描角度范围，如60或15
  scanFraction: number; // 扫描区域占比，如1.0表示全区域，0.25表示1/4
  centerOffset?: number; // 扫描中心位置的偏移量，默认为0（即中心位置）
  elevationLevel?: 'low' | 'medium' | 'high'; // 添加天线高度级别
}

// Define the parameters for onTargetSelect callback
interface TargetSelectParams {
  targetId: string | undefined;
  lockX?: number;
  iffMode?: boolean;
  externalTargetsTimestamp?: number | null;
}

// 定义组件属性接口
export interface RadarDisplayProps {
  width: number;
  height: number;
  radarConfig: any;
  framePositions: {
    startX: number;
    startY: number;
    endX: number;
    endY: number;
  };
  tdcPosition: { x: number, y: number };
  onTargetSelect?: (params: TargetSelectParams) => void;
  scanMode: ScanModeType;
  scanControl: ScanControlParams;
  onTDCPositionSet?: (offset: number) => void;
  showVectorHUD?: boolean;
  range?: number;
  showUnknownTargets?: boolean;
  unknownTargetCount?: number;
  maxScanCount?: number; // 添加扫描计数上限属性
  displayMode?: 'AUTO' | 'HI' | 'MED'; // 添加显示模式属性，用于外部控制
  onModeDisplayChange?: (mode: 'AUTO' | 'HI' | 'MED') => void; // 添加显示模式变更回调
  isSilent?: boolean; // 添加雷达静默模式属性
  isStarted?: boolean; // 添加系统启动状态属性
  sendMessage: (message: any) => void; // 添加发送消息函数
  resetIFF?: React.MutableRefObject<() => void>; // 添加用于重置IFF模式的ref
  connected: boolean;
  radarData: import('../hooks/useRadarData').RadarData | null;
  error: string | null;
  onResetForNextMission?: () => void;
  onAddMessage?: (type: import('./CommunicationLog').MessageType, content: string) => void; // 添加日志记录功能
  onClearMessages?: () => void; // 添加清空日志功能
  cognitiveLoad?: 'low' | 'medium' | 'high'; // 认知负荷等级：低/中/高
}

const RadarDisplay: React.FC<RadarDisplayProps> = observer(({ 
  width, 
  height, 
  radarConfig, 
  framePositions,
  tdcPosition,
  onTargetSelect,
  scanMode = { name: 'normal', scanAngle: 60, scanFraction: 1 }, // 默认扫描模式
  scanControl = { scanSpeed: 1.0 }, // 默认扫描控制参数
  onTDCPositionSet, // TDC位置设置回调函数
  showVectorHUD = true, // 默认显示
  range = 20, // 默认范围值
  showUnknownTargets = true, // 默认显示未知目标
  maxScanCount = 4, // 默认值为4
  displayMode, // 从props接收显示模式
  onModeDisplayChange, // 显示模式变更回调
  isSilent = false, // 默认不处于静默模式
  isStarted = false, // 默认未启动状态
  sendMessage, // 传递发送消息函数
  resetIFF,
  connected,
  radarData,
  error,
  onResetForNextMission,
  onAddMessage,
  onClearMessages,
  cognitiveLoad = 'low'
}) => {
  // 使用钩子获取实时雷达数据以及发送消息的函数
  // const { connected, radarData, error } = useRadarData(wsUrl);
  
  // 获取重复信息和摇杆数据
  const { repetitionInfos, mainPos, subY, button1, button2, button7, joystickEnabled } = useRadarData();

  // 计算当前难度和AI状态
  const currentDifficulty = useMemo(() => {
    const radarRepetitionInfo = repetitionInfos['RADAR_TARGETING'];
    return radarRepetitionInfo && typeof radarRepetitionInfo !== 'string' ? (radarRepetitionInfo as any).difficulty : undefined;
  }, [repetitionInfos]);

  const isAIActive = useMemo(() => {
    const radarRepetitionInfo = repetitionInfos['RADAR_TARGETING'];
    return radarRepetitionInfo && typeof radarRepetitionInfo !== 'string' ? !!(radarRepetitionInfo as any).is_ai_active : false;
  }, [repetitionInfos]);

  // 添加任务确认弹窗状态
  const [showMissionConfirm, setShowMissionConfirm] = React.useState(false);
  const [missionResultMessage, setMissionResultMessage] = React.useState(''); // State to hold the result message
  const [radarAzimuth, setRadarAzimuth] = React.useState<number>(0);
  const [ownHeading, setOwnHeading] = React.useState<number>(0);
  
  // 添加IFF模式状态
  const [iffMode, setIffMode] = React.useState(false);
  
  // 添加HI/MED状态切换
  const [hiMedToggle, setHiMedToggle] = React.useState<'HI' | 'MED'>('HI');
  const [showScenarioCompletionModal, setShowScenarioCompletionModal] = React.useState(false);
  const [showDifficultyChangeModal, setShowDifficultyChangeModal] = React.useState(false);
  
  // 摇杆控制TDC相关状态
  const [calibrationOffset, setCalibrationOffset] = React.useState({x: 0, y: 0});
  const [expectedJoystickPos, setExpectedJoystickPos] = React.useState({x: 0, y: 0});
  const [lockedTdcPosition, setLockedTdcPosition] = React.useState<{x: number, y: number} | null>(null);
  const previousButton7Ref = React.useRef(false);
  
  // 摇杆控制天线高度相关状态
  const [lockedAntennaElevation, setLockedAntennaElevation] = React.useState<number | null>(null);
  const [antennaElevationCalibrationOffset, setAntennaElevationCalibrationOffset] = React.useState(0);
  const [expectedSubY, setExpectedSubY] = React.useState(0);
  
  // 防抖相关状态 - 防止快速重复触发
  const lastButton7TriggerTime = React.useRef(0);
  const button7DebounceDelay = 300; // 300ms防抖延迟
  
  // 将重置函数暴露给父组件
  React.useEffect(() => {
    if (resetIFF) {
      resetIFF.current = () => {
        setIffMode(false);
        console.log('IFF mode has been reset via ref.');
      };
    }
  }, [resetIFF]);
  
  // 计算显示区域中心
  const centerX = (framePositions.startX + framePositions.endX) / 2;
  const centerY = (framePositions.startY + framePositions.endY) / 2;
  
  // TDC坐标转换函数
  const tdcToJoystick = React.useCallback((tdcPos: {x: number, y: number}) => {
    const radarWidth = framePositions.endX - framePositions.startX;
    const radarHeight = framePositions.endY - framePositions.startY;
    const bufferX = 20;
    const bufferY = 20;
    
    // 将TDC屏幕坐标转换为摇杆逻辑坐标(-1到1)
    const joystickX = ((tdcPos.x - framePositions.startX - bufferX) / (radarWidth - 2 * bufferX)) * 2 - 1;
    const joystickY = ((tdcPos.y - framePositions.startY - bufferY) / (radarHeight - 2 * bufferY)) * 2 - 1;
    
    // 限制在-1到1范围内
    return {
      x: Math.max(-1, Math.min(1, joystickX)),
      y: Math.max(-1, Math.min(1, joystickY))
    };
  }, [framePositions]);
  
  const joystickToTdc = React.useCallback((joystickPos: {x: number, y: number}) => {
    const radarWidth = framePositions.endX - framePositions.startX;
    const radarHeight = framePositions.endY - framePositions.startY;
    const bufferX = 20;
    const bufferY = 20;
    
    // 将摇杆坐标(-1到1)转换为TDC屏幕坐标
    const tdcX = framePositions.startX + bufferX + 
                 (joystickPos.x + 1) / 2 * (radarWidth - 2 * bufferX);
    const tdcY = framePositions.startY + bufferY + 
                 (joystickPos.y + 1) / 2 * (radarHeight - 2 * bufferY);
    
    return { x: tdcX, y: tdcY };
  }, [framePositions]);
  
  // 副轴到天线高度的转换函数
  const subYToAntennaElevation = React.useCallback((subY: number) => {
    // 将副轴坐标(-1到1)转换为天线高度(-3到3度)
    // subY: -1 = 天线高度 +3度（最高）
    // subY: +1 = 天线高度 -3度（最低）
    const elevation = -subY * 3; // 反向映射
    return Math.max(-3, Math.min(3, Math.round(elevation))); // 限制在-3到3度范围内并四舍五入
  }, []);
  
  const antennaElevationToSubY = React.useCallback((elevation: number) => {
    // 将天线高度(-3到3度)转换为副轴坐标(-1到1)
    return -elevation / 3; // 反向映射
  }, []);
  
  

  
  // 计算校准后的摇杆位置
  const getCalibratedJoystickPos = React.useCallback(() => {
    if (!joystickEnabled || !mainPos) {
      return { x: 0, y: 0 };
    }
    
    // 应用校准偏移
    return {
      x: Math.max(-1, Math.min(1, mainPos.x + calibrationOffset.x)),
      y: Math.max(-1, Math.min(1, mainPos.y + calibrationOffset.y))
    };
  }, [joystickEnabled, mainPos, calibrationOffset]);
  
  // 计算校准后的副轴位置
  const getCalibratedSubY = React.useCallback(() => {
    if (!joystickEnabled || subY === undefined) {
      return 0;
    }
    
    // 应用校准偏移
    return Math.max(-1, Math.min(1, subY + antennaElevationCalibrationOffset));
  }, [joystickEnabled, subY, antennaElevationCalibrationOffset]);
  
  // 根据摇杆位置计算TDC位置
  const calculatedTdcPosition = React.useMemo(() => {
    // 如果TDC位置被锁定，使用锁定时的TDC位置
    if (lockedTdcPosition) {
      console.log('[TDC计算] TDC位置已锁定，使用锁定位置:', lockedTdcPosition);
      return lockedTdcPosition;
    }
    
    if (!joystickEnabled) {
      console.log('[TDC计算] 摇杆未启用，使用原始位置:', tdcPosition);
      return tdcPosition; // 摇杆未启用时使用原始位置
    }
    
    const calibratedPos = getCalibratedJoystickPos();
    const newTdcPos = joystickToTdc(calibratedPos);
    
    // 调试日志（减少频繁日志输出）
    if (Math.abs(newTdcPos.x - tdcPosition.x) > 1 || Math.abs(newTdcPos.y - tdcPosition.y) > 1) {
      console.log('[TDC计算] 摇杆控制模式');
      console.log('[TDC计算] 摇杆物理位置:', mainPos);
      console.log('[TDC计算] 校准偏移量:', calibrationOffset);
      console.log('[TDC计算] 校准后位置:', calibratedPos);
      console.log('[TDC计算] 计算TDC位置:', newTdcPos);
      console.log('[TDC计算] 锁定状态:', radarStore.lockedTargetId ? '已锁定' : '未锁定');
    }
    
    return newTdcPos;
  }, [joystickEnabled, getCalibratedJoystickPos, joystickToTdc, tdcPosition, lockedTdcPosition, mainPos, calibrationOffset]);
  
  // 根据副轴位置计算天线高度
  const calculatedAntennaElevation = React.useMemo(() => {
    // 如果天线高度被锁定，使用锁定时的天线高度
    if (lockedAntennaElevation !== null) {
      console.log('[天线高度计算] 天线高度已锁定，使用锁定高度:', lockedAntennaElevation);
      return lockedAntennaElevation;
    }
    
    if (!joystickEnabled || subY === undefined) {
      return radarStore.currentAntennaElevation; // 摇杆未启用时使用store中的当前值
    }
    
    const calibratedSubY = getCalibratedSubY();
    const newElevation = subYToAntennaElevation(calibratedSubY);
    
    // 调试日志（减少频繁日志输出）
    if (Math.abs(newElevation - radarStore.currentAntennaElevation) > 0.1) {
      console.log('[天线高度计算] 副轴控制模式');
      console.log('[天线高度计算] 副轴物理位置:', subY);
      console.log('[天线高度计算] 校准偏移量:', antennaElevationCalibrationOffset);
      console.log('[天线高度计算] 校准后位置:', calibratedSubY);
      console.log('[天线高度计算] 计算天线高度:', newElevation);
      console.log('[天线高度计算] 锁定状态:', lockedAntennaElevation !== null ? '已锁定' : '未锁定');
    }
    
    return newElevation;
  }, [joystickEnabled, getCalibratedSubY, subYToAntennaElevation, radarStore.currentAntennaElevation, lockedAntennaElevation, subY, antennaElevationCalibrationOffset]);
  
  // 监听计算出的天线高度变化，更新radarStore
  React.useEffect(() => {
    if (joystickEnabled && calculatedAntennaElevation !== radarStore.currentAntennaElevation) {
      radarStore.setCurrentAntennaElevation(calculatedAntennaElevation, 'user', sendMessage);
    }
  }, [calculatedAntennaElevation, joystickEnabled, sendMessage]);
  
  // 监听目标解锁时清除TDC位置锁定（如果是通过其他方式解锁的目标）
  React.useEffect(() => {
    // 如果目标被其他方式解锁（比如键盘Escape键），同时清除TDC位置锁定
    if (!radarStore.lockedTargetId && lockedTdcPosition) {
      console.log('[目标解锁] 检测到目标被其他方式解锁，清除TDC位置锁定');
      
      const lastLockedPosition = lockedTdcPosition;
      setLockedTdcPosition(null);
      
      if (joystickEnabled && mainPos) {
        // 重新校准摇杆，使TDC保持在解锁前的位置
        const expectedPos = tdcToJoystick(lastLockedPosition);
        const newOffset = {
          x: Math.max(-1, Math.min(1, expectedPos.x - mainPos.x)),
          y: Math.max(-1, Math.min(1, expectedPos.y - mainPos.y))
        };
        
        setCalibrationOffset(newOffset);
        setExpectedJoystickPos(expectedPos);
        console.log('[目标解锁] 重新校准摇杆，偏移量:', newOffset);
      }
    }
  }, [radarStore.lockedTargetId, lockedTdcPosition, joystickEnabled, mainPos, tdcToJoystick]);
  
  // 监听天线高度变化，当通过其他方式改变天线高度时同步更新期望副轴位置
  React.useEffect(() => {
    if (joystickEnabled && lockedAntennaElevation === null && subY !== undefined) {
      const newExpectedSubY = antennaElevationToSubY(radarStore.currentAntennaElevation);
      if (Math.abs(newExpectedSubY - expectedSubY) > 0.01) {
        setExpectedSubY(newExpectedSubY);
        console.log('[天线高度摇杆控制] 同步期望副轴位置:', newExpectedSubY);
      }
    }
  }, [joystickEnabled, radarStore.currentAntennaElevation, expectedSubY, antennaElevationToSubY, lockedAntennaElevation, subY]);

  // 当TDC位置通过其他方式改变时，同步更新期望摇杆位置
  React.useEffect(() => {
    if (joystickEnabled && !lockedTdcPosition) { // 只有在TDC位置未锁定时才同步
      const newExpectedPos = tdcToJoystick(tdcPosition);
      if (Math.abs(newExpectedPos.x - expectedJoystickPos.x) > 0.01 || 
          Math.abs(newExpectedPos.y - expectedJoystickPos.y) > 0.01) {
        setExpectedJoystickPos(newExpectedPos);
        console.log('[TDC摇杆控制] 同步期望摇杆位置:', newExpectedPos);
      }
    }
  }, [joystickEnabled, tdcPosition, expectedJoystickPos, tdcToJoystick, lockedTdcPosition]);
  
  // 添加useEffect来监控radarData的变化并更新本地状态
  React.useEffect(() => {
    if (radarData) {
      setRadarAzimuth(radarData.radar_azimuth);
      setOwnHeading(radarData.own_heading);
    }
  }, [radarData]);
  
  // 组件卸载时清理摇杆控制状态
  React.useEffect(() => {
    return () => {
      if (joystickEnabled) {
        console.log('[摇杆控制] 组件卸载，清理状态');
        setCalibrationOffset({x: 0, y: 0});
        setExpectedJoystickPos({x: 0, y: 0});
        setLockedTdcPosition(null);
        setLockedAntennaElevation(null);
        setAntennaElevationCalibrationOffset(0);
        setExpectedSubY(0);
      }
    };
  }, [joystickEnabled]);
  
  // 直接检查并处理targets
  React.useEffect(() => {

    if (radarData?.externalTargets) {
      console.log('RadarDisplay - externalTargets已更新:', radarData.externalTargets);
      if(radarData.externalTargets.length > 0) {
        console.log('RadarDisplay - externalTargets已更新:', radarData.externalTargets, agentStore.isAIActive);
        if(agentStore.isAIActive) {
          audioManager.play('radarAISelect');
        }
      }
    } else {
      console.log('【RadarDisplay调试】externalTargets 为空或未定义');
    }
  }, [radarData?.externalTargets, centerX, centerY]);
  
  // 从本地状态获取externalTargets并处理坐标
  const processedExternalTargets = React.useMemo(() => {
    if (!radarData?.externalTargets) {
      return undefined;
    }
    
    // --- 坐标系转换逻辑 ---
    // 1. 定义屏幕坐标系的原点 (O)，即雷达的底边中点，代表自己的位置。
    const originX = (framePositions.startX + framePositions.endX) / 2;
    const originY = framePositions.endY;

    // 2. 计算距离的比例尺：每海里(nm)对应多少屏幕像素(px)。
    // 这是通过用雷达显示区域的像素高度除以当前的最大量程(range)得到的。
    const pixelsPerNm = radarConfig.mainBoxHeight / range;

    // 3. 遍历从服务器收到的所有目标，将其极坐标转换为屏幕的笛卡尔坐标。
    return radarData.externalTargets.map(target => {
      // 从目标数据中获取角度 (azimuth) 和距离 (distance)。
      const angleDegrees = target.position.x; // X 代表角度
      const distanceNm = target.position.y;   // Y 代表距离（海里）

      // 步骤 A: 将角度从度(degrees)转换为弧度(radians)，因为三角函数需要使用弧度。
      const angleRadians = angleDegrees * (Math.PI / 180);

      // 步骤 B: 将距离从海里(nm)转换为屏幕像素(px)。
      const distancePixels = distanceNm * pixelsPerNm;

      // 步骤 C: 使用三角函数计算目标相对于原点(O)的X和Y方向的像素偏移量。
      // 标准极坐标中0度朝右，因此 x = r * cos(θ), y = r * sin(θ)。
      // 在我们的雷达中，0度朝上，因此我们需要进行调整：
      // - X方向的偏移量由 sin(θ) 决定。
      // - Y方向的偏移量由 cos(θ) 决定。
      const offsetX = distancePixels * Math.sin(angleRadians);
      // Y轴需要取反，因为在屏幕坐标系中，Y值向下增加，而我们希望目标向上移动。
      const offsetY = -distancePixels * Math.cos(angleRadians); 

      // 步骤 D: 计算出目标在屏幕上的最终绝对坐标。
      const screenX = originX + offsetX;
      const screenY = originY + offsetY;

      // 返回包含最终屏幕坐标的新目标对象。
      // 明确返回值的类型为 RadarTarget，以保留所有原始字段
      return {
      ...target,
      distance_nm: distanceNm, // 保留原始距离（海里）
      position: {
          x: screenX,
          y: screenY
        }
      } as RadarTarget;
    });
  }, [radarData?.externalTargets, framePositions, range, radarConfig]);
  
  // Effect to update the store with the latest target positions
  useEffect(() => {
    if (processedExternalTargets) {
      const positionsMap = new Map<string, { x: number; y: number }>();
      processedExternalTargets.forEach(target => {
        positionsMap.set(target.id, target.position);
      });
      radarStore.setTargetDisplayPositions(positionsMap);
    } else {
      // If there are no targets, clear the map in the store
      radarStore.setTargetDisplayPositions(new Map());
    }
  }, [processedExternalTargets]);
  
  // 计算目标的距离和航向信息的通用函数
  const calculateTargetInfo = useCallback((target: RadarTarget) => {
    // 计算距离（海里）
    // 后端的target.position实际上是极坐标：x=角度，y=距离（海里）
    // 所以距离可以直接从y值获取，无需复杂的像素转换
    const distanceNm = Math.abs(target.position.y); // 使用绝对值确保距离为正
    
    // 使用后端预处理的导航坐标系角度
    // 后端已经将数学坐标系转换为导航坐标系角度（0°=北, 90°=东, 180°=南, 270°=西）
    const directionDegrees = target.direction_degrees;
    
    // 直接使用后端计算的威胁评分，确保完全一致
    const threatScore = target.threat_score;
    
    return {
      distance: distanceNm,
      direction: directionDegrees,
      threatScore: threatScore
    };
  }, [framePositions, radarConfig, range]);

  // 处理IFF模式下的目标点击
  const handleTargetClickInIFF = useCallback((target: RadarTarget) => {
    if (!iffMode) return;
    
    const targetInfo = calculateTargetInfo(target);
    
    // 添加目标详细信息到日志
    if (onAddMessage) {
      onAddMessage('info', '=== IFF模式目标信息 ===');
      onAddMessage('info', `目标ID: ${target.id}`);
      onAddMessage('info', `目标类型: ${target.type === 'army' ? '敌机' : '友机'}`);
      onAddMessage('info', `距离: ${targetInfo.distance.toFixed(2)} 海里`);
        onAddMessage('info', `屏幕坐标: (${target.position.x.toFixed(1)}, ${target.position.y.toFixed(1)})`);
        if (target.speed !== undefined) {
          onAddMessage('info', `速度: ${target.speed}`);
        }
              if (targetInfo.direction !== undefined) {
        onAddMessage('info', `运动方向: ${targetInfo.direction.toFixed(1)}°`);
      }
      if (targetInfo.threatScore !== undefined) {
        onAddMessage('info', `威胁评分: ${targetInfo.threatScore.toFixed(3)} (0°最小威胁，180°最大威胁)`);
      }
      onAddMessage('info', '======================');
    }
    
    console.log(`[IFF模式] 点击目标 ${target.id}:`, targetInfo);
  }, [iffMode, calculateTargetInfo, onAddMessage]);

  // 处理按下Enter键时的TDC和目标选择逻辑
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape' && onTargetSelect) {
      // 处理Escape键，解锁目标
      console.log('RadarDisplay - Escape键被按下，解锁目标');
      onTargetSelect({ targetId: undefined, lockX: undefined });
      return;
    }
    
    if (e.key === 'Enter' && processedExternalTargets && onTargetSelect) {
      // 使用实际的TDC位置（可能是摇杆控制的位置）
      const currentTdcPos = joystickEnabled ? calculatedTdcPosition : tdcPosition;
      console.log('RadarDisplay - Enter键被按下，TDC位置:', currentTdcPos);
      
      // 计算TDC的X偏移量
      if (onTDCPositionSet) {
        const offset = currentTdcPos.x - centerX;
        onTDCPositionSet(offset);
        console.log(`TDC位置已设置，偏移量: ${offset}px`);
      }
      
      // 查找与TDC位置接近的目标
      let closestTarget: RadarTarget | undefined;
      let minDistance = 30; // 设置一个阈值，只有距离小于这个值的目标才会被选中
      
      // ✅ 修复：使用RadarStore中的实际显示位置进行距离计算
      processedExternalTargets.forEach(target => {
        // 获取目标的实际显示位置（包含动画偏移）
        const actualPosition = radarStore.targetDisplayPositions.get(target.id);
        const targetPos = actualPosition || target.position; // 如果没有实际位置，使用原始位置作为备选
        
        const distance = Math.sqrt(
          Math.pow(targetPos.x - currentTdcPos.x, 2) + 
          Math.pow(targetPos.y - currentTdcPos.y, 2)
        );
        
        if (distance < minDistance) {
          minDistance = distance;
          closestTarget = target;
        }
        console.log(`[锁定检测] 目标 ${target.id}: 计算位置(${target.position.x.toFixed(1)}, ${target.position.y.toFixed(1)}) vs 实际位置(${targetPos.x.toFixed(1)}, ${targetPos.y.toFixed(1)}) 距离TDC: ${distance.toFixed(1)}px`);
      });
      
      if (closestTarget) {
        console.log('找到最近的目标:', closestTarget.id, '距离:', minDistance);
        onTargetSelect({
          targetId: closestTarget.id,
          lockX: currentTdcPos.x,
          iffMode: iffMode,
          externalTargetsTimestamp: radarData?.externalTargetsTimestamp
        });
      } else {
        console.log('没有找到靠近TDC的目标');
        onTargetSelect({ targetId: undefined });
      }
    }

  }, [tdcPosition, processedExternalTargets, centerX, onTDCPositionSet, onTargetSelect, iffMode, radarData?.externalTargetsTimestamp, radarStore.targetDisplayPositions, joystickEnabled, calculatedTdcPosition]);

  // 处理确认弹窗的确认操作
  const handleConfirmYes = useCallback(() => {
    // 先清空日志
    if (onClearMessages) {
      onClearMessages();
    }
    
    // 然后重置任务
    if (onResetForNextMission) {
      onResetForNextMission();
    }
    setShowMissionConfirm(false);
  }, [onClearMessages, onResetForNextMission]);

  // 处理button7的位置锁定/解锁逻辑（长按按钮 - 下降沿检测）
  React.useEffect(() => {
    // 检测button7从true变为false的瞬间（按钮松开）
    if (!button7 && previousButton7Ref.current && joystickEnabled) {
      const currentTime = Date.now();
      
      // 防抖处理：如果距离上次触发时间太短，则忽略这次触发
      if (currentTime - lastButton7TriggerTime.current < button7DebounceDelay) {
        console.log('[位置锁定] Button7触发被防抖过滤');
        previousButton7Ref.current = button7;
        return;
      }
      
      lastButton7TriggerTime.current = currentTime;
      
      // 优先检查是否有弹窗显示，如果有则触发确认
      if (showMissionConfirm) {
        console.log('[Button7] 任务弹窗显示中，触发确认');
        handleConfirmYes();
        previousButton7Ref.current = button7;
        return;
      }
      
      if (lockedTdcPosition || lockedAntennaElevation !== null) {
        // TDC位置或天线高度已锁定，触发解锁功能
        console.log('[Button7] 位置已锁定，触发解锁');
        
        // 保存当前锁定的位置和天线高度
        const lastLockedPosition = lockedTdcPosition;
        const lastLockedElevation = lockedAntennaElevation;
        
        // 解锁TDC位置和天线高度
        setLockedTdcPosition(null);
        setLockedAntennaElevation(null);
        
        // 同时解锁目标（如果有锁定的目标）
        if (radarStore.lockedTargetId) {
          const keyEvent = new KeyboardEvent('keydown', { key: 'Escape' });
          handleKeyDown(keyEvent);
        }
        
        // 重新校准摇杆（主轴）
        if (mainPos && lastLockedPosition) {
          const expectedPos = tdcToJoystick(lastLockedPosition);
          const newOffset = {
            x: Math.max(-1, Math.min(1, expectedPos.x - mainPos.x)),
            y: Math.max(-1, Math.min(1, expectedPos.y - mainPos.y))
          };
          
          setCalibrationOffset(newOffset);
          setExpectedJoystickPos(expectedPos);
          console.log('[Button7] 解锁后重新校准摇杆主轴');
          console.log('[Button7] 解锁前TDC位置:', lastLockedPosition);
          console.log('[Button7] 期望摇杆位置:', expectedPos);
          console.log('[Button7] 当前摇杆位置:', mainPos);
          console.log('[Button7] 校准偏移量:', newOffset);
        }
        
        // 重新校准摇杆（副轴）
        if (subY !== undefined && lastLockedElevation !== null) {
          const expectedSubY = antennaElevationToSubY(lastLockedElevation);
          const newAntennaOffset = Math.max(-1, Math.min(1, expectedSubY - subY));
          
          setAntennaElevationCalibrationOffset(newAntennaOffset);
          setExpectedSubY(expectedSubY);
          console.log('[Button7] 解锁后重新校准摇杆副轴');
          console.log('[Button7] 解锁前天线高度:', lastLockedElevation);
          console.log('[Button7] 期望副轴位置:', expectedSubY);
          console.log('[Button7] 当前副轴位置:', subY);
          console.log('[Button7] 校准偏移量:', newAntennaOffset);
        }
        
        console.log('[Button7] TDC位置和天线高度已解锁，恢复摇杆控制');
      } else {
        // TDC位置和天线高度未锁定，触发锁定功能
        console.log('[Button7] 位置未锁定，触发锁定');
        
        // 锁定当前TDC位置
        let currentTdcPos = tdcPosition;
        
        if (joystickEnabled) {
          // 使用摇杆控制的TDC位置
          const calibratedJoystickPos = getCalibratedJoystickPos();
          currentTdcPos = joystickToTdc(calibratedJoystickPos);
        }
        
        setLockedTdcPosition(currentTdcPos);
        console.log('[Button7] TDC位置已锁定:', currentTdcPos);
        
        // 锁定当前天线高度
        const currentElevation = calculatedAntennaElevation;
        setLockedAntennaElevation(currentElevation);
        console.log('[Button7] 天线高度已锁定:', currentElevation);
        
        // 尝试锁定目标（如果TDC位置附近有目标）
        const keyEvent = new KeyboardEvent('keydown', { key: 'Enter' });
        handleKeyDown(keyEvent);
      }
    }
    previousButton7Ref.current = button7;
  }, [button7, joystickEnabled, handleKeyDown, lockedTdcPosition, lockedAntennaElevation, tdcPosition, getCalibratedJoystickPos, joystickToTdc, mainPos, tdcToJoystick, radarStore.lockedTargetId, subY, antennaElevationToSubY, calculatedAntennaElevation, showMissionConfirm, handleConfirmYes]);
  
  // 处理IFF按钮点击，现在用于弹出确认框
  const handleIffButtonClick = () => {
    if (lockedTargetObject) {
      const targetInfo = calculateTargetInfo(lockedTargetObject);
      
      // 添加目标详细信息到日志
      if (onAddMessage) {
        onAddMessage('info', '=== 目标识别结果详情 ===');
        onAddMessage('info', `目标ID: ${lockedTargetObject.id}`);
        onAddMessage('info', `目标类型: ${lockedTargetObject.type === 'army' ? '敌机' : '友机'}`);
        onAddMessage('info', `距离: ${targetInfo.distance.toFixed(2)} 海里`);
        onAddMessage('info', `屏幕坐标: (${lockedTargetObject.position.x.toFixed(1)}, ${lockedTargetObject.position.y.toFixed(1)})`);
        if (lockedTargetObject.speed !== undefined) {
          onAddMessage('info', `速度: ${lockedTargetObject.speed}`);
        }
        if (targetInfo.direction !== undefined) {
          onAddMessage('info', `运动方向: ${targetInfo.direction.toFixed(1)}°`);
        }
        if (targetInfo.threatScore !== undefined) {
          onAddMessage('info', `威胁评分: ${targetInfo.threatScore.toFixed(3)} (0°最小威胁，180°最大威胁)`);
        }
      
        
      }
    
      // 添加重复次数信息
      const radarRepetitionInfo = repetitionInfos['RADAR_TARGETING'];
      if (radarRepetitionInfo && typeof radarRepetitionInfo !== 'string') {
        // onAddMessage('info', `重复进度: ${formatRepetitionText(radarRepetitionInfo)}`);
        
        // 判断是否需要显示难度变化弹窗
        const shouldShowDifficultyChangeModal = (radarRepetitionInfo as any).will_difficulty_change && !agentStore.isAIActive && isLastRepetition(radarRepetitionInfo);
        
        if (shouldShowDifficultyChangeModal) {
          setShowDifficultyChangeModal(true);
        } else if (isLastRepetition(radarRepetitionInfo) && agentStore.isAIActive) {
          setShowScenarioCompletionModal(true);
          // onAddMessage('info', '⚠️ 这是人机模式下当前场景的最后一次任务，请联系主试');
        } else {
          setShowMissionConfirm(true);
        }
      }
      
      // 'army' is considered the correct type for this task (enemy)
      if (lockedTargetObject.type === 'army') {
        setMissionResultMessage('结果: 正确');
      } else {
        setMissionResultMessage('结果: 错误');
      }
    } else {
      setMissionResultMessage('结果: 未锁定目标');
      setShowMissionConfirm(true);
    }
    setIffMode(prev => !prev);
  };

  
  // 监听自动激活IFF事件
  React.useEffect(() => {
    const handleResetIFF = () => {
      console.log('RadarDisplay - 收到重置IFF事件');
      setIffMode(false);
      console.log('RadarDisplay - IFF模式已重置');
    };

    window.addEventListener('resetIFF', handleResetIFF);
    
    return () => {
      window.removeEventListener('resetIFF', handleResetIFF);
    };
  }, []);

  // 监听摇杆双按钮IFF触发事件
  React.useEffect(() => {
    const handleJoystickIFFTrigger = () => {
      console.log('RadarDisplay - 收到摇杆IFF触发事件');
      handleIffButtonClick();
    };

    window.addEventListener('joystickIFFTrigger', handleJoystickIFFTrigger);
    
    return () => {
      window.removeEventListener('joystickIFFTrigger', handleJoystickIFFTrigger);
    };
  }, []);
  
  // 自定义渲染函数，添加IFF按钮的点击事件
  const renderCustomText = (props: any) => {
    const originalElements = renderText({
      ...props,
      displayMode, // 传递当前显示模式
      isSilent     // 传递静默状态
    });
    
    // 为IFF文本元素添加点击处理
    return React.cloneElement(originalElements, {}, [
      ...React.Children.toArray(originalElements.props.children),
      // 额外添加IFF按钮点击区域（透明覆盖层）
      <Group key="iff-click-area" x={props.framePositions.startX + 290} y={props.framePositions.startY - 40}>
        <Line
          points={[-5, -5, 30, -5, 30, 20, -5, 20, -5, -5]}
          fill={iffMode ? 'rgba(0, 255, 0, 0.2)' : 'rgba(255, 0, 0, 0.2)'}
          closed={true}
          onClick={handleIffButtonClick}
          onTap={handleIffButtonClick}
        />
      </Group>
    ]);
  };
  
  // 添加和移除键盘事件监听器
  React.useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleKeyDown]);
  
  // 添加扫描计数状态
  const [scanCount, setScanCount] = useState(0);
  
  // 处理扫描完成一次循环
  const handleScanCycleComplete = useCallback(() => {
    setScanCount((prevCount) => (prevCount + 1) % (maxScanCount || 4));
    
    // 根据当前显示模式更新HI/MED切换
    if (displayMode === 'AUTO') {
      // 在AUTO模式下，每次扫描循环后切换HI/MED显示
      setHiMedToggle(prev => prev === 'HI' ? 'MED' : 'HI');
      // console.log(`AUTO模式: 切换到 ${hiMedToggle === 'HI' ? 'MED' : 'HI'}`);
    }
    // 在HI或MED模式下，hiMedToggle保持不变
    
    // console.log("扫描完成一次循环，更新计数");
  }, [maxScanCount, displayMode]);
  
  // 创建scanLineRef
  const scanLineRef = React.useRef<{ scanCount: number } | null>(null);
  
  // 创建scanLineProps
  const scanLineProps = {
    azimuth: radarData?.radar_azimuth,
    radarConfig,
    framePositions,
    scanMode,
    scanControl,
    // onScanCycleComplete,
    isStarted,
    scanCount: scanLineRef.current?.scanCount
  };
  
  // 创建rendererProps
  const rendererProps = {
            width,
            height,
            radarConfig,
            framePositions,
            tdcPosition: joystickEnabled ? calculatedTdcPosition : tdcPosition, // 使用摇杆控制的位置或原始位置
            scanAngle: scanMode.scanAngle,
            centerOffset: scanMode.centerOffset,
            onTDCPositionSet,
            range,
            scanCount,
            maxScanCount,
    displayMode,
    hiMedToggle,
    isSilent,
    isStarted,
    sendMessage,
    heading: radarData?.own_heading,
    joystickEnabled, // 添加摇杆控制状态
  };
  
  // Find the locked target object from the list
  const lockedTargetObject = useMemo(() => {
    if (radarStore.lockedTargetId && processedExternalTargets) {
      return processedExternalTargets.find(t => t.id === radarStore.lockedTargetId);
    }
    return undefined;
  }, [radarStore.lockedTargetId, processedExternalTargets]);
  
  // 新增：创建一个符合LiveTarget props要求的对象
  const liveTargetForRender = useMemo(() => {
    if (!lockedTargetObject) {
      return null;
    }
    // 将 RadarTarget 转换为 LiveTarget 需要的格式
    // 并为可选属性提供默认值
    return {
      ...lockedTargetObject,
      x: lockedTargetObject.position.x,
      y: lockedTargetObject.position.y,
      quality: lockedTargetObject.quality ?? 0.8,
      threat_level: lockedTargetObject.threat_level ?? 0,
      relative_heading: lockedTargetObject.relative_heading ?? 0,
    };
  }, [lockedTargetObject]);
  
  return (
    <div style={{ position: 'relative', width, height }}>
      
      摇杆控制状态指示器
      {joystickEnabled && (
        <div style={{
          position: 'absolute',
          top: '10px',
          right: '10px',
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          color: (lockedTdcPosition || lockedAntennaElevation !== null) ? '#FF6600' : '#00FF00',
          padding: '8px 12px',
          borderRadius: '4px',
          fontSize: '12px',
          fontFamily: 'monospace',
          border: `1px solid ${(lockedTdcPosition || lockedAntennaElevation !== null) ? '#FF6600' : '#00FF00'}`,
          zIndex: 1000,
          whiteSpace: 'pre-line'
        }}>
          {`摇杆控制: ${(lockedTdcPosition || lockedAntennaElevation !== null) ? '位置锁定' : '启用'}
B1: ${button1 ? '按下' : '释放'} (范围) | B2: ${button2 ? '按下' : '释放'} (角度) | B7: ${button7 ? '按下' : '释放'} (锁定)`}
        </div>
      )}
      

      
      <Stage width={width} height={height}>
        <Layer>
          {/* 雷达主框架和文本 */}
          {renderMainFrame({ ...rendererProps, scanAngle: scanMode.scanAngle, scanCount })}
          
          {/* 渲染文本信息 */}
          {renderText({ ...rendererProps, heading: radarData?.own_heading, range, scanAngle: scanMode.scanAngle })}
          
          {/* 扫描线 */}
          {radarData && !isSilent && isStarted && (
            <ScanLine 
              azimuth={radarData.radar_azimuth} 
              radarConfig={radarConfig} 
              framePositions={framePositions} 
              scanMode={scanMode}
              scanControl={scanControl}
              onScanCycleComplete={handleScanCycleComplete}
              isStarted={isStarted}
            />
          )}
          
         
          
          {/* 渲染未知目标 - 使用UnknownTargetManager */}
          {showUnknownTargets && processedExternalTargets && (
            <UnknownTargetManager
              showTargets={!isSilent}
              color={radarConfig.recColor}
              externalTargets={processedExternalTargets}
              selectedTargetId={radarStore.lockedTargetId}
              verticalLineX={radarStore.lockScreenX}
              framePositions={framePositions}
              iffMode={iffMode}
              scanAngle={scanMode.scanAngle}
              onTargetClick={handleTargetClickInIFF}
              cognitiveLoad={cognitiveLoad}
              range={range}
            />
          )}
          
          {/* 速度矢量HUD */}
          {showVectorHUD && (
            <>
              <VelocityVector
                x={framePositions.startX + radarConfig.mainBoxWidth * 0.3}
                y={framePositions.startY + radarConfig.mainBoxHeight * 0.4}
                color={radarConfig.gridColor}
              />
              <HorizonHUD
                x={framePositions.startX + radarConfig.mainBoxWidth * 0.3}
                y={framePositions.startY + radarConfig.mainBoxHeight * 0.4 - 10}
                color={radarConfig.gridColor}
              />
            </>
          )}
          
          {/* IFF模式指示器 */}
          {renderCustomText({ 
            width, 
            height, 
            radarConfig, 
            framePositions,
            // 传递实时数据中的航向信息
            heading: radarData?.own_heading,
            // 传递当前扫描角度
            scanAngle: scanMode.scanAngle,
            // 传递当前范围值
            range: range,
            // 传递静默状态
            isSilent: isSilent,
            // 传递系统启动状态
            isStarted: isStarted
          })}
        </Layer>
      </Stage>
      
      {/* 任务确认弹窗 */}
      {showMissionConfirm && (
        <div style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            // backgroundColor: 'rgba(0, 0, 0, 0.7)',
            display: 'flex',
            justifyContent: 'flex-end',
            alignItems: 'center',
            zIndex: 100,
            paddingRight: '60px',
            marginLeft: '200px'
        }}>
          <div style={{
              backgroundColor: 'black',
              padding: '24px',
              border: '2px solid #00ff00',
              borderRadius: '8px',
              textAlign: 'center',
              boxShadow: '0 0 15px rgba(0, 255, 0, 0.5)',
              color: '#00ff00',
              fontFamily: '"Courier New", Courier, monospace',
          }}>
            <p style={{
              margin: '0 0 10px 0',
              fontSize: '1.2em',
              fontWeight: 'bold',
              color: missionResultMessage === '结果: 正确' ? '#00cc00' : missionResultMessage === '结果: 错误' ? '#ff4444' : '#ffffff'
            }}>
              {missionResultMessage}
            </p>
            <h3 style={{ margin: 0, fontSize: '1.2em' }}>{lockedTargetObject?.type ? '进行下一次任务' : '重新进行本次任务'}</h3>
            <div style={{ marginTop: '20px' }}>
           
              <button 
                onClick={handleConfirmYes}
                style={{
                  backgroundColor: '#003300',
                  border: '1px solid #00ff00',
                  color: '#00ff00',
                  padding: '8px 16px',
                  margin: '0 10px',
                  cursor: 'pointer',
                  borderRadius: '4px'
                }}
              >
                确定
              </button>
          
            </div>
          </div>
        </div>
      )}
       <ScenarioCompletionModal 
        isOpen={showScenarioCompletionModal}
        onClose={() => {setShowScenarioCompletionModal(false); setShowMissionConfirm(true);}}
      />
      <DifficultyChangeModal 
        isOpen={showDifficultyChangeModal} 
        onClose={() => {setShowDifficultyChangeModal(false); setShowMissionConfirm(true);}} 
      />

      {/* Non-Konva components are here, positioned over the canvas */}
      {!connected && (
        <ConnectionStatus
          connected={false}
          error={error}
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            zIndex: 10
          }}
        />
      )}
    </div>
  );
});

export default RadarDisplay; 