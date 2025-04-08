import React, { useState, useEffect } from 'react';
import RadarButtons from './RadarButtons';
import RadarDisplay, { ScanModeType, ScanControlParams } from './RadarDisplay';
import { useKeyboardControl } from '../hooks/useKeyboardControl';
import useRadarData from '../hooks/useRadarData';

// 雷达范围值数组
const RADAR_RANGES = [10, 20, 40, 80];

export interface RadarProps {
  width?: number;
  height?: number;
  onTargetSelect?: (targetId: string) => void;
}

const Radar: React.FC<RadarProps> = ({
  width = 600,
  height = 600,
  onTargetSelect,
}) => {
  // 使用自定义hook获取WebSocket连接和发送消息的函数
  const { sendMessage, resetTargets } = useRadarData();

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
    // 记录当前参数
    console.log('当前雷达参数:', {
      rangeIndex,
      range: RADAR_RANGES[rangeIndex],
      scanAngle: scanMode.scanAngle,
      scanMode: scanMode.name
    });
    
    // 准备要发送的数据
    const messageData = {
      type: 'settings_update',
      range: RADAR_RANGES[rangeIndex],
      scanAngle: scanMode.scanAngle
    };
    
    console.log('发送设置更新:', messageData);
    
    // 如果WebSocket已连接，发送消息
    if (sendMessage) {
      sendMessage(messageData);
    }
  }, [rangeIndex, scanMode.scanAngle, sendMessage]);

  // 添加目标选择处理函数
  const handleTargetSelection = (targetId: string) => {
    if (onTargetSelect) {
      onTargetSelect(targetId);
    }
  };

  // 处理按钮点击事件
  const handleButtonClick = (position: string, buttonIndex: number) => {
    console.log(`${position} button ${buttonIndex} clicked`);
    
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
    }
    // 添加左侧第2个按钮的功能，用于调整扫描中心位置
    else if (position === 'left' && buttonIndex === 2) {
      // 循环切换扫描中心位置：左偏 -> 中心 -> 右偏 -> 左偏...
      let newCenterOffset: number;
      
      if (scanMode.centerOffset === undefined || scanMode.centerOffset === 0) {
        // 如果当前是中心，切换到右偏
        newCenterOffset = 100; // 向右偏移100像素
      } else if (scanMode.centerOffset > 0) {
        // 如果当前是右偏，切换到左偏
        newCenterOffset = -100; // 向左偏移100像素
      } else {
        // 如果当前是左偏，切换到中心
        newCenterOffset = 0;
      }
      
      // 更新扫描模式
      setScanMode({
        ...scanMode,
        centerOffset: newCenterOffset
      });
    }
    else if (position === 'left' && buttonIndex === 5) {
      // 左侧第5个按钮循环切换BR计数上限：1 -> 2 -> 4 -> 1
      setMaxScanCount((prev) => {
        if (prev === 1) return 2;
        if (prev === 2) return 4;
        return 1; // 如果是4或其他值，回到1
      });
      console.log("BR计数上限已更新:", maxScanCount);
    }
    else if (position === 'right' && buttonIndex === 1) {
      // 增加范围索引，实现循环
      setRangeIndex((prevIndex) => (prevIndex + 1) % RADAR_RANGES.length);
    }
    else if (position === 'right' && buttonIndex === 2) {
      // 减少范围索引，确保不小于0
      setRangeIndex((prevIndex) => (prevIndex > 0 ? prevIndex - 1 : RADAR_RANGES.length - 1));
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

  // 添加一个设置特定状态的函数
  const setSpecialCondition = () => {
    console.log('====== 设置特殊条件 ======');
    console.log('设置特殊条件: scan_angle=30, range=80海里');
    
    // 设置扫描角度为精确的30度
    const newScanMode = {
      name: 'medium',
      scanAngle: 30,
      scanFraction: 0.5,
      centerOffset: scanMode.centerOffset // 保持原有的中心偏移量
    };
    
    console.log('设置新的扫描模式:', newScanMode);
    setScanMode(newScanMode);
    
    // 设置范围为精确的80海里 (索引3)
    console.log('设置雷达范围为:', RADAR_RANGES[3], '海里 (索引:', 3, ')');
    setRangeIndex(3); // RADAR_RANGES[3] = 80
    
    // 手动发送更新消息以确保服务器接收
    setTimeout(() => {
      const messageData = {
        type: 'settings_update',
        range: RADAR_RANGES[3],
        scanAngle: 30
      };
      
      console.log('手动发送精确的设置更新:', messageData);
      sendMessage(messageData);
      console.log('====== 特殊条件设置完成 ======');
    }, 100); // 短暂延迟确保状态已更新
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

export default Radar; 