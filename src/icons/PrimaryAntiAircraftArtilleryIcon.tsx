import React from 'react';
import { Group, Circle, Line } from 'react-konva';

interface PrimaryAntiAircraftArtilleryIconProps {
  x: number;
  y: number;
  size?: number;
  color?: string;
  strokeWidth?: number;
}

const PrimaryAntiAircraftArtilleryIcon: React.FC<PrimaryAntiAircraftArtilleryIconProps> = ({
  x,
  y,
  size = 48,
  color = '#ff0000', // 红色
  strokeWidth = 3,
}) => {
  const center = size / 2;
  const radius = size * 0.35;
  const lineLen = size * 0.22;

  // 四周短线
  const lines = [
    // 上
    [center, center - radius - lineLen, center, center - radius],
    // 下
    [center, center + radius, center, center + radius + lineLen],
    // 左
    [center - radius - lineLen, center, center - radius, center],
    // 右
    [center + radius, center, center + radius + lineLen, center],
  ];

  // 向下偏移量
  const offsetY = radius * 0.35;

  // 圆内横线
  const innerLineY = center + offsetY;
  const innerLineLen = radius * 1.2;

  // 对号：以中点为顶点，左右两线夹角90度，左长右短
  const checkMidX = center;
  const checkMidY = center - radius * 0.15 + offsetY;
  // 左线：225°，较长
  const leftLen = radius * 0.7;
  const leftAngle = (225 * Math.PI) / 180;
  const checkStartX = checkMidX + leftLen * Math.cos(leftAngle);
  const checkStartY = checkMidY + leftLen * Math.sin(leftAngle);
  // 右线：315°，较短
  const rightLen = radius * 0.38;
  const rightAngle = (315 * Math.PI) / 180;
  const checkEndX = checkMidX + rightLen * Math.cos(rightAngle);
  const checkEndY = checkMidY + rightLen * Math.sin(rightAngle);

  return (
    <Group x={x} y={y}>
      {/* 空心圆 */}
      <Circle
        x={center}
        y={center}
        radius={radius}
        stroke={color}
        strokeWidth={strokeWidth}
      />
      {/* 四周短线 */}
      {lines.map((pts, idx) => (
        <Line key={idx} points={pts} stroke={color} strokeWidth={strokeWidth} lineCap="round" />
      ))}
      {/* 圆内横线 */}
      <Line
        points={[
          center - innerLineLen / 2,
          innerLineY,
          center + innerLineLen / 2,
          innerLineY,
        ]}
        stroke={color}
        strokeWidth={strokeWidth * 0.8}
        lineCap="round"
      />
      {/* 下方直角对号，左长右短，夹角90度 */}
      <Line
        points={[
          checkEndX, checkEndY, // 右上（短）
          checkMidX, checkMidY, // 顶点
          checkStartX, checkStartY, // 左下（长）
        ]}
        stroke={color}
        strokeWidth={strokeWidth * 0.8}
        lineCap="round"
        lineJoin="round"
      />
    </Group>
  );
};

export default PrimaryAntiAircraftArtilleryIcon; 