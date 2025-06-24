import React from 'react';
import { Group, Line, Text } from 'react-konva';
import { RadarTarget } from '../hooks/useRadarData';

interface LiveTargetProps {
  target: RadarTarget;
  radarConfig: any;
  scanAngle?: number;
}

const LiveTarget: React.FC<LiveTargetProps> = ({ target, radarConfig, scanAngle = 60 }) => {
  // 根据威胁等级选择不同颜色
  const getThreatColor = (level: number) => {
    switch (level) {
      case 3: return '#ff0000'; // 高威胁 - 红色
      case 2: return '#ff9900'; // 中等威胁 - 橙色
      case 1: return '#ffff00'; // 低威胁 - 黄色
      default: return '#ffffff'; // 未知威胁 - 白色
    }
  };

  // 根据scanAngle计算缩放比例
  const getScale = () => {
    switch (scanAngle) {
      case 15: return 1.2;
      case 30: return 1.0;
      case 60: return 0.8;
      default: return 1.0;
    }
  };
  const scale = getScale();

  // 根据目标质量计算透明度
  const alpha = 0.5 + target.quality * 0.5;
  const color = getThreatColor(target.threat_level);

  // 将后端的笛卡尔坐标系角度 (direction) 转换为屏幕坐标系下的旋转角度（单位：度）
  // 我们的基础图标(>)的朝向是左边, 所以需要增加180度来对齐0度朝右的标准。
  const rotationDegrees = -target.direction * 180 / Math.PI + 180;

  return (
    <Group 
      x={target.x} 
      y={target.y} 
      rotation={rotationDegrees}
      opacity={alpha}
      scaleX={scale}
      scaleY={scale}
    >
      {/* 速度矢量线 / 拖尾 - 从顶点向后延伸 */}
      <Line
        points={[-15, 0, -15 - target.speed * 2, 0]} // 长度与速度相关
        stroke={color}
        strokeWidth={1.5}
      />
      
      {/* 目标三角形 - 底边朝前 */}
      <Line
        points={[
           0, 7,   // 底边上端点
           0, -7,  // 底边下端点
           -15, 0  // 顶点
        ]}
        closed={true}
        fill={color}
        stroke={color}
        strokeWidth={1}
      />
    </Group>
  );
};

export default LiveTarget; 