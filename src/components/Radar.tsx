import React, { useState, useEffect } from 'react';
import RadarButtons from './RadarButtons';
import RadarDisplay, { ScanModeType, ScanControlParams } from './RadarDisplay';
import { useKeyboardControl } from '../hooks/useKeyboardControl';
import useRadarData from '../hooks/useRadarData';
import { observer } from 'mobx-react-lite';
import { useStore } from '../stores/StoreProvider';

// 雷达范围值数组
const RADAR_RANGES = [10, 20, 40, 80];

export interface RadarProps {
  width?: number;
  height?: number;
  onTargetSelect?: (targetId: string) => void;
  isStarted?: boolean; // 添加系统是否已启动的属性
  onRadarParamsUpdate?: (range: number, scanAngle: number) => void; // 添加参数更新回调
}

const Radar: React.FC<RadarProps> = ({
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
    antennaAdjustmentRequired
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

  const tdcPosition = useKeyboardControl({
    initialPosition: { x: width / 2, y: height / 2 },
    moveStep: 5,
    boundaries: {
      minX: framePositions.startX + radarConfig.padding,
      maxX: framePositions.endX - radarConfig.padding,
      minY: framePositions.startY + radarConfig.padding,
      maxY: framePositions.endY - radarConfig.padding
    }
  });

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
  }, [rangeIndex, scanMode.scanAngle, isSilent, onRadarParamsUpdate]);

  // 添加目标选择处理函数
  const handleTargetSelection = (targetId: string) => {
    if (onTargetSelect) {
      onTargetSelect(targetId);
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
        {/* 左侧按钮 */}
        <RadarButtons 
          position="left" 
          framePositions={framePositions} 
          radarConfig={radarConfig} 
          onButtonClick={handleButtonClick}
        />
        
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
};

// 使用MobX的observer包装组件
export default observer(Radar); 