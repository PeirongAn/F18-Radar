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
  onClearMessages
}) => {
  // 使用钩子获取实时雷达数据以及发送消息的函数
  // const { connected, radarData, error } = useRadarData(wsUrl);
  
  // 获取重复信息
  const { repetitionInfos } = useRadarData();

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
  
  
  // 添加useEffect来监控radarData的变化并更新本地状态
  React.useEffect(() => {
    if (radarData) {
      setRadarAzimuth(radarData.radar_azimuth);
      setOwnHeading(radarData.own_heading);
    }
  }, [radarData]);
  
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
    if (e.key === 'Enter' && processedExternalTargets && onTargetSelect) {
      console.log('RadarDisplay - Enter键被按下，TDC位置:', tdcPosition);
      
      // 计算TDC的X偏移量
      if (onTDCPositionSet) {
        const offset = tdcPosition.x - centerX;
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
          Math.pow(targetPos.x - tdcPosition.x, 2) + 
          Math.pow(targetPos.y - tdcPosition.y, 2)
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
          lockX: tdcPosition.x,
          iffMode: iffMode,
          externalTargetsTimestamp: radarData?.externalTargetsTimestamp
        });
      } else {
        console.log('没有找到靠近TDC的目标');
        onTargetSelect({ targetId: undefined });
      }
    }

  }, [tdcPosition, processedExternalTargets, centerX, onTDCPositionSet, onTargetSelect, iffMode, radarData?.externalTargetsTimestamp, radarStore.targetDisplayPositions]);
  
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
        const shouldShowDifficultyChangeModal = (radarRepetitionInfo as any).will_difficulty_change && !agentStore.isAIActive && radarRepetitionInfo.current === radarRepetitionInfo.total;
        
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
  
  const handleConfirmYes = () => {
    // 先清空日志
    if (onClearMessages) {
      onClearMessages();
    }
    
    // 然后重置任务
    if (onResetForNextMission) {
      onResetForNextMission();
    }
    setShowMissionConfirm(false);
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
            tdcPosition,
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