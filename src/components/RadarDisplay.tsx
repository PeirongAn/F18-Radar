import React, { useState, useEffect } from 'react';
import { Stage, Layer, Group, Line } from 'react-konva';
import { renderMainFrame, renderText } from './RadarRenderers';
import useRadarData from '../hooks/useRadarData';
import ScanLine from './ScanLine';
import ConnectionStatus from './ConnectionStatus';
import VelocityVector from './VelocityVector';
import HorizonHUD from './HorizonHUD';
import { UnknownTargetManager } from './UnknownTargetManager';
import { UnknownTargetData } from './UnknownTarget';

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
export type ScanModeType = {
  name: string;
  scanAngle: number; // 扫描角度范围，如60或15
  scanFraction: number; // 扫描区域占比，如1.0表示全区域，0.25表示1/4
  centerOffset?: number; // 扫描中心位置的偏移量，默认为0（即中心位置）
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
  onTargetSelect?: (targetId: string) => void;
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
}

const RadarDisplay: React.FC<RadarDisplayProps> = ({ 
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
  onModeDisplayChange // 显示模式变更回调
}) => {
  // 使用钩子获取实时雷达数据以及发送消息的函数
  const { connected, radarData, error } = useRadarData(wsUrl);
  
  // 添加本地状态来跟踪和强制更新externalTargets
  const [localExternalTargets, setLocalExternalTargets] = React.useState<UnknownTargetData[] | undefined>(undefined);
  const [updateCounter, setUpdateCounter] = React.useState(0); // 用于强制更新的计数器
  
  // 添加状态跟踪选中的目标和垂直线
  const [selectedTargetId, setSelectedTargetId] = React.useState<string | undefined>(undefined);
  const [verticalLineX, setVerticalLineX] = React.useState<number | undefined>(undefined);
  
  // 添加IFF模式状态
  const [iffMode, setIffMode] = React.useState(false);
  

  
  // 添加HI/MED状态切换
  const [hiMedToggle, setHiMedToggle] = React.useState<'HI' | 'MED'>('HI');
  
  // 计算显示区域中心
  const centerX = (framePositions.startX + framePositions.endX) / 2;
  const centerY = (framePositions.startY + framePositions.endY) / 2;
  
  // 计算缩放因子将海里换算到像素坐标
  const scale = ((framePositions.endX - framePositions.startX) / 2 - radarConfig.padding) / 80; // 假设80海里是最大范围
  
  // 添加useEffect来监控radarData的变化并更新本地状态
  React.useEffect(() => {
    console.log('【调试】RadarDisplay - radarData变化, 值:', JSON.stringify(radarData));
    
    if (radarData) {
      console.log('【调试】RadarDisplay - radarData包含的键:', Object.keys(radarData));
      const hasExternalTargets = 'externalTargets' in radarData && Array.isArray(radarData.externalTargets);
      console.log('【调试】RadarDisplay - radarData是否包含externalTargets:', hasExternalTargets);
      
      if (hasExternalTargets && radarData.externalTargets) {
        console.log('【调试】RadarDisplay - 设置本地externalTargets:', JSON.stringify(radarData.externalTargets));
        setLocalExternalTargets(radarData.externalTargets);
        // 强制更新计数器增加，确保组件重新渲染
        setUpdateCounter(prev => prev + 1);
      }
    }
  }, [radarData]); // 移除updateCounter以避免循环依赖
  
  // 直接检查并处理targets
  React.useEffect(() => {
    if (localExternalTargets) {
      console.log('RadarDisplay - 本地externalTargets已更新:', localExternalTargets);
    }
  }, [localExternalTargets, centerX, centerY]);
  
  // 添加一些额外的调试信息
  console.log('RadarDisplay - 渲染运行，updateCounter:', updateCounter);
  
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
  const handleKeyDown = React.useCallback((e: KeyboardEvent) => {
    if (e.key === 'Enter' && processedExternalTargets) {
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
        setSelectedTargetId(closestTarget.id);
        setVerticalLineX(tdcPosition.x); // 设置垂直线的X坐标为TDC的X坐标
        
        // 如果有外部的目标选择回调，调用它
        if (onTargetSelect) {
          onTargetSelect(closestTarget.id);
        }
      } else {
        console.log('没有找到靠近TDC的目标');
        // 如果没有找到目标，清除选中状态
        setSelectedTargetId(undefined);
        setVerticalLineX(undefined);
      }
    }
  }, [tdcPosition, processedExternalTargets, centerX, onTDCPositionSet, onTargetSelect]);
  
  // 添加IFF按钮点击处理函数
  const handleIFFClick = React.useCallback(() => {
    console.log(`IFF模式：${!iffMode ? '启用' : '关闭'}`);
    setIffMode(!iffMode); // 切换IFF模式
  }, [iffMode]);
  
  // 自定义渲染函数，添加IFF按钮的点击事件
  const renderCustomText = (props: any) => {
    const originalElements = renderText({
      ...props,
      displayMode // 传递当前显示模式
    });
    
    // 为IFF文本元素添加点击处理
    return React.cloneElement(originalElements, {}, [
      ...React.Children.toArray(originalElements.props.children),
      // 额外添加IFF按钮点击区域（透明覆盖层）
      <Group key="iff-click-area" x={props.framePositions.startX + 290} y={props.framePositions.startY - 40}>
        <Line
          points={[-5, -5, 30, -5, 30, 20, -5, 20, -5, -5]}
          fill={iffMode ? 'rgba(0, 255, 0, 0.2)' : 'transparent'} // IFF模式启用时有轻微绿色背景
          closed={true}
          onClick={handleIFFClick}
          onTap={handleIFFClick}
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
            hiMedToggle // 传递HI/MED切换状态
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
            range: range
          })}
          
          {/* 渲染雷达扫描线 - 传递当前的扫描模式和控制参数 */}
          {radarData && (
            <ScanLine 
              azimuth={radarData.radar_azimuth} 
              radarConfig={radarConfig} 
              framePositions={framePositions} 
              scanMode={scanMode} // 传递扫描模式
              scanControl={scanControl} // 传递扫描控制参数
              onScanCycleComplete={handleScanCycleComplete} // 传递扫描完成事件处理函数
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
            showTargets={showUnknownTargets}
            color={radarConfig.recColor}
            externalTargets={processedExternalTargets} // 传递处理后的目标数据
            selectedTargetId={selectedTargetId} // 传递选中的目标ID
            verticalLineX={verticalLineX} // 传递垂直线的X坐标
            framePositions={framePositions} // 传递雷达显示区域边界
            iffMode={iffMode} // 传递IFF模式状态
          />
        </Layer>
      </Stage>
    </div>
  );
};

export default RadarDisplay; 