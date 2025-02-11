import React from 'react';
import { Group, Circle, Line } from 'react-konva';

interface VelocityVectorProps {
  x: number;
  y: number;
  color: string;
}

const VelocityVector: React.FC<VelocityVectorProps> = ({ x, y, color }) => {
  const radius = 8;
  const lineLength = 8;

  return (
    <Group x={x} y={y}>
      {/* 中心圆 */}
      <Circle
        radius={radius}
        stroke={color}
        strokeWidth={1}
      />
      
      {/* 上方线段 */}
      <Line
        points={[0, -radius, 0, -(radius + lineLength)]}
        stroke={color}
        strokeWidth={1}
      />
      
      {/* 左方线段 */}
      <Line
        points={[-radius, 0, -(radius + lineLength), 0]}
        stroke={color}
        strokeWidth={1}
      />
      
      {/* 右方线段 */}
      <Line
        points={[radius, 0, radius + lineLength, 0]}
        stroke={color}
        strokeWidth={1}
      />
    </Group>
  );
};

export default VelocityVector; 