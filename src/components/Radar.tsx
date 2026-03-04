import React, { useState, useEffect, useRef, useCallback } from 'react';
import RadarButtons from './RadarButtons';
import RadarDisplay, { ScanModeType, ScanControlParams } from './RadarDisplay';
import AntennaElevationMarker from './AntennaElevationMarker'; // Import AntennaElevationMarker
import { useKeyboardControl } from '../hooks/useKeyboardControl';
import useRadarData from '../hooks/useRadarData';
import useExternalTDCControl, { CoordinateConfig, TDCCoordinateMessage, TDCPosition } from '../hooks/useExternalTDCControl';
import { observer } from 'mobx-react-lite';
import { useStore } from '../stores/StoreProvider';
import agentStore from '../stores/AgentStore'; // Import AgentStore directly
import radarStore from '../stores/RadarStore';
import toast from 'react-hot-toast';

// 雷达范围值数组
const RADAR_RANGES = [10, 20, 40, 80];

// 定义传递给App.tsx中onTargetSelect回调的参数类型
interface TargetSelectParams {
  targetId: string | undefined;
  lockX?: number;
  iffMode?: boolean; // AI可能不直接处理IFF模式，但类型需匹配
  externalTargetsTimestamp?: number | null; // AI获取数据的方式不同，可能为null
  event_owner?: 'AI' | 'manual';
}

export interface RadarProps {
  width?: number;
  height?: number;
  onTargetSelect?: (params: TargetSelectParams) => void; // 更新类型
  isStarted?: boolean; // 添加系统是否已启动的属性
  onRadarParamsUpdate?: (range: number, scanAngle: number) => void; // 添加参数更新回调
  onAddMessage?: (type: import('./CommunicationLog').MessageType, content: string) => void; // 添加日志记录功能
  onClearMessages?: () => void; // 添加清空日志功能
}

const Radar: React.FC<RadarProps> = (({
  width = 600,
  height = 600,
  onTargetSelect,
  isStarted = false, // 默认为未启动状态
  onRadarParamsUpdate,
  onAddMessage,
  onClearMessages,
}) => {
  // 使用自定义hook获取WebSocket连接和发送消息的函数
  const { 
    sendMessage, 
    resetTargets, 
    clearAndResetView,

    clearInitSettings,
    resetAntennaAdjustment,
    initializeSystem, 
    taskId,
    submitSettings,
    antennaAdjustmentRequired,
    targetAntennaElevation, // Ensure this is destructured
    radarData, 
    initSettings, 
    confirmAntennaAdjustmentHandled, // Destructure the new function
    connected,
    error,
  } = useRadarData();
  
  // 使用MobX Store
  const { radarStore } = useStore();

  const resetIffRef = useRef<() => void>(() => {});
  
  const [missionSettingsReady, setMissionSettingsReady] = useState(false);
  const [missionAntennaReady, setMissionAntennaReady] = useState(false);

  // 定义扫描模式状态
  const [scanMode, setScanMode] = useState<ScanModeType>({
    name: 'normal',
    scanAngle: 30,
    scanFraction: 1.0,
    centerOffset: 0 // 设置扫描中心偏移量，0表示居中
  });

  // 添加显示控制状态
  const [showVectorHUD, setShowVectorHUD] = useState(false);
  
  // 添加未知目标显示控制状态
  const [showUnknownTargets, setShowUnknownTargets] = useState(true);
  const [unknownTargetCount, setUnknownTargetCount] = useState(5); // 默认显示全部5个未知目标
  
  // 添加雷达范围索引状态
  const [rangeIndex, setRangeIndex] = useState(3); // 默认为20海里(索引1)
  
  // 添加BR计数状态
  const [maxScanCount, setMaxScanCount] = useState(1); // 默认BR计数上限为1
  
  // 添加显示模式状态
  const [displayMode, setDisplayMode] = useState<'AUTO' | 'HI' | 'MED'>('AUTO');
  
  // 添加雷达静默状态
  const [isSilent, setIsSilent] = useState(false);

  // 添加认知负荷等级状态：低（详细信息）、中（概要信息）、高（无额外信息）
  const [cognitiveLoad, setCognitiveLoad] = useState<'low' | 'medium' | 'high'>('low');

  // 定义扫描控制参数状态
  const [scanControl, setScanControl] = useState<ScanControlParams>({
    sinCoefficient: Math.PI/2,   // 控制正弦映射的系数
    amplitudeScale: 1.0,         // 控制扫描幅度的缩放
    useSineMapping: true,        // 是否使用正弦映射
    scanSpeed: 2.0               // 扫描速度系数
  });

  // Ref for AI target selection timeout - type changed to number for browser environment
  const aiTargetSelectionTimeoutRef = useRef<number | null>(null);
  const aiTdcMoveTimeoutRef = useRef<number | null>(null); // Ref for TDC movement timeout

  const radarConfig = {
    backgroundColor: '#000000',
    gridColor: '#ffffff',  // 白色线条
    textColor: '#00ff00',  // 绿色文本
    recColor: 'yellow',  // 黄色矩形
    padding: 4,
    mainBoxWidth: 480,
    mainBoxHeight: 480,
    buttonSize: 30,
    buttonOffset: 15
  };

  // 计算主显示区域的边界位置
  const framePositions = {
    startX: (width - radarConfig.mainBoxWidth) / 2,
    startY: (height - radarConfig.mainBoxHeight) / 2,
    endX: (width + radarConfig.mainBoxWidth) / 2,
    endY: (height + radarConfig.mainBoxHeight) / 2
  };

  // State for TDC position, managed locally in Radar.tsx
  const [tdcPosition, setTdcPosition] = useState({ x: width / 2, y: height / 2 });

  // 外部控制状态
  const [hasRecentWebSocketControl, setHasRecentWebSocketControl] = useState(false);

  // 外部TDC控制配置
  const coordinateConfig: CoordinateConfig = React.useMemo(() => ({
    frameStartX: framePositions.startX,
    frameStartY: framePositions.startY,
    radarWidth: radarConfig.mainBoxWidth,
    radarHeight: radarConfig.mainBoxHeight,
    padding: radarConfig.padding
  }), [framePositions.startX, framePositions.startY, radarConfig.mainBoxWidth, radarConfig.mainBoxHeight, radarConfig.padding]);

  // 处理外部TDC更新
  const handleExternalTDCUpdate = useCallback((
    coordinate: TDCCoordinateMessage, 
    pixelPosition: TDCPosition
  ) => {
    console.log('[Radar] 外部TDC坐标更新:', {
      normalized: { x: coordinate.x, y: coordinate.y },
      pixel: { x: pixelPosition.x, y: pixelPosition.y },
      source: coordinate.source
    });

    setTdcPosition(pixelPosition);
    setHasRecentWebSocketControl(true);
    setTimeout(() => setHasRecentWebSocketControl(false), 2000);
  }, []);

  // 处理外部ButtonK3（触发目标锁定，模拟Enter键效果）
  const handleExternalButtonK3 = useCallback(() => {
    console.log('[Radar] 外部ButtonK3激活，模拟Enter键效果（目标锁定）');
    
    const simulatedEnterEvent = new KeyboardEvent('keydown', {
      key: 'Enter',
      code: 'Enter',
      keyCode: 13,
      which: 13,
      bubbles: true,
      cancelable: true
    });
    
    window.dispatchEvent(simulatedEnterEvent);
  }, []);

  // 使用外部TDC控制Hook
  const externalTDC = useExternalTDCControl(
    undefined,
    coordinateConfig,
    handleExternalTDCUpdate,
    handleExternalButtonK3
  );

  const handleClearAndReset = useCallback(() => {
    console.log('Clearing panel and resetting for next mission.');

   
    // Reset local state in Radar.tsx to initial values
    setScanMode({
      name: 'normal',
      scanAngle: 30,
      scanFraction: 1.0,
      centerOffset: 0,
    });
    setShowVectorHUD(false);
    setShowUnknownTargets(true);
    setRangeIndex(3); // 20nm
    setMaxScanCount(1);
    setDisplayMode('AUTO');
    setIsSilent(false);
    setTdcPosition({ x: width / 2, y: height / 2 });

    // Reset target lock
    if (onTargetSelect) {
      onTargetSelect({ targetId: undefined });
    } else {
      radarStore.setLockedTargetId(undefined);
    }
    
    // Reset IFF mode in RadarDisplay
    if (resetIffRef.current) {
      resetIffRef.current();
    }

    // Reset antenna elevation to its initial value (0) before sending it
    radarStore.setCurrentAntennaElevation(0);

    // Clear the old init settings from the hook's state
    clearInitSettings();

    // Reset the mission readiness flags
    setMissionSettingsReady(false);
    setMissionAntennaReady(false);
    
    // Reset the antenna adjustment required flag *before* initializing
    resetAntennaAdjustment();
    
    // Reset the flag for processing initial settings
    initSettingsProcessedRef.current = false;

    // Clear targets from the backend/data source
    clearAndResetView();

    // Re-initialize the system for the next mission
    console.log('Starting next mission...');
    initializeSystem(radarStore.userId, agentStore.isAIActive, radarStore.isPractice);
    
  }, [width, height, onTargetSelect, radarStore, clearAndResetView, initializeSystem, clearInitSettings, resetAntennaAdjustment]);

  // Handler for TDC key actions from useKeyboardControl
  const handleTdcKeyAction = useCallback((action: 'up' | 'down' | 'left' | 'right') => {
    // DO NOT resume data stream here. It's managed by the readiness state.
    const moveStep = 5; // Define TDC move step here or pass from somewhere
    setTdcPosition(prev => {
      const newPos = { ...prev };
      switch (action) {
        case 'up':
          newPos.y = Math.max(framePositions.startY + radarConfig.padding, prev.y - moveStep);
          break;
        case 'down':
          newPos.y = Math.min(framePositions.endY - radarConfig.padding, prev.y + moveStep);
          break;
        case 'left':
          newPos.x = Math.max(framePositions.startX + radarConfig.padding, prev.x - moveStep);
          break;
        case 'right':
          newPos.x = Math.min(framePositions.endX - radarConfig.padding, prev.x + moveStep);
          break;
      }
      return newPos;
    });
  }, [width, height, radarConfig.padding, radarConfig.mainBoxWidth, radarConfig.mainBoxHeight, framePositions]); // resumeDataStream removed from dependencies

  // 条件性启用键盘控制（当没有外部控制活跃时启用）
  const enableKeyboardControl = !hasRecentWebSocketControl && !externalTDC.isTDCControlActive(2000);

  const hybridTdcKeyAction = useCallback((action: 'up' | 'down' | 'left' | 'right') => {
    if (enableKeyboardControl) {
      console.log(`[TDC键盘] 执行${action}操作`);
      handleTdcKeyAction(action);
    } else {
      console.log(`[TDC键盘] WebSocket控制活跃，忽略${action}操作`);
    }
  }, [enableKeyboardControl, handleTdcKeyAction]);

  // Setup keyboard controls for TDC (支持混合控制)
  useKeyboardControl({
    moveStep: 5,
    boundaries: {
      minX: framePositions.startX + radarConfig.padding,
      maxX: framePositions.endX - radarConfig.padding,
      minY: framePositions.startY + radarConfig.padding,
      maxY: framePositions.endY - radarConfig.padding
    },
    controls: {
      // Define specific keys for TDC if different from Antenna or use defaults (ArrowKeys)
      // Example: up: 'w', down: 's', left: 'a', right: 'd' 
      // If not specified, useKeyboardControl defaults to arrow keys for these actions.
    },
    onKeyAction: hybridTdcKeyAction,
  });

  // Effect for AI to automatically set radar parameters based on server recommendations
  useEffect(() => {
    if (agentStore.isAIActive && isStarted && agentStore.serverAIRecommendation) {
      const recommendation = agentStore.serverAIRecommendation;
      console.log('[AI Radar] Processing server recommendation for parameters:', recommendation);

      const targetRange = recommendation.range;
      const targetScanAngle = recommendation.scanAngle;

      const currentActualRange = RADAR_RANGES[rangeIndex];
      const currentActualScanAngle = scanMode.scanAngle;

      let needsSettingsSubmission = false;

      // Check and update range
      const newRangeIndex = RADAR_RANGES.findIndex(r => r === targetRange);
      if (newRangeIndex !== -1 && rangeIndex !== newRangeIndex) {
        console.log(`[AI Radar] Adjusting range from ${currentActualRange} to ${targetRange}`);
        setRangeIndex(newRangeIndex);
        needsSettingsSubmission = true;
      }

      // Check and update scan angle/mode
      if (scanMode.scanAngle !== targetScanAngle) {
        console.log(`[AI Radar] Adjusting scan angle from ${currentActualScanAngle} to ${targetScanAngle}`);
        let newScanModeName: ScanModeType['name'] = 'normal';
        let newScanFraction = 1.0;
        if (targetScanAngle === 30) {
          newScanModeName = 'medium'; newScanFraction = 0.5;
        } else if (targetScanAngle === 15) {
          newScanModeName = 'narrow'; newScanFraction = 0.25;
        } else if (targetScanAngle !== 60) {
            console.warn(`[AI Radar] Unsupported scan angle ${targetScanAngle} recommended by server. Defaulting to 60.`);
            // Potentially set to a default like 60 if recommendation is out of expected discrete values
        }
        
        setScanMode({
          name: newScanModeName,
          scanAngle: targetScanAngle, // Use the recommended angle
          scanFraction: newScanFraction,
          centerOffset: 0 // AI usually resets offset
        });
        needsSettingsSubmission = true;
      }

      if (needsSettingsSubmission) {
        submitSettings({
          range: targetRange,       // Submit the actual recommended value
          scanAngle: targetScanAngle  // Submit the actual recommended value
        });
        console.log('[AI Radar] Parameters automatically adjusted by AI based on server recommendation and submitted.');
        
        // Important: Clear the recommendation to prevent re-triggering unless a new one arrives.
        agentStore.clearServerAIRecommendation(); 
      }
    }
  }, [
    agentStore.isAIActive, 
    isStarted, 
    agentStore.serverAIRecommendation, // Main trigger
    submitSettings,
    rangeIndex, // To compare current state
    scanMode    // To compare current state
  ]);

  const initSettingsProcessedRef = useRef(false);

  useEffect(() => {
    // If initSettings is null (e.g., after a reset), do nothing until new settings arrive.
    if (!initSettings) {
      return;
    }
    
    console.log('initSettings Check:', { 
      isAIActive: agentStore.isAIActive, 
      isStarted, 
      initSettings, 
      processed: initSettingsProcessedRef.current
    });
    if (
      agentStore.isAIActive &&
      !initSettingsProcessedRef.current &&
      isStarted &&
      initSettings &&
      typeof initSettings.range === 'number' &&
      typeof initSettings.scanAngle === 'number'
    ) {
      console.log('[Radar] Processing initSettings for auto-configuration:', initSettings);
      initSettingsProcessedRef.current = true;  // 标记为已处理

      const targetRange = initSettings.range;
      const targetScanAngle = initSettings.scanAngle;
      let needsSettingsSubmission = false;
      let paramsChangedForUI = false;

      // Update local rangeIndex if different
      const newRangeIndex = RADAR_RANGES.findIndex(r => r === targetRange);
      if (newRangeIndex !== -1 && rangeIndex !== newRangeIndex) {
        console.log(`[Radar] initSettings: Adjusting range from ${RADAR_RANGES[rangeIndex]} to ${targetRange}`);
        setRangeIndex(newRangeIndex);
        paramsChangedForUI = true;
      }

      // Update local scanMode if different
      if (scanMode.scanAngle !== targetScanAngle) {
        console.log(`[Radar] initSettings: Adjusting scan angle from ${scanMode.scanAngle} to ${targetScanAngle}`);
        let newScanModeName: ScanModeType['name'] = 'normal';
        let newScanFraction = 1.0;
        if (targetScanAngle === 30) {
          newScanModeName = 'medium'; newScanFraction = 0.5;
        } else if (targetScanAngle === 15) {
          newScanModeName = 'narrow'; newScanFraction = 0.25;
        } else if (targetScanAngle !== 60) {
            console.warn(`[Radar] initSettings: Unsupported scan angle ${targetScanAngle}. Defaulting to 60 for UI.`);
        }
        setScanMode({
          name: newScanModeName,
          scanAngle: targetScanAngle,
          scanFraction: newScanFraction,
          centerOffset: 0
        });
        paramsChangedForUI = true;
      }
      
      needsSettingsSubmission = true;

      if (needsSettingsSubmission) {
        console.log('[Radar] Submitting initSettings to backend.');
        submitSettings({
          range: targetRange,
          scanAngle: targetScanAngle,
        });
        console.log('[Radar] Initial parameters (from initSettings) processed.');
      } else if (paramsChangedForUI) {
        console.log('[Radar] initSettings: UI parameters updated, but no submission needed as values might match server expectations already or validation might handle it.');
      }

      setMissionSettingsReady(true);
    }
  }, [isStarted, initSettings, submitSettings, rangeIndex, scanMode, agentStore.isAIActive]);


  useEffect(() => {
    // This effect detects when the manual or AI adjustment is complete.
    if (antennaAdjustmentRequired && radarStore.targetAntennaElevation !== null) {
      if (radarStore.currentAntennaElevation === radarStore.targetAntennaElevation) {
        console.log('Antenna adjustment complete.');
        setMissionAntennaReady(true);
      }
    }
    // Handle the case where no adjustment is required.
    // This now relies on the server sending `adjust_antenna` or not.
    // We assume if `antennaAdjustmentRequired` is false after init, we are ready.
    // A better approach would be explicit confirmation from the server.
    // For now, if adjustment is not required from the start, we assume ready.
    if (!antennaAdjustmentRequired) {
        setMissionAntennaReady(true);
    }
  }, [
    antennaAdjustmentRequired,
    radarStore.currentAntennaElevation,
    radarStore.targetAntennaElevation
  ]);



  // 当AI被禁用时重置ref
  useEffect(() => {
    if (!agentStore.isAIActive) {
      initSettingsProcessedRef.current = false;
    }
  }, [agentStore.isAIActive]);

  // Effect for AI to automatically select a target and move TDC
  useEffect(() => {
    if (!agentStore.isAIActive || !agentStore.currentAILevelConfig || !isStarted) {
      return;
    }

    // 只在没有锁定目标时执行目标选择
    if (!radarStore.lockedTargetId && radarData?.externalTargets && radarData.externalTargets.length > 0) {
      const config = agentStore.currentAILevelConfig;
      const availableTargets = radarData.externalTargets;
      
      if (availableTargets.length > 0) {
        let targetToSelect: (typeof availableTargets)[0] | undefined;

        // 最新的、更精确的逻辑
        if (config.decision_probabilities && config.decision_probabilities.length > 0) {
          // 新增：根据数组长度生成准确率（从正确池子选择的概率）
          let accuracy = 1.0; // 默认值
          if (config.decision_probabilities.length === 1) {
            // 只有一个值，直接使用
            accuracy = config.decision_probabilities[0];
          } else if (config.decision_probabilities.length >= 2) {
            // 有两个或多个值，第一个是最小值，第二个是最大值，在范围内随机生成
            const min = config.decision_probabilities[0];
            const max = config.decision_probabilities[1];
            accuracy = parseFloat((Math.random() * (max - min) + min).toFixed(2));
          }
          const randomChoice = Math.random();

          const enemyTargets = availableTargets.filter((t: { id: string }) => t.id.startsWith('enemy'));
          const friendlyTargets = availableTargets.filter((t: { id: string }) => !t.id.startsWith('enemy'));
          console.log(`[AI Engine] Decision probabilities: ${config.decision_probabilities}, ${randomChoice}`);
          // 根据准确率，决定是从敌机池选还是友机池选
          if (randomChoice < accuracy) {
            // 决定 "准确" 选择: 从敌机池里选
            if (enemyTargets.length > 0) {
              targetToSelect = enemyTargets[Math.floor(Math.random() * enemyTargets.length)];
              console.log(`[AI Engine] Decision: ACCURATE. Choosing from enemy pool. Selected: ${targetToSelect.id}`);
            } else {
              // 敌机池是空的，只能从友机池选
              targetToSelect = friendlyTargets[Math.floor(Math.random() * friendlyTargets.length)];
              console.log(`[AI Engine] Decision: ACCURATE. Enemy pool empty, fallback to friendly pool. Selected: ${targetToSelect?.id}`);
            }
          } else {
            // 决定 "失误" 选择: 从友机池里选
            if (friendlyTargets.length > 0) {
              targetToSelect = friendlyTargets[Math.floor(Math.random() * friendlyTargets.length)];
               console.log(`[AI Engine] Decision: INACCURATE. Choosing from friendly pool. Selected: ${targetToSelect.id}`);
            } else {
              // 友机池是空的，只能从敌机池选
              targetToSelect = enemyTargets[Math.floor(Math.random() * enemyTargets.length)];
              console.log(`[AI Engine] Decision: INACCURATE. Friendly pool empty, fallback to enemy pool. Selected: ${targetToSelect?.id}`);
            }
          }
        } else {
          // 旧逻辑：如果没配置概率，则默认优先选择敌机
          const enemyTarget = availableTargets.find((target: { id:string }) => target.id.startsWith('enemy'));
          targetToSelect = enemyTarget || availableTargets[0];
          console.log(`[AI Engine] Legacy decision: Chose ${targetToSelect?.id}`);
        }

        if (!targetToSelect) {
          console.warn("[AI Engine] Could not select any target.");
          return;
        }

        const finalTargetToSelect = targetToSelect;
        const targetDisplayPosition = radarStore.targetDisplayPositions.get(finalTargetToSelect.id);
        
        // 使用tdc_select_delay_ms作为统一的延迟参数
        const actionTimeout = setTimeout(() => {
          if (!agentStore.isAIActive) return;

          // 第一步：移动TDC到目标位置
          if (targetDisplayPosition) {
            console.log(`[AI Engine] Moving TDC to target position: (${targetDisplayPosition.x}, ${targetDisplayPosition.y})`);
            setTdcPosition(targetDisplayPosition);

            // 第二步：选择目标并设置锁定线
            console.log(`[AI Engine] AI is selecting target: ${finalTargetToSelect.id}`);
            if (onTargetSelect) {
              // 计算锁定线的X坐标（使用目标的x坐标）
              const lockX = targetDisplayPosition.x;
              
              // 调用目标选择回调，传入锁定线位置
              onTargetSelect({ 
                targetId: finalTargetToSelect.id, 
                lockX: lockX,
                externalTargetsTimestamp: radarData?.externalTargetsTimestamp,
                event_owner: 'AI', // AI操作
              });

              console.log(`[AI Engine] Target locked at X: ${lockX}`);
            }
          } else {
            // 如果没有位置信息，使用屏幕中心作为默认lockX
            console.log(`[AI Engine] Selecting target without position: ${finalTargetToSelect.id}`);
            if (onTargetSelect) {
              // 使用屏幕中心的X坐标作为默认锁定线位置
              const centerX = (framePositions.startX + framePositions.endX) / 2;
              onTargetSelect({ 
                targetId: finalTargetToSelect.id,
                lockX: centerX, // 添加默认的lockX值
                externalTargetsTimestamp: radarData?.externalTargetsTimestamp,
                event_owner: 'AI', // AI操作
              });
              
              console.log(`[AI Engine] Target locked at center X: ${centerX} (fallback)`);
            }
          }
        }, config.tdc_select_delay_ms);

        return () => clearTimeout(actionTimeout);
      }
    }
  }, [
    agentStore.isAIActive,
    agentStore.currentAILevelConfig,
    radarData,
    radarStore.lockedTargetId,
    onTargetSelect,
    isStarted,
    radarStore.targetDisplayPositions
  ]);

  // useEffect for AI to automatically adjust antenna when required
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
      
      if (confirmAntennaAdjustmentHandled) {
        confirmAntennaAdjustmentHandled();
      }
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

  // 当rangeIndex或scanMode变化时发送消息到服务器
  useEffect(() => {
    // 如果雷达处于静默模式，则不进行任何操作
    if (isSilent) {
      console.log('雷达处于静默模式，不发送扫描信号');
      return;
    }
    
    // 记录当前参数
    const currentRange = RADAR_RANGES[rangeIndex];
    const currentAngle = scanMode.scanAngle;
    
    console.log('当前雷达参数已更新:', {
      rangeIndex,
      range: currentRange,
      scanAngle: currentAngle,
      scanMode: scanMode.name
    });
    
    // 通知父组件参数已更新
    if (onRadarParamsUpdate) {
      onRadarParamsUpdate(currentRange, currentAngle);
    }
  }, [rangeIndex, scanMode, isSilent, onRadarParamsUpdate]);

  // 自动设置
  useEffect(() => {
    
    if (initSettings && submitSettings) {
      console.log('自动设置', initSettings)
      const range = RADAR_RANGES[rangeIndex];
      const scanAngle = initSettings.scanAngle;
      submitSettings(
        {
          range,
          scanAngle,
        }
      );
    }

  }, [submitSettings, initSettings])

  // 添加目标选择处理函数
  const handleTargetSelection = (params: TargetSelectParams) => {
    // 直接更新radarStore中的lockedTargetId和lockScreenX
    radarStore.setLockedTargetId(params.targetId);
    radarStore.setLockScreenX(params.lockX);
    console.log(`[Radar] 目标锁定状态更新: ${params.targetId}, 锁定线X坐标: ${params.lockX}`);
    
    if (onTargetSelect) {
      // 用户手动操作
      onTargetSelect({ ...params, event_owner: 'manual' });
    }
  };

  // 处理按钮点击事件
  const handleButtonClick = (position: string, buttonIndex: number) => {
    console.log(`${position} button ${buttonIndex} clicked`);
    
    // DO NOT resume data stream here.
    
    // Add clear and reset functionality to the first left button
    if (position === 'left' && buttonIndex === 1) {
      handleClearAndReset();
      return; // Stop further processing for this button
    }
    
    // 使用MobX store中的系统状态
    const isSystemReady = radarStore.isStarted ;
    
    // 根据不同位置和按钮索引设置不同的扫描模式或控制
    if (position === 'left' && buttonIndex === 3) {
      // 左侧第3个按钮循环切换扫描角度，在15度、30度和60度之间切换
      let newScanAngle: number;
      let newScanFraction: number;
      
      // 根据当前角度确定下一个角度
      if (scanMode.scanAngle === 60) {
        newScanAngle = 15;
        newScanFraction = 0.25; // 1/4区域
      } else if (scanMode.scanAngle === 15) {
        newScanAngle = 30;
        newScanFraction = 0.5;  // 1/2区域
      } else {
        newScanAngle = 60;
        newScanFraction = 1.0;  // 全区域
      }
      
      // 设置新的扫描模式
      setScanMode({
        name: newScanAngle === 60 ? 'normal' : newScanAngle === 30 ? 'medium' : 'narrow',
        scanAngle: newScanAngle,
        scanFraction: newScanFraction,
        centerOffset: scanMode.centerOffset // 保持原有的中心偏移量
      });
       // 如果系统已准备就绪，向服务器发送雷达范围更新
      if (isStarted) {
       console.log("isStarted####", isStarted, RADAR_RANGES[rangeIndex], newScanAngle);

        submitSettings({
          range: RADAR_RANGES[rangeIndex],
          scanAngle: newScanAngle
        });
      }
      
     
    }
    // 添加左侧第2个按钮的功能，用于调整天线高度
    else if (position === 'left' && buttonIndex === 2) {
     
    }
    else if (position === 'left' && buttonIndex === 5) {
      // 左侧第5个按钮循环切换BR计数上限：1 -> 2 -> 4 -> 1
      setMaxScanCount((prev) => {
        if (prev === 1) return 2;
        if (prev === 2) return 4;
        return 1; // 如果是4或其他值，回到1
      });
      console.log("BR计数上限已更新:", maxScanCount);
      
      // 如果系统已准备就绪，向服务器发送BR计数上限更新
      if (isSystemReady && sendMessage) {
        const newValue = maxScanCount === 1 ? 2 : maxScanCount === 2 ? 4 : 1;
        sendMessage({
          type: 'scan_count_update',
          maxScanCount: newValue
        });
      }
    }
    else if (position === 'right' && buttonIndex === 1) {
      // 增加范围索引，实现循环
      const newIndex = (rangeIndex + 1) % RADAR_RANGES.length;
      setRangeIndex(newIndex);
      
      // 如果系统已准备就绪，向服务器发送雷达范围更新
      if (isStarted) {
        submitSettings({
          range: RADAR_RANGES[newIndex],
          scanAngle: scanMode.scanAngle
        });
      }
    }
    else if (position === 'right' && buttonIndex === 2) {
      // 减少范围索引，确保不小于0
      const newIndex = rangeIndex > 0 ? rangeIndex - 1 : RADAR_RANGES.length - 1;
      setRangeIndex(newIndex);
      
      // 如果系统已准备就绪，向服务器发送雷达范围更新
      if (isStarted) {
        submitSettings({
          range: RADAR_RANGES[newIndex],
          scanAngle: scanMode.scanAngle
        });
      }
    }
    else if (position === 'right' && buttonIndex === 3) {
      // 切换VelocityVector和HorizonHUD的显示状态
      setShowVectorHUD(prev => !prev);
    }
    else if (position === 'right' && buttonIndex === 4) {
      // 切换未知目标的显示状态
      setShowUnknownTargets(prev => !prev);
    }
    else if (position === 'right' && buttonIndex === 5) {
      // 切换显示模式：AUTO -> HI -> MED -> AUTO
      if (displayMode === 'AUTO') setDisplayMode('HI');
      else if (displayMode === 'HI') setDisplayMode('MED');
      else setDisplayMode('AUTO');
      console.log(`显示模式已切换为: ${displayMode === 'AUTO' ? 'HI' : displayMode === 'HI' ? 'MED' : 'AUTO'}`);
    }
    else if (position === 'right' && buttonIndex === 6) {
      // 切换雷达静默模式
      const newSilentState = !isSilent;
      setIsSilent(newSilentState);
      console.log(`雷达静默模式已${newSilentState ? '启用' : '禁用'}`);
      
      // 通知服务器雷达静默状态变化
      if (sendMessage) {
        sendMessage({
          type: 'silent_mode',
          enabled: newSilentState
        });
      }
    }
    
    // 如果系统处于初始化等待状态，且任务需要开始，通过MobX store自动启动初始化
  
    
    // 如果系统正在等待设置参数，且特定按钮被点击，通过MobX store自动提交当前设置
  
  };

  // 处理TDC位置设置
  const handleTDCPositionSet = (offset: number) => {
    // DO NOT resume data stream here. It's managed by the readiness state.
    // 更新扫描模式，设置新的中心偏移量
    setScanMode({
      ...scanMode,
      centerOffset: offset
    });
    console.log(`扫描中心已设置，偏移量: ${offset}px`);
  };

  // 添加接管按钮处理函数
  const handleTakeControl = useCallback(() => {
    console.log('用户手动接管控制');
    // 禁用AI控制
    agentStore.setAIActive(!agentStore.isAIActive);
    
    // 发送接管消息到服务器
    if (sendMessage) {
      sendMessage({
        type: 'user_take_control',
        timestamp: Date.now(),
        user_id: 'current_user' // 这里可以从props或store中获取实际用户ID
      });
    }
    
    // 可以添加一些UI反馈，比如短暂显示"已接管控制"的提示
    console.log('✅ 用户已接管雷达控制');
  }, [sendMessage]);

  // 处理摇杆button2触发的扫描角度切换功能
  const handleJoystickScanAngleSwitch = useCallback(() => {
    console.log('[摇杆控制] 执行扫描角度切换功能');
    
    // 左侧第3个按钮循环切换扫描角度，在15度、30度和60度之间切换
    let newScanAngle: number;
    let newScanFraction: number;
    
    // 根据当前角度确定下一个角度
    if (scanMode.scanAngle === 60) {
      newScanAngle = 15;
      newScanFraction = 0.25; // 1/4区域
    } else if (scanMode.scanAngle === 15) {
      newScanAngle = 30;
      newScanFraction = 0.5;  // 1/2区域
    } else {
      newScanAngle = 60;
      newScanFraction = 1.0;  // 全区域
    }
    
    // 设置新的扫描模式
    setScanMode({
      name: newScanAngle === 60 ? 'normal' : newScanAngle === 30 ? 'medium' : 'narrow',
      scanAngle: newScanAngle,
      scanFraction: newScanFraction,
      centerOffset: scanMode.centerOffset // 保持原有的中心偏移量
    });
    
    // 如果系统已准备就绪，向服务器发送雷达范围更新
    if (isStarted) {
      console.log("摇杆扫描角度切换####", isStarted, RADAR_RANGES[rangeIndex], newScanAngle);
      submitSettings({
        range: RADAR_RANGES[rangeIndex],
        scanAngle: newScanAngle
      });
    }
  }, [scanMode, isStarted, submitSettings, rangeIndex]);

  // 监听摇杆按钮自定义事件
  useEffect(() => {
    const handleJoystickScanAngleSwitchEvent = () => {
      handleJoystickScanAngleSwitch();
    };
    
    window.addEventListener('joystickScanAngleSwitch', handleJoystickScanAngleSwitchEvent);
    
    return () => {
      window.removeEventListener('joystickScanAngleSwitch', handleJoystickScanAngleSwitchEvent);
    };
  }, [handleJoystickScanAngleSwitch]);

  // 添加F10快捷键监听
  useEffect(() => {
    const handleKeyPress = (event: KeyboardEvent) => {
      if (event.key === 'F10') {
        // event.preventDefault();
        // handleTakeControl();
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => {
      window.removeEventListener('keydown', handleKeyPress);
    };
  }, [handleTakeControl]);

  // 优化系统重置功能 - 保留用户信息
  const handleReset = () => {
    console.log('====== 系统重置 (模拟页面重新载入) ======');
    
    // 保存用户名和AI选项到sessionStorage，模拟页面重新载入但保留用户信息
    if (radarStore.userId) {
      sessionStorage.setItem('preservedUserId', radarStore.userId);
      sessionStorage.setItem('preservedIncludeAI', agentStore.isAIActive.toString());
      console.log('用户信息已保存:', { 
        userId: radarStore.userId, 
        includeAI: agentStore.isAIActive 
      });
    }
    
    // 执行页面重新载入
    window.location.reload();
  };

  return (
    <div className="flex flex-col items-center justify-center relative">
      {/* 认知负荷选择按钮 */}
      <div className="flex items-center gap-2 mb-2">
        <span className="text-green-500 font-mono text-sm mr-1">认知负荷:</span>
        {([
          { key: 'low' as const, label: '低' },
          { key: 'medium' as const, label: '中' },
          { key: 'high' as const, label: '高' },
        ]).map(({ key, label }) => (
          <button
            key={key}
            className={`font-mono text-sm px-3 py-1 border rounded transition-colors ${
              cognitiveLoad === key
                ? 'bg-green-700 border-green-400 text-green-100'
                : 'bg-gray-900 border-gray-600 text-gray-400 hover:border-green-600 hover:text-green-300'
            }`}
            onClick={() => setCognitiveLoad(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {/* 控制面板 */}
      {/* 顶部按钮 */}
      <RadarButtons 
        position="top" 
        framePositions={framePositions} 
        radarConfig={radarConfig} 
        onButtonClick={handleButtonClick}
      />
      
      <div className="flex items-center justify-center">
        {/* 左侧按钮和天线指示器 */}
        <div className="flex flex-col items-center mr-2"> {/* Wrapper for left buttons */}
        <RadarButtons 
          position="left" 
          framePositions={framePositions} 
          radarConfig={radarConfig} 
          onButtonClick={handleButtonClick}
        />
        </div>
        
        {/* 雷达显示 */}
        <div className="relative">
          <RadarDisplay
            width={width}
            height={height}
            radarConfig={radarConfig}
            framePositions={framePositions}
            tdcPosition={tdcPosition}
            onTargetSelect={handleTargetSelection}
            scanMode={scanMode}
            scanControl={scanControl}
            onTDCPositionSet={handleTDCPositionSet}
            showVectorHUD={showVectorHUD}
            range={RADAR_RANGES[rangeIndex]}
            showUnknownTargets={showUnknownTargets}
            unknownTargetCount={unknownTargetCount}
            maxScanCount={maxScanCount} // 传递BR计数上限
            displayMode={displayMode} // 传递显示模式
            onModeDisplayChange={setDisplayMode} // 传递显示模式变更回调
            isSilent={isSilent} // 传递雷达静默状态
            isStarted={isStarted} // 传递系统启动状态
            sendMessage={sendMessage} // 传递发送消息函数
            connected={connected}
            radarData={radarData}
            error={error}
            onResetForNextMission={handleClearAndReset}
            resetIFF={resetIffRef}
            onAddMessage={onAddMessage}
            onClearMessages={onClearMessages}
            cognitiveLoad={cognitiveLoad}
          />
          
          {/* 接管控制按钮 - 位置更靠近操作区域， 临时隐藏 */}
          {/* {agentStore.isAIActive && (
            <button 
              className="absolute bg-orange-600 hover:bg-orange-700 text-white font-bold py-2 px-4 rounded shadow-lg transition-colors duration-200"
              style={{
                top: '10px',
                right: '10px',
                zIndex: 100
              }}
              onClick={handleTakeControl}
              title="按F10或点击此按钮接管控制"
            >
              接管控制 (F10)
            </button>
          )} */}
        </div>
        
        {/* 右侧按钮 */}
        <RadarButtons 
          position="right" 
          framePositions={framePositions} 
          radarConfig={radarConfig} 
          onButtonClick={handleButtonClick}
        />
      </div>
      
      {/* 底部按钮 */}
      <RadarButtons 
        position="bottom" 
        framePositions={framePositions} 
        radarConfig={radarConfig} 
        onButtonClick={handleButtonClick}
      />
      
      {/* 添加右下角的重置按钮 */}
      <button 
        className="absolute bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded"
        style={{
          bottom: '10px',
          right: '10px',
          zIndex: 100
        }}
        onClick={handleReset}
      >
        重新载入
      </button>
    </div>
  );
});

export default observer(Radar); 