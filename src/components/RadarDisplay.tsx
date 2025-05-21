import React, { useState, useEffect, useCallback } from 'react';
import { Stage, Layer, Group, Line } from 'react-konva';
import { observer } from 'mobx-react-lite';
import { renderMainFrame, renderText } from './RadarRenderers';
import useRadarData from '../hooks/useRadarData';
import ScanLine from './ScanLine';
import ConnectionStatus from './ConnectionStatus';
import VelocityVector from './VelocityVector';
import HorizonHUD from './HorizonHUD';
import { UnknownTargetManager } from './UnknownTargetManager';
import { UnknownTargetData } from './UnknownTarget';
import { globalWS } from '../hooks/useRadarData';
import radarStore from '../stores/RadarStore';
import agentStore from '../stores/AgentStore';

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
  wsUrl?: string; // WebSocket服务器URL
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
}

const RadarDisplay: React.FC<RadarDisplayProps> = observer(({ 
  width, 
  height, 
  radarConfig, 
  framePositions,
  tdcPosition,
  onTargetSelect,
  wsUrl = 'ws://localhost:8765',
  scanMode = { name: 'normal', scanAngle: 60, scanFraction: 1 }, // 默认扫描模式
  scanControl = {
    sinCoefficient: Math.PI/2,
    amplitudeScale: 1.0,
    useSineMapping: true,
    scanSpeed: 1.0  // 添加默认扫描速度
  }, // 默认扫描控制参数
  onTDCPositionSet, // TDC位置设置回调函数
  showVectorHUD = true, // 默认显示
  range = 80, // 默认范围值
  showUnknownTargets = true, // 默认显示未知目标
  maxScanCount = 4, // 默认值为4
  displayMode, // 从props接收显示模式
  onModeDisplayChange, // 显示模式变更回调
  isSilent = false, // 默认不处于静默模式
  isStarted = false, // 默认未启动状态
  sendMessage // 传递发送消息函数
}) => {
  // 使用钩子获取实时雷达数据以及发送消息的函数
  const { connected, radarData, error } = useRadarData(wsUrl);
  
  // 添加本地状态来跟踪和强制更新externalTargets
  const [localExternalTargets, setLocalExternalTargets] = React.useState<UnknownTargetData[] | undefined>(undefined);
  const [updateCounter, setUpdateCounter] = React.useState(0); // 用于强制更新的计数器
  
  // 添加IFF模式状态
  const [iffMode, setIffMode] = React.useState(false);
  const [radarAzimuth, setRadarAzimuth] = React.useState<number>(0);
  const [ownHeading, setOwnHeading] = React.useState<number>(0);
  
  // 添加HI/MED状态切换
  const [hiMedToggle, setHiMedToggle] = React.useState<'HI' | 'MED'>('HI');
  
  // 计算显示区域中心
  const centerX = (framePositions.startX + framePositions.endX) / 2;
  const centerY = (framePositions.startY + framePositions.endY) / 2;
  
  
  // 添加useEffect来监控radarData的变化并更新本地状态
  React.useEffect(() => {
    if (radarData) {
      const hasExternalTargets = 'externalTargets' in radarData && Array.isArray(radarData.externalTargets);
      if (hasExternalTargets && radarData.externalTargets) {
        setLocalExternalTargets(radarData.externalTargets);
        setUpdateCounter(prev => prev + 1);
      }
      setRadarAzimuth(radarData.radar_azimuth);
      setOwnHeading(radarData.own_heading);
    }
  }, [radarData]);
  
  // 直接检查并处理targets
  React.useEffect(() => {
    if (localExternalTargets) {
      console.log('RadarDisplay - 本地externalTargets已更新:', localExternalTargets);
    }
  }, [localExternalTargets, centerX, centerY]);
  
  // 从本地状态获取externalTargets并处理坐标
  const processedExternalTargets = React.useMemo(() => {
    console.log('RadarDisplay - processedExternalTargets 计算被调用');
    console.log('RadarDisplay - localExternalTargets:', localExternalTargets);
    
    if (!localExternalTargets) {
      console.log('RadarDisplay - 未找到 localExternalTargets 或为空');
      return undefined;
    }
    
    console.log('RadarDisplay - 处理 localExternalTargets:', localExternalTargets);
    // 对每个目标的坐标进行处理，将偏移量调整为相对于屏幕中心的实际坐标
    return localExternalTargets.map(target => ({
      ...target,
      position: {
        x: centerX + target.position.x, // 将x偏移量调整为相对于屏幕中心的坐标
        y: centerY + target.position.y  // 将y偏移量调整为相对于屏幕中心的坐标
      }
    }));
  }, [localExternalTargets, centerX, centerY, updateCounter]); // 添加updateCounter作为依赖
  
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
      let closestTarget: UnknownTargetData | undefined;
      let minDistance = 30; // 设置一个阈值，只有距离小于这个值的目标才会被选中
      
      processedExternalTargets.forEach(target => {
        const distance = Math.sqrt(
          Math.pow(target.position.x - tdcPosition.x, 2) + 
          Math.pow(target.position.y - tdcPosition.y, 2)
        );
        
        if (distance < minDistance) {
          minDistance = distance;
          closestTarget = target;
        }
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
    // Space key for auto-lock (existing logic)
    if (e.key === ' ' && processedExternalTargets && onTargetSelect) { // Space bar
      console.log('RadarDisplay - Spacebar pressed. TDC position:', tdcPosition);
      let closestTarget: UnknownTargetData | undefined;
      let minDistance = 30; // 30px search radius

      processedExternalTargets.forEach(target => {
        const distance = Math.sqrt(
          Math.pow(target.position.x - tdcPosition.x, 2) +
          Math.pow(target.position.y - tdcPosition.y, 2)
        );
        if (distance < minDistance) {
          minDistance = distance;
          closestTarget = target;
        }
      });

      if (closestTarget) {
        console.log('RadarDisplay - Spacebar: Found closest target:', closestTarget.id, 'at TDC X:', closestTarget.position.x);
        onTargetSelect({
          targetId: closestTarget.id,
          lockX: closestTarget.position.x,
          iffMode: iffMode,
          externalTargetsTimestamp: radarData?.externalTargetsTimestamp
        });
      } else {
        console.log('RadarDisplay - Spacebar: No target found near TDC for auto-lock.');
      }
    }
  }, [tdcPosition, processedExternalTargets, centerX, onTDCPositionSet, onTargetSelect, iffMode, radarData?.externalTargetsTimestamp]);
  
  // 处理IFF模式切换
  const handleIFFModeToggle = () => {
    setIffMode(prev => !prev);
  };
  
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
          onClick={handleIFFModeToggle}
          onTap={handleIFFModeToggle}
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
  const handleScanCycleComplete = () => {
    // 增加扫描计数，当达到上限时重置为0
    setScanCount(prevCount => {
      const newCount = prevCount + 1;
      // 当计数达到最大值时，重置为0
      return newCount < maxScanCount ? newCount : 0;
    });
    
    // 根据当前显示模式更新HI/MED切换
    if (displayMode === 'AUTO') {
      // 在AUTO模式下，每次扫描循环后切换HI/MED显示
      setHiMedToggle(prev => prev === 'HI' ? 'MED' : 'HI');
      console.log(`AUTO模式: 切换到 ${hiMedToggle === 'HI' ? 'MED' : 'HI'}`);
    }
    // 在HI或MED模式下，hiMedToggle保持不变
    
    console.log("扫描完成一次循环，更新计数");
  };
  


  return (
    <div className="radar-container bg-black" style={{ 
      borderRadius: '4px',
      width: width,
      height: height,
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      position: 'relative'
    }}>
      {/* 连接状态指示器 */}
      <ConnectionStatus 
        connected={connected} 
        error={error} 
        style={{
          position: 'absolute',
          top: 5,
          right: 5,
          zIndex: 10
        }}
      />
      
      {/* 未启动提示 */}
      {!isStarted && (
        <div 
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            color: '#00ff00',
            backgroundColor: 'rgba(0, 0, 0, 0.7)',
            padding: '15px 25px',
            borderRadius: '5px',
            zIndex: 5,
            border: '1px solid #00ff00',
            fontSize: '18px',
            fontFamily: 'monospace'
          }}
        >
          等待系统启动...
        </div>
      )}
      
      <Stage width={width} height={height}>
        <Layer>
          {/* 渲染雷达背景、网格和文本 - 使用renderMainFrame函数而不是RadarRenderers组件 */}
          {renderMainFrame({
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
            displayMode, // 传递显示模式
            hiMedToggle, // 传递HI/MED切换状态
            isSilent,    // 传递静默状态
            isStarted,    // 传递系统启动状态
            sendMessage, // 传递发送消息函数
          })}
          
          {/* 渲染文本和状态信息，使用自定义渲染函数 */}
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
          
          {/* 渲染雷达扫描线 - 只在非静默模式下且系统已启动时显示 */}
          {radarData && !isSilent && isStarted && (
            <ScanLine 
              azimuth={radarData.radar_azimuth} 
              radarConfig={radarConfig} 
              framePositions={framePositions} 
              scanMode={scanMode} // 传递扫描模式
              scanControl={scanControl} // 传递扫描控制参数
              onScanCycleComplete={handleScanCycleComplete} // 传递扫描完成事件处理函数
              isStarted={isStarted} // 传递系统启动状态
            />
          )}
          
          {/* 根据showVectorHUD状态渲染VelocityVector和HorizonHUD */}
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
          
          {/* 渲染未知目标 - 使用UnknownTargetManager */}
          <UnknownTargetManager
            showTargets={showUnknownTargets && !isSilent} // 在静默模式下不显示目标
            color={radarConfig.recColor}
            externalTargets={processedExternalTargets} // 传递处理后的目标数据
            selectedTargetId={radarStore.lockedTargetId} // Use from store
            verticalLineX={radarStore.lockScreenX}    // Use from store
            framePositions={framePositions} // 传递显示区域边界
            iffMode={iffMode} // 启用IFF模式
          />
          
          {/* IFF模式指示器 */}
         
        </Layer>
      </Stage>
    </div>
  );
});

export default RadarDisplay; 