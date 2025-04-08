import React from 'react';
import { Group, Line, Text } from 'react-konva';
import { RadarTarget } from '../hooks/useRadarData';

interface LiveTargetProps {
  target: RadarTarget;
  radarConfig: any;
}

const LiveTarget: React.FC<LiveTargetProps> = ({ target, radarConfig }) => {
  // 根据威胁等级选择不同颜色
  const getThreatColor = (level: number) => {
    switch (level) {
      case 3: return '#ff0000'; // 高威胁 - 红色
      case 2: return '#ff9900'; // 中等威胁 - 橙色
      case 1: return '#ffff00'; // 低威胁 - 黄色
      default: return '#ffffff'; // 未知威胁 - 白色
    }
  };

  // 根据目标质量计算透明度
  const alpha = 0.5 + target.quality * 0.5;
  const color = getThreatColor(target.threat_level);

  // 根据航向创建三角形
  const createTriangle = () => {
    // 定义基础三角形形状
    const trianglePoints = [
      [0, 1],       // 顶点
      [-0.8, -0.6], // 左下角
      [0.8, -0.6]   // 右下角
    ];

    // 旋转三角形以匹配目标航向
    // 注意：雷达中向上是北方(0度)，但在Canvas中向上是-90度
    const rotationAdjust = target.heading - 90;
    
    // 应用旋转变换
    const rotatedPoints = trianglePoints.map(point => {
      const [x, y] = point;
      const rad = (rotationAdjust * Math.PI) / 180;
      const cos = Math.cos(rad);
      const sin = Math.sin(rad);
      return [
        x * cos - y * sin,
        x * sin + y * cos
      ];
    });

    // 平移旋转后的三角形到目标位置
    return rotatedPoints.map(point => {
      return [
        target.x + point[0], 
        target.y + point[1]
      ];
    }).flat();
  };

  return (
    <Group>
      {/* 目标三角形 */}
      <Line
        points={createTriangle()}
        closed={true}
        fill={color}
        stroke={color}
        strokeWidth={0.5}
        opacity={alpha}
      />
      
      {/* 速度矢量线 - 表示目标运动方向 */}
      <Line
        points={[
          target.x, target.y,
          target.x + Math.sin(target.heading * Math.PI / 180) * (target.speed / 100),
          target.y + Math.cos(target.heading * Math.PI / 180) * (target.speed / 100)
        ]}
        stroke={color}
        strokeWidth={0.5}
        opacity={alpha * 0.8}
      />
      
      {/* 目标ID显示 */}
      <Text
        text={`${target.id}`}
        x={target.x + 1.2}
        y={target.y - 0.6}
        fill={color}
        fontSize={10}
        opacity={alpha}
      />
      
      {/* 历史轨迹点 */}
      {target.history.map((pos, index) => (
        <Line
          key={`hist-${target.id}-${index}`}
          points={[pos[0], pos[1], pos[0], pos[1]]}
          stroke={color}
          strokeWidth={0.3}
          opacity={(index + 1) / target.history.length * 0.6 * alpha}
          lineCap="round"
        />
      ))}
    </Group>
  );
};

export default LiveTarget; 