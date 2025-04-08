import React, { useEffect, useState, useRef } from 'react';
import { Group, Line, Text } from 'react-konva';

// 定义未知目标数据接口
export interface UnknownTargetData {
  id: string;                       // 目标唯一标识
  position: { x: number, y: number }; // 当前位置
  history: { x: number, y: number }[]; // 历史位置记录
  speed: number;                    // 目标速度
  direction: number;                // 运动方向（弧度）
  type: 'friend' | 'army'; // 目标类型
  selected?: boolean;               // 添加选中状态标记
}

interface UnknownTargetProps {
  data: UnknownTargetData;
  color: string;
  framePositions?: {  // 添加雷达显示边界信息
    startX: number;
    startY: number;
    endX: number;
    endY: number;
  };
}

const UnknownTarget: React.FC<UnknownTargetProps> = ({ data, color, framePositions }) => {
  // 简化状态，只用一个状态跟踪偏移量，而不是完整的位置
  // 这样即使原始position发生变化，也不会影响偏移量的累加
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  
  // 使用useRef记录动画ID
  const animationFrameId = useRef<number | null>(null);
  
  // 从props解构需要的属性
  const { id, direction, type, speed, selected, position } = data;
  
  // 计算实际显示位置 = 原始位置 + 当前偏移量
  const displayPosition = {
    x: position.x + offset.x,
    y: position.y + offset.y
  };
  
  // 判断目标是否在显示区域内
  const isInDisplayArea = () => {
    // 如果未提供边界信息，默认显示
    if (!framePositions) return true;
    
    // 检查目标是否在边界内（包含边界）
    // 添加小的缓冲区，避免目标刚好在边缘时闪烁
    const buffer = 5;
    return (
      displayPosition.x >= framePositions.startX - buffer &&
      displayPosition.x <= framePositions.endX + buffer &&
      displayPosition.y >= framePositions.startY - buffer &&
      displayPosition.y <= framePositions.endY + buffer
    );
  };
  
  // 如果目标超出显示区域，停止动画并不渲染
  if (!isInDisplayArea()) {
    // 清理动画
    if (animationFrameId.current) {
      cancelAnimationFrame(animationFrameId.current);
      animationFrameId.current = null;
    }
    
    // 返回null表示不渲染任何内容
    return null;
  }
  
  // 将弧度转换为角度，便于调试
  const directionDegrees = (direction * 180 / Math.PI) % 360;
  
  // 旋转点的辅助函数
  const rotatePoint = (x: number, y: number, angle: number): [number, number] => {
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    return [
      x * cos - y * sin,
      x * sin + y * cos
    ];
  };
  
  // ==================== 三角形绘制 ====================
  
  // 定义三角形基础形状（倒置，底边在上，尖端朝下）
  const triangleTip = { x: 0, y: 10 }; // 顶点（朝下）
  const baseLeft = { x: -5, y: 0 }; // 底边左端点
  const baseRight = { x: 5, y: 0 }; // 底边右端点
  const baseCenter = { x: 0, y: 0 }; // 底边中心点
  
  // 计算三角形旋转角度 - 保持倒三角形状但根据方向旋转整体
  // 在雷达坐标系中: 0度→右, 90度(π/2)→下, 180度(π)→左, 270度(3π/2)→上
  const triangleRotation = speed > 0 ? direction : Math.PI/2; // 静止目标默认朝上
  
  // 应用旋转，计算三角形顶点
  let baseTrianglePoints: number[] = [];
  const rawTrianglePoints = [
    triangleTip.x, triangleTip.y,
    baseLeft.x, baseLeft.y,
    baseRight.x, baseRight.y,
    triangleTip.x, triangleTip.y
  ];
  
  // 旋转所有点
  for (let i = 0; i < rawTrianglePoints.length; i += 2) {
    const [rotatedX, rotatedY] = rotatePoint(
      rawTrianglePoints[i], 
      rawTrianglePoints[i + 1], 
      triangleRotation
    );
    baseTrianglePoints.push(rotatedX, rotatedY);
  }
  
  // 计算旋转后的底边中心点
  let rotatedBaseCenter = { ...baseCenter };
  if (speed > 0) {
    const [rotatedX, rotatedY] = rotatePoint(
      baseCenter.x, 
      baseCenter.y, 
      triangleRotation
    );
    rotatedBaseCenter = { x: rotatedX, y: rotatedY };
  }
  
  // ==================== 拖尾计算 ====================
  
  // 计算拖尾点
  const tailPoints = (() => {
    // 所有目标使用固定长度的拖尾
    const tailLength = 25;
    
    // 计算旋转后的三角形顶点（尖端）位置
    const [rotatedTipX, rotatedTipY] = rotatePoint(
      triangleTip.x, 
      triangleTip.y, 
      triangleRotation
    );
    
    // 计算旋转后的底边中心点位置
    const [rotatedCenterX, rotatedCenterY] = rotatePoint(
      baseCenter.x, 
      baseCenter.y, 
      triangleRotation
    );
    
    // 计算从底边中心到顶点的方向向量
    const directionX = rotatedTipX - rotatedCenterX;
    const directionY = rotatedTipY - rotatedCenterY;
    
    // 计算向量长度
    const vectorLength = Math.sqrt(directionX * directionX + directionY * directionY);
    
    // 归一化方向向量
    const normalizedDirX = directionX / vectorLength;
    const normalizedDirY = directionY / vectorLength;
    
    // 计算拖尾终点，沿着三角形中轴线的延长线
    const tailEndX = rotatedTipX + normalizedDirX * tailLength;
    const tailEndY = rotatedTipY + normalizedDirY * tailLength;
    
    // 拖尾从三角形顶点延伸到终点
    return [
      rotatedTipX, rotatedTipY, // 从三角形顶点开始拖尾
      tailEndX, tailEndY // 延伸到拖尾终点
    ];
  })();
  
  // ==================== 动画逻辑 ====================
  
  // 目标移动动画
  useEffect(() => {
    // 只有速度大于0才创建动画
    if (speed <= 0) return;
    
    // 记录开始时间
    let startTime = Date.now();
    console.log(`目标 ${id} 开始移动: 方向=${directionDegrees.toFixed(1)}°, 速度=${speed}`);
    
    // 移动动画函数
    const moveTarget = () => {
      // 计算时间差（秒）
      const now = Date.now();
      const deltaTime = (now - startTime) / 1000;
      startTime = now;
      
      // 速度调整系数 - 控制移动快慢
      // 值越小移动越慢，值越大移动越快
      const speedFactor = 0.1; // 调整这个值来控制速度
      
      // 根据原始speed和速度因子计算实际移动距离
      const moveDistance = speed * speedFactor * deltaTime;
      
      // 计算x和y的增量 - 方向计算已正确，保持不变
      // 在雷达坐标系中: cos(direction)计算x轴移动, sin(direction)计算y轴移动
      const dx = Math.cos(direction) * moveDistance;
      const dy = Math.sin(direction) * moveDistance;
      
      // 累加到当前偏移量
      setOffset(current => ({
        x: current.x + dx,
        y: current.y + dy
      }));
      
      // 每10帧输出一次位置信息
      if (Math.random() < 0.1) {
        console.log(`目标 ${id} 移动: 位置=(${displayPosition.x.toFixed(1)},${displayPosition.y.toFixed(1)}), 移动=(${dx.toFixed(1)},${dy.toFixed(1)})`);
      }
      
      // 继续下一帧动画
      animationFrameId.current = requestAnimationFrame(moveTarget);
    };
    
    // 启动动画
    animationFrameId.current = requestAnimationFrame(moveTarget);
    
    // 清理函数
    return () => {
      if (animationFrameId.current) {
        cancelAnimationFrame(animationFrameId.current);
        animationFrameId.current = null;
      }
    };
  }, [id, direction, speed]); // 当这些值变化时重启动画
  
  // 当原始位置变化时，重置偏移量
  useEffect(() => {
    // 注意：只有当position确实发生变化时才重置
    console.log(`目标 ${id} 位置重置检查: ${JSON.stringify(position)}`);
    // 重置累积的偏移量
    setOffset({ x: 0, y: 0 });
  }, [position.x, position.y, id]); // 只在原始位置变化时触发
  
  return (
    // 使用计算出的显示位置，而不是原始position
    <Group x={displayPosition.x} y={displayPosition.y}>
      {/* 拖尾 */}
      <Line
        points={tailPoints}
        stroke={color}
        strokeWidth={2}
        listening={false}
      />
      
      {/* 三角形 */}
      <Line
        points={baseTrianglePoints}
        closed={true}
        stroke={color}
        strokeWidth={2}
        fill={selected ? color : undefined}
      />
    </Group>
  );
};

export default UnknownTarget; 