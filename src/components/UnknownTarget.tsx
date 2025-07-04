import React, { useEffect, useState, useRef } from 'react';
import { Group, Line, Text } from 'react-konva';
import radarStore from '../stores/RadarStore'; // <--- 导入 RadarStore

// 定义未知目标数据接口
export interface UnknownTargetData {
  id: string;                       // 目标唯一标识
  position: { x: number, y: number }; // 当前位置
  history: { x: number, y: number }[]; // 历史位置记录
  speed: number;                    // 目标速度
  direction: number;                // 运动方向（弧度）
  direction_degrees?: number;       // 预处理的导航坐标系角度（度数）
  type: 'friend' | 'army'; // 目标类型
  selected?: boolean;               // 添加选中状态标记
  trail_length?: number;            // 新增：拖尾长度
  threat_score?: number;            // 后端计算的威胁评分
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
  scanAngle?: number;
  onTargetClick?: (target: UnknownTargetData) => void; // 添加点击事件回调
}

const UnknownTarget: React.FC<UnknownTargetProps> = ({ data, color, framePositions, scanAngle = 60, onTargetClick }) => {
  // 从props解构需要的属性
  const { id, direction, type, speed, selected, position } = data;
  
  // // 根据scanAngle计算缩放比例
  // const getScale = () => {
  //   switch (scanAngle) {
  //     case 15: return 1.2;
  //     case 30: return 1.0;
  //     case 60: return 0.8;
  //     default: return 1.0;
  //   }
  // };
  // const scale = getScale();
  
  // 简化状态，只用一个状态跟踪偏移量，而不是完整的位置
  // 这样即使原始position发生变化，也不会影响偏移量的累加
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  
  // 使用useRef记录动画ID
  const animationFrameId = useRef<number | null>(null);
  
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
  
  // 当 displayPosition 更新时，将其报告给 RadarStore
  useEffect(() => {
    radarStore.setTargetDisplayPosition(id, displayPosition);

    // 组件卸载时，从 Store 中移除该目标的位置信息
    return () => {
      radarStore.removeTargetDisplayPosition(id);
      // console.log(`[UnknownTarget ${id}] Removed displayPosition from store.`);
    };
  }, [id, displayPosition.x, displayPosition.y]); // 依赖项包含 displayPosition 的变化
  
  // 临时去掉目标移动动画
  // useEffect(() => {
  //   // 只有速度大于0才创建动画
  //   if (speed <= 0) return;
    
  //   // 记录开始时间
  //   let startTime = Date.now();
  //   // console.log(`[UnknownTarget ${id}] Animation started: dir=${directionDegrees.toFixed(1)}°, speed=${speed}`);
    
  //   // 移动动画函数
  //   const moveTarget = () => {
  //     // 计算时间差（秒）
  //     const now = Date.now();
  //     const deltaTime = (now - startTime) / 1000;
  //     startTime = now;
      
  //     // 速度调整系数 - 控制移动快慢
  //     // 值越小移动越慢，值越大移动越快
  //     const speedFactor = 0.1; // 调整这个值来控制速度
      
  //     // 根据原始speed和速度因子计算实际移动距离
  //     const moveDistance = speed * speedFactor * deltaTime;
      
  //     // 计算x和y的增量
  //     // direction是笛卡尔坐标系角度，但屏幕坐标系Y轴是反的，所以sin(direction)需要取反才能得到正确的Y轴移动
  //     const dx = Math.cos(direction) * moveDistance;
  //     const dy = -Math.sin(direction) * moveDistance;
      
  //     // 累加到当前偏移量
  //     setOffset(current => ({
  //       x: current.x + dx,
  //       y: current.y + dy
  //     }));
      
  //     // 每10帧输出一次位置信息
  //     // if (Math.random() < 0.1) {
  //     //   console.log(`目标 ${id} 移动: 位置=(${displayPosition.x.toFixed(1)},${displayPosition.y.toFixed(1)}), 移动=(${dx.toFixed(1)},${dy.toFixed(1)})`);
  //     // }
      
  //     // 继续下一帧动画
  //     animationFrameId.current = requestAnimationFrame(moveTarget);
  //   };
    
  //   // 启动动画
  //   animationFrameId.current = requestAnimationFrame(moveTarget);
    
  //   // 清理函数
  //   return () => {
  //     if (animationFrameId.current) {
  //       cancelAnimationFrame(animationFrameId.current);
  //       animationFrameId.current = null;
  //       // console.log(`[UnknownTarget ${id}] Animation cancelled.`);
  //     }
  //   };
  // }, [id, direction, speed]); // 当这些值变化时重启动画
  
  // 当原始位置变化时，重置偏移量
  useEffect(() => {
    // 注意：只有当position确实发生变化时才重置
    // console.log(`[UnknownTarget ${id}] Position prop changed: ${JSON.stringify(position)}. Resetting offset.`);
    setOffset({ x: 0, y: 0 });
  }, [position.x, position.y, id]); // 只在原始位置变化时触发
  
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
  
  // 处理目标点击事件
  const handleTargetClick = () => {
    if (onTargetClick) {
      onTargetClick(data);
    }
  };

  // 使用后端预处理的导航坐标系角度，不再需要前端转换
  // 后端已经将数学坐标系转换为导航坐标系角度（0°=北, 90°=东, 180°=南, 270°=西）
  const rotationDegrees = data.direction_degrees || 0;
  
  return (
    // 使用计算出的显示位置，而不是原始position
    // 将旋转应用于整个Group，这样三角形和拖尾都会一起旋转
    <Group 
      x={displayPosition.x} 
      y={displayPosition.y}
      rotation={rotationDegrees - 90}
      scaleX={1}
      scaleY={1}
      onClick={handleTargetClick}
      onTap={handleTargetClick}
    >
      {/* 拖尾 - 从顶点向后延伸 */}
      <Line
        points={[-15, 0, -15 - (data.trail_length ?? 25), 0]} // 优先使用trail_length, 否则使用默认值25
        stroke={color}
        strokeWidth={1.5}
        opacity={0.6}
        lineCap="round"
      />
      
      {/* 目标三角形 - 底边在前方(右侧)，顶点在后(左侧) */}
      <Line
        points={[
           0, 7,   // 底边上端点
           0, -7,  // 底边下端点
           -15, 0  // 顶点
        ]}
        closed={true}
        fill={selected ? 'white' : color} // 选中时高亮为白色
        stroke={color}
        strokeWidth={1}
        shadowColor={selected ? 'cyan' : 'transparent'} // 选中时发光
        shadowBlur={selected ? 10 : 0}
      />
    </Group>
  );
};

export default UnknownTarget; 