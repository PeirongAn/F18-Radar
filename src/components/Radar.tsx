import React, { useState, useEffect, useRef, useCallback } from 'react';
import RadarButtons from './RadarButtons';
import RadarDisplay, { ScanModeType, ScanControlParams } from './RadarDisplay';
import AntennaElevationMarker from './AntennaElevationMarker'; // Import AntennaElevationMarker
import { useKeyboardControl } from '../hooks/useKeyboardControl';
import useRadarData from '../hooks/useRadarData';
import { observer } from 'mobx-react-lite';
import { useStore } from '../stores/StoreProvider';
import agentStore from '../stores/AgentStore'; // Import AgentStore directly
import radarStore from '../stores/RadarStore';

// 雷达范围值数组
const RADAR_RANGES = [10, 20, 40, 80];

// 定义传递给App.tsx中onTargetSelect回调的参数类型
interface TargetSelectParams {
  targetId: string | undefined;
  lockX?: number;
  iffMode?: boolean; // AI可能不直接处理IFF模式，但类型需匹配
  externalTargetsTimestamp?: number | null; // AI获取数据的方式不同，可能为null
}

export interface RadarProps {
  width?: number;
  height?: number;
  onTargetSelect?: (params: TargetSelectParams) => void; // 更新类型
  isStarted?: boolean; // 添加系统是否已启动的属性
  onRadarParamsUpdate?: (range: number, scanAngle: number) => void; // 添加参数更新回调
}

const Radar: React.FC<RadarProps> = (({
  width = 600,
  height = 600,
  onTargetSelect,
  isStarted = false, // 默认为未启动状态
  onRadarParamsUpdate,
}) => {
  // 使用自定义hook获取WebSocket连接和发送消息的函数
  const { 
    sendMessage, 
    resetTargets, 
    initializeSystem, 
    taskId,
    submitSettings,
    antennaAdjustmentRequired,
    targetAntennaElevation, // Ensure this is destructured
    radarData, 
    initSettings, 
    confirmAntennaAdjustmentHandled, // Destructure the new function
  } = useRadarData();
  
  // 使用MobX Store
  const { radarStore } = useStore();

  // 定义扫描模式状态
  const [scanMode, setScanMode] = useState<ScanModeType>({
    name: 'normal',
    scanAngle: 60,
    scanFraction: 1.0,
    centerOffset: 0 // 设置扫描中心偏移量，0表示居中
  });

  // 添加显示控制状态
  const [showVectorHUD, setShowVectorHUD] = useState(false);
  
  // 添加未知目标显示控制状态
  const [showUnknownTargets, setShowUnknownTargets] = useState(true);
  const [unknownTargetCount, setUnknownTargetCount] = useState(5); // 默认显示全部5个未知目标
  
  // 添加雷达范围索引状态
  const [rangeIndex, setRangeIndex] = useState(1); // 默认为20海里(索引1)
  
  // 添加BR计数状态
  const [maxScanCount, setMaxScanCount] = useState(1); // 默认BR计数上限为1
  
  // 添加显示模式状态
  const [displayMode, setDisplayMode] = useState<'AUTO' | 'HI' | 'MED'>('AUTO');
  
  // 添加雷达静默状态
  const [isSilent, setIsSilent] = useState(false);

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
    padding: 40,
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

  // Handler for TDC key actions from useKeyboardControl
  const handleTdcKeyAction = useCallback((action: 'up' | 'down' | 'left' | 'right') => {
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
  }, [width, height, radarConfig.padding, radarConfig.mainBoxWidth, radarConfig.mainBoxHeight]); // Dependencies for framePositions

  // Setup keyboard controls for TDC
  useKeyboardControl({
    moveStep: 5, // This moveStep is now for context or can be removed if logic is fully in handleTdcKeyAction
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
    onKeyAction: handleTdcKeyAction,
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
        agentStore.setOperationOwner('AI');
        submitSettings({
          range: targetRange,       // Submit the actual recommended value
          scanAngle: targetScanAngle  // Submit the actual recommended value
        });
        agentStore.setOperationOwner('manual');
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

  // useEffect for AI to automatically submit initial radar parameters when AI is activated
  useEffect(() => {
    console.log('initSettings', agentStore.isAIActive, isStarted, initSettings);
    if (
      agentStore.isAIActive &&
      isStarted &&
      initSettings &&
      typeof initSettings.range === 'number' &&
      typeof initSettings.scanAngle === 'number'
    ) {
      console.log('[AI Radar] AI is active and initSettings received. Processing for auto-configuration:', initSettings);

      const targetRange = initSettings.range;
      const targetScanAngle = initSettings.scanAngle;
      let needsSettingsSubmission = false;
      let paramsChangedForUI = false;

      // Update local rangeIndex if different
      const newRangeIndex = RADAR_RANGES.findIndex(r => r === targetRange);
      if (newRangeIndex !== -1 && rangeIndex !== newRangeIndex) {
        console.log(`[AI Radar] initSettings: Adjusting range from ${RADAR_RANGES[rangeIndex]} to ${targetRange}`);
        setRangeIndex(newRangeIndex);
        paramsChangedForUI = true;
      }

      // Update local scanMode if different
      if (scanMode.scanAngle !== targetScanAngle) {
        console.log(`[AI Radar] initSettings: Adjusting scan angle from ${scanMode.scanAngle} to ${targetScanAngle}`);
        let newScanModeName: ScanModeType['name'] = 'normal';
        let newScanFraction = 1.0;
        if (targetScanAngle === 30) {
          newScanModeName = 'medium'; newScanFraction = 0.5;
        } else if (targetScanAngle === 15) {
          newScanModeName = 'narrow'; newScanFraction = 0.25;
        } else if (targetScanAngle !== 60) {
            console.warn(`[AI Radar] initSettings: Unsupported scan angle ${targetScanAngle}. Defaulting to 60 for UI.`);
            // UI will use targetScanAngle, but name/fraction might be for 'normal'
        }
        setScanMode({
          name: newScanModeName,
          scanAngle: targetScanAngle, // Use the initSetting angle
          scanFraction: newScanFraction,
          centerOffset: 0 // Reset offset when AI takes over with initSettings
        });
        paramsChangedForUI = true;
      }
      
      // Always try to submit initSettings if AI is active and initSettings are present, 
      // as backend might expect this handshake regardless of UI change.
      // The validateSettings in useRadarData will ensure it's within tolerance of its own initSettings copy.
      needsSettingsSubmission = true; 

      if (needsSettingsSubmission) {
        console.log('[AI Radar] Submitting initSettings to backend.');
        agentStore.setOperationOwner('AI');
        submitSettings({
          range: targetRange, // Submit the actual initSetting value
          scanAngle: targetScanAngle, // Submit the actual initSetting value
        });
        agentStore.setOperationOwner('manual');
        console.log('[AI Radar] Initial parameters (from initSettings) processed by AI.');
      } else if (paramsChangedForUI) {
        console.log('[AI Radar] initSettings: UI parameters updated, but no submission needed as values might match server expectations already or validation might handle it.');
      }

    }
  }, [agentStore.isAIActive, isStarted, initSettings, submitSettings, rangeIndex, scanMode]);

  // Effect for AI to automatically select a target
  useEffect(() => {
    if (agentStore.isAIActive && agentStore.currentAILevelConfig && radarData?.externalTargets && radarData.externalTargets.length > 0 && !radarStore.lockedTargetId && isStarted) {
      const config = agentStore.currentAILevelConfig;
      // const availableTargets = radarData.externalTargets.filter(t => !t.isHostile); // Example: AI avoids hostile targets or specific logic
      // For now, AI considers all external targets
      const availableTargets = radarData.externalTargets;
      
      if (availableTargets.length > 0) {
        // Simple AI: select the first available target
        // More complex AI might use threat assessment, distance, etc.
        const targetToSelect = availableTargets[0];

        // Simulate AI decision delay
        const decisionTimeoutId = setTimeout(() => {
          if (!agentStore.isAIActive || radarStore.lockedTargetId) return; // Double check before action

          console.log(`[AI Engine] AI is preparing to select target: ${targetToSelect.id}`);
          agentStore.setOperationOwner('AI');

          // AI needs to determine the TDC position for the lock line.
          // For simplicity, let's assume AI wants to place TDC directly on the target.
          // We need the target's current display position.
          const targetDisplayPosition = radarStore.targetDisplayPositions.get(targetToSelect.id);

          if (targetDisplayPosition) {
            const aiTdcXForLock = targetDisplayPosition.x;
            console.log(`[AI Engine] AI selected target ${targetToSelect.id}. Calculated TDC X for lock: ${aiTdcXForLock}`);
            if (onTargetSelect) {
              onTargetSelect({ targetId: targetToSelect.id, lockX: aiTdcXForLock });
            }
            // 操作完成后，AI应在合适的时机将 operationOwner 恢复为 'manual'
            // 例如，在一个模拟操作序列的末尾，或者如果这是一个独立操作，则可以在此之后不久恢复
            // setTimeout(() => agentStore.setOperationOwner('manual'), 100); // Example: Reset after a short delay
          } else {
            console.warn(`[AI Engine] Could not get display position for target ${targetToSelect.id}. Cannot lock with AI TDC.`);
            // Fallback or do nothing if position is not available
             if (onTargetSelect) {
              // Select without specific lockX, App.tsx might handle default or no line
              onTargetSelect({ targetId: targetToSelect.id }); 
            }
          }
          // Consider resetting operation owner after a short delay or sequence completion
          // setTimeout(() => agentStore.setOperationOwner('manual'), 200); // Example reset
        }, config.threat_select_delay_ms || 1000);

        return () => clearTimeout(decisionTimeoutId);
      }
    }
  }, [agentStore.isAIActive, agentStore.currentAILevelConfig, radarData, radarStore.lockedTargetId, onTargetSelect, isStarted]);

  // Effect for AI to move TDC to the selected target (if AI selected it)
  useEffect(() => {
    if (agentStore.isAIActive && radarStore.lockedTargetId && agentStore.currentOperationOwner === 'AI' && agentStore.currentAILevelConfig) {
      const targetId = radarStore.lockedTargetId;
      const targetPosition = radarStore.targetDisplayPositions.get(targetId);
      const config = agentStore.currentAILevelConfig;

      if (targetPosition && config?.tdc_move_delay_ms !== undefined) {
        console.log(`[AI TDC DEBUG Radar.tsx] AI preparing to move TDC to target ${targetId} at (${targetPosition.x}, ${targetPosition.y}) after ${config.tdc_move_delay_ms}ms delay.`);
        
        const tdcMoveTimeoutId = setTimeout(() => {
          if (agentStore.isAIActive && radarStore.lockedTargetId === targetId) { // Check if still relevant
            console.log(`[AI TDC DEBUG Radar.tsx] AI moving TDC to (${targetPosition.x}, ${targetPosition.y}) for target ${targetId}.`);
            setTdcPosition(targetPosition);
            // After TDC movement, AI might perform other actions or reset its state.
            // Resetting operation owner to manual should happen after the *entire sequence* of AI actions for this target.
            // For example, if AI selects, moves TDC, then does something else, reset owner after all steps.
            // If this is the last step for this specific target selection event by AI: 
            // setTimeout(() => agentStore.setOperationOwner('manual'), 50); // Small delay to ensure message sending etc.
          }
        }, config.tdc_move_delay_ms);
        return () => clearTimeout(tdcMoveTimeoutId);
      }
    }
  }, [radarStore.lockedTargetId, agentStore.isAIActive, agentStore.currentOperationOwner, agentStore.currentAILevelConfig, radarStore.targetDisplayPositions]);

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
      agentStore.setOperationOwner('AI');
      
      // Pass 'ai' as source and the sendMessage callback
      radarStore.setCurrentAntennaElevation(targetAntennaElevation, 'ai', sendMessage);
      
      agentStore.setOperationOwner('manual');
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

  // 添加目标选择处理函数
  const handleTargetSelection = (params: TargetSelectParams) => {
    if (onTargetSelect) {
      onTargetSelect(params);
    }
  };

  // 处理按钮点击事件
  const handleButtonClick = (position: string, buttonIndex: number) => {
    console.log(`${position} button ${buttonIndex} clicked`);
    
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
    // 更新扫描模式，设置新的中心偏移量
    setScanMode({
      ...scanMode,
      centerOffset: offset
    });
    console.log(`扫描中心已设置，偏移量: ${offset}px`);
  };


  // 添加系统重置功能
  const handleReset = () => {
    console.log('====== 系统重置 ======');
    
    // 发送消息到服务器重置目标
    if (resetTargets) {
      resetTargets();
      console.log('已发送重置目标请求到服务器');
    }
    
    // 发送重置后的设置到服务器
    if (sendMessage) {
      const resetMessage = {
        type: 'settings_update',
        range: RADAR_RANGES[1], // 20海里
        scanAngle: 60
      };
      sendMessage(resetMessage);
      console.log('已发送重置设置到服务器');
    }
    
    console.log('系统即将刷新页面...');
    
    // 短暂延迟后刷新页面，确保消息已发送
    setTimeout(() => {
      window.location.reload();
    }, 300);
  };

  return (
    <div className="flex flex-col items-center justify-center relative">
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
        <div className="flex flex-col items-center mr-2"> {/* Wrapper for left buttons and marker */}
          <RadarButtons 
            position="left" 
            framePositions={framePositions} 
            radarConfig={radarConfig} 
            onButtonClick={handleButtonClick}
          />
          {/* 天线高度指示器 - 放置在左侧按钮下方 */}
          {isStarted && (
            <div style={{ marginTop: '10px', width: radarConfig.buttonSize, height: '100px', backgroundColor: '#222', padding:'5px' }}>
              {/* 
                x: 相对于其父容器的偏移，这里因为AntennaElevationMarker内部使用的是Konva, 
                   直接在HTML div中渲染可能需要调整或包裹在Stage/Layer中。
                   为了简单起见，我们假设AntennaElevationMarker可以处理这种混合，
                   或者提供一个简化的HTML/SVG版本的天线指示器。
                   对于Konva组件，它需要一个Konva Stage环境。
                   此处仅为占位，实际渲染Konva组件需要更复杂的集成。
                   我们先传递必要的props。
              */}
              {/* Placeholder for AntennaElevationMarker Konva rendering, needs a Stage/Layer */}
              {/* For now, let's assume we want to render it conceptually here. */}
              {/* Actual Konva rendering of AntennaElevationMarker inside a non-Konva parent (div) 
                  would require setting up a new Konva Stage for it, or making AntennaElevationMarker 
                  a pure React component if it's simple enough. 
                  Given its current Konva dependencies, it's best rendered within a Stage.
                  Let's simplify for now and assume its props are what matter for the logic.
              */}
               <AntennaElevationMarker
                x={radarConfig.buttonSize / 2} // Example X position within its own small container
                minY={10} // Example minY for the marker display area
                maxY={90} // Example maxY for the marker display area
                color={radarConfig.gridColor}
                sendMessage={sendMessage} // Pass the sendMessage function
              />
            </div>
          )}
        </div>
        
        {/* 雷达显示 */}
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
        />
        
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
        重置系统
      </button>
    </div>
  );
});

export default observer(Radar); 