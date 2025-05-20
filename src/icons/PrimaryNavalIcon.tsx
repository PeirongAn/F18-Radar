import React from 'react';
import { Group, Circle, Line } from 'react-konva';

interface PrimaryNavalIconProps {
  x: number;
  y: number;
  size?: number;
  color?: string;
  strokeWidth?: number;
}

const PrimaryNavalIcon: React.FC<PrimaryNavalIconProps> = ({
  x,
  y,
  size = 64,
  color = '#ff0000', // 红色
  strokeWidth = 3,
}) => {
  const center = size / 2;
  const radius = size * 0.38;
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

  // 向上整体偏移量
  const offsetY = -size * 0.09;

  // 船体（正梯形，上宽下窄）
  const trapWidthTop = size * 0.62;
  const trapWidthBottom = size * 0.38;
  const trapHeight = size * 0.16;
  const trapY = center + size * 0.18 + offsetY;
  const trapPoints = [
    center - trapWidthTop / 2, trapY, // 左上
    center + trapWidthTop / 2, trapY, // 右上
    center + trapWidthBottom / 2, trapY + trapHeight, // 右下
    center - trapWidthBottom / 2, trapY + trapHeight, // 左下
    center - trapWidthTop / 2, trapY // 闭合
  ];

  // 对钩（右侧，直角，镜像）
  const checkMidX = center + size * 0.12;
  const checkMidY = trapY;
  // 右线：315°，较短
  const rightLen = size * 0.18;
  const rightAngle = (315 * Math.PI) / 180;
  const checkEndX = checkMidX + rightLen * Math.cos(rightAngle);
  const checkEndY = checkMidY + rightLen * Math.sin(rightAngle);
  // 左线：225°，较长
  const leftLen = size * 0.28;
  const leftAngle = (225 * Math.PI) / 180;
  const checkStartX = checkMidX + leftLen * Math.cos(leftAngle);
  const checkStartY = checkMidY + leftLen * Math.sin(leftAngle);

  // 梯形左侧平行线（起点为梯形上长边左上角，方向与对钩长边平行，长度略短于对钩长边）
  const parallelStartX = center - trapWidthTop / 6;
  const parallelStartY = trapY;
  const parallelLen = leftLen * 0.6;
  const parallelAngle = leftAngle;
  const parallelEndX = parallelStartX + parallelLen * Math.cos(parallelAngle);
  const parallelEndY = parallelStartY + parallelLen * Math.sin(parallelAngle);

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
      {/* 船体（正梯形，上宽下窄） */}
      <Line
        points={trapPoints}
        closed
        stroke={color}
        strokeWidth={strokeWidth}
        lineJoin="round"
      />
      {/* 对钩（右侧，直角，镜像） */}
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
      {/* 梯形左侧平行线（起点为梯形上长边左上角） */}
      <Line
        points={[
          parallelStartX, parallelStartY,
          parallelEndX, parallelEndY,
        ]}
        stroke={color}
        strokeWidth={strokeWidth * 0.8}
        lineCap="round"
      />
    </Group>
  );
};

export default PrimaryNavalIcon; 