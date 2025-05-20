import React from 'react';
import { Group, Rect, Line, Text } from 'react-konva';

interface PrimaryAirIconProps {
  x: number;
  y: number;
  size?: number;
  color?: string;
  strokeWidth?: number;
  label?: string;
}

const PrimaryAirIcon: React.FC<PrimaryAirIconProps> = ({
  x,
  y,
  size = 48,
  color = '#ff0000', // 红色
  strokeWidth = 3,
  label,
}) => {
  const rectWidth = size;
  const rectHeight = size * 0.5;
  const center = size / 2;
  const rectX = 0;
  const rectY = center - rectHeight / 2;
  const lineLen = size * 0.22;

  return (
    <Group x={x} y={y}>
      {/* 空心矩形 */}
      <Rect
        x={rectX}
        y={rectY}
        width={rectWidth}
        height={rectHeight}
        stroke={color}
        strokeWidth={strokeWidth}
        fillEnabled={false}
        cornerRadius={2}
      />
      {/* 上短线 */}
      <Line
        points={[center, rectY - lineLen, center, rectY]}
        stroke={color}
        strokeWidth={strokeWidth}
      />
      {/* 下短线 */}
      <Line
        points={[center, rectY + rectHeight, center, rectY + rectHeight + lineLen]}
        stroke={color}
        strokeWidth={strokeWidth}
      />
      {/* 左短线 */}
      <Line
        points={[rectX - lineLen, center, rectX, center]}
        stroke={color}
        strokeWidth={strokeWidth}
      />
      {/* 右短线 */}
      <Line
        points={[rectX + rectWidth, center, rectX + rectWidth + lineLen, center]}
        stroke={color}
        strokeWidth={strokeWidth}
      />
      {/* 型号字母 */}
      {label && (
        <Text
          text={label}
          x={rectX}
          y={rectY}
          width={rectWidth}
          height={rectHeight}
          align="center"
          verticalAlign="middle"
          fontSize={rectHeight * 0.7}
          fill={color}
          fontStyle="bold"
        />
      )}
    </Group>
  );
};

export default PrimaryAirIcon; 