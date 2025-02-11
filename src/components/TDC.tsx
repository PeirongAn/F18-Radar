import React from 'react';
import { Group, Line, Text } from 'react-konva';

interface TDCProps {
  x: number;
  y: number;
  color: string;
  upperValue: string;
  lowerValue: string;
}

const TDC: React.FC<TDCProps> = ({ x, y, color, upperValue, lowerValue }) => {
  const lineHeight = 15; // 竖线高度
  const gap = 16; // 两条线之间的水平间隔
  const lineWidth = 1; // 线条宽度
  
  return (
    <Group x={x} y={y}>
      {/* 左侧竖线 */}
      <Line
        points={[-gap/2, -lineHeight/2, -gap/2, lineHeight/2]}
        stroke={color}
        strokeWidth={lineWidth}
      />
      {/* 右侧竖线 */}
      <Line
        points={[gap/2, -lineHeight/2, gap/2, lineHeight/2]}
        stroke={color}
        strokeWidth={lineWidth}
      />
      {/* 上方高度值 */}
      <Text
        text={upperValue}
        x={-8}
        y={-lineHeight/2 - 12}
        fill={color}
        fontSize={12}
        align="center"
      />
      {/* 下方高度值 */}
      <Text
        text={lowerValue}
        x={-8}
        y={lineHeight/2}
        fill={color}
        fontSize={12}
        align="center"
      />
    </Group>
  );
};

export default TDC; 