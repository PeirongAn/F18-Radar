import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Line, Group } from 'react-konva';
import { ScanModeType, ScanControlParams } from './RadarDisplay';

interface ScanLineProps {
  // azimuth参数仍然保留在接口中以保持兼容性，但不再使用
  azimuth?: number;
  radarConfig: any;
  framePositions: {
    startX: number;
    startY: number;
    endX: number;
    endY: number;
  };
  scanMode?: ScanModeType; // 扫描模式配置
  scanControl?: ScanControlParams; // 扫描控制参数
  onScanCycleComplete?: () => void; // 添加扫描完成一次循环的回调函数
  isStarted?: boolean; // 添加系统是否已启动的标志
}

const ScanLine: React.FC<ScanLineProps> = ({ 
  radarConfig, 
  framePositions,
  scanMode = { name: 'normal', scanAngle: 60, scanFraction: 1.0 }, // 默认扫描模式
  scanControl = { 
    sinCoefficient: Math.PI/2, 
    amplitudeScale: 1.0,
    scanSpeed: 1.0, 
    useSineMapping: true 
  }, // 默认扫描控制参数
  onScanCycleComplete,
  isStarted = false // 默认未启动
}) => {
  // 设置基准扫描速度（每毫秒移动的像素数）
  const BASE_SPEED = 0.1; // 像素/毫秒
  
  // 提取控制参数
  const { scanSpeed = 1.0 } = scanControl;
  
  // 使用ref存储当前扫描范围
  const rangeRef = useRef({
    start: 0,
    end: 0,
    scanAngle: scanMode.scanAngle
  });
  
  // 使用ref存储动画状态
  const animRef = useRef({
    position: 0,
    isForward: true,
    lastTime: 0,
    requestId: null as number | null,
    cycleCompleted: false // 添加标记表示当前循环是否已发送完成事件
  });
  
  // 显示位置状态
  const [displayPosition, setDisplayPosition] = useState(0);
  
  // 更新扫描范围的函数
  const updateScanRange = useCallback(() => {
    const centerX = (framePositions.startX + framePositions.endX) / 2;
    const boxWidth = framePositions.endX - framePositions.startX;
    
    // 计算扫描中心位置（应用偏移量）
    const scanCenterX = centerX + (scanMode.centerOffset || 0);
    
    let newStart, newEnd;
    
    // 根据扫描角度确定扫描范围
    if (scanMode.scanAngle === 60) {
      // 60度 - 使用全部范围
      newStart = framePositions.startX;
      newEnd = framePositions.endX;
    } else if (scanMode.scanAngle === 30) {
      // 30度 - 使用中间1/2范围
      newStart = scanCenterX - boxWidth / 4;
      newEnd = scanCenterX + boxWidth / 4;
    } else {
      // 15度 - 使用中间1/4范围
      newStart = scanCenterX - boxWidth / 8;
      newEnd = scanCenterX + boxWidth / 8;
    }
    
    // 如果扫描角度发生变化
    if (rangeRef.current.scanAngle !== scanMode.scanAngle) {
      // 更新范围
      rangeRef.current = {
        start: newStart,
        end: newEnd,
        scanAngle: scanMode.scanAngle
      };
      
      // 重置位置到起点
      animRef.current.position = newStart;
      animRef.current.isForward = true;
      setDisplayPosition(newStart);
      
      // console.log(`扫描范围已更新: 角度=${scanMode.scanAngle}, 范围=[${newStart}, ${newEnd}]`);
    } else {
      // 角度相同但范围可能因窗口大小变化而改变
      rangeRef.current.start = newStart;
      rangeRef.current.end = newEnd;
    }
  }, [framePositions, scanMode.scanAngle, scanMode.centerOffset]);
  
  // 动画函数
  const animate = useCallback((time: number) => {
    const anim = animRef.current;
    const range = rangeRef.current;
    
    if (!anim.lastTime) {
      anim.lastTime = time;
    }
    
    // 计算时间差（毫秒）
    const deltaTime = time - anim.lastTime;
    anim.lastTime = time;
    
    // 计算移动像素
    const pixelDelta = deltaTime * BASE_SPEED * scanSpeed;
    
    // 根据当前方向更新位置
    if (anim.isForward) {
      anim.position += pixelDelta;
      
      // 当扫描线离开左侧边界一段距离后，重置循环完成标记
      if (anim.position > range.start + (range.end - range.start) * 0.1) {
        anim.cycleCompleted = false;
      }
      
      if (anim.position >= range.end) {
        anim.position = range.end;
        anim.isForward = false;
        
        // 当达到右侧边界时，标记为循环完成并通知父组件
        if (!anim.cycleCompleted && onScanCycleComplete) {
          onScanCycleComplete();
          anim.cycleCompleted = true;
          // console.log("扫描完成一次从左到右的循环");
        }
      }
    } else {
      anim.position -= pixelDelta;
      
      // 当扫描线离开右侧边界一段距离后，重置循环完成标记
      if (anim.position < range.end - (range.end - range.start) * 0.1) {
        anim.cycleCompleted = false;
      }
      
      if (anim.position <= range.start) {
        anim.position = range.start;
        anim.isForward = true;
        
        // 当达到左侧边界时，也标记为循环完成并通知父组件
        if (!anim.cycleCompleted && onScanCycleComplete) {
          onScanCycleComplete();
          anim.cycleCompleted = true;
          console.log("扫描完成一次从右到左的循环");
        }
      }
    }
    
    // 更新状态以触发重新渲染
    setDisplayPosition(anim.position);
    
    // 继续动画循环
    anim.requestId = requestAnimationFrame(animate);
  }, [scanSpeed, onScanCycleComplete]);
  
  // 修改重置cycleCompleted标记的位置，确保扫描线开始新方向的移动时才重置
  const startAnimation = useCallback(() => {
    // 如果系统未启动，不启动动画
    if (!isStarted) {
      console.log("系统未启动，不启动扫描动画");
      return;
    }
    
    // 确保先停止已有动画
    if (animRef.current.requestId !== null) {
      cancelAnimationFrame(animRef.current.requestId);
    }
    
    // 重置时间戳
    animRef.current.lastTime = 0;
    
    // 启动新动画
    animRef.current.requestId = requestAnimationFrame(animate);
    
  }, [animate, isStarted]);
  
  const stopAnimation = useCallback(() => {
    if (animRef.current.requestId !== null) {
      cancelAnimationFrame(animRef.current.requestId);
      animRef.current.requestId = null;
    }
  }, []);
  
  // 初始化扫描范围和位置
  useEffect(() => {
    updateScanRange();
    animRef.current.position = rangeRef.current.start;
    setDisplayPosition(rangeRef.current.start);
  }, [updateScanRange]);
  
  // 监听扫描角度变化
  useEffect(() => {
    stopAnimation();
    updateScanRange();
    startAnimation();
    
    return () => stopAnimation();
  }, [scanMode.scanAngle, updateScanRange, startAnimation, stopAnimation]);
  
  // 监听扫描速度变化
  useEffect(() => {
    console.log(`扫描速度变化: ${scanSpeed}`);
    stopAnimation();
    startAnimation();
    
    return () => stopAnimation();
  }, [scanSpeed, startAnimation, stopAnimation]);
  
  // 监听系统启动状态变化
  useEffect(() => {
    console.log(`系统启动状态变化: ${isStarted ? '已启动' : '未启动'}`);
    if (isStarted) {
      startAnimation();
    } else {
      stopAnimation();
    }
    
    return () => stopAnimation();
  }, [isStarted, startAnimation, stopAnimation]);
  
  // T字型标识参数
  const tHeight = 15; // T字型的垂直线高度
  const tWidth = 20;  // T字型的水平线宽度
  
  return (
    <Group>
      {/* T字型扫描标识 */}
      <Line
        points={[
          displayPosition, framePositions.endY,           // 底部起点
          displayPosition, framePositions.endY - tHeight  // 垂直线
        ]}
        stroke={radarConfig.textColor || '#00ff00'}
        strokeWidth={2}
      />
      <Line
        points={[
          displayPosition - tWidth/2, framePositions.endY - tHeight,  // 左端点
          displayPosition + tWidth/2, framePositions.endY - tHeight   // 右端点
        ]}
        stroke={radarConfig.textColor || '#00ff00'}
        strokeWidth={2}
      />
    </Group>
  );
};

export default ScanLine; 