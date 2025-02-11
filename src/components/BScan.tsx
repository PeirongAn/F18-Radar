import React from 'react';
import { Line } from 'react-konva';

interface BScanProps {
  x: number;  // 水平位置
  startY: number;
  endY: number;
  color: string;
}

const BScan: React.FC<BScanProps> = ({ x, startY, endY, color }) => {
  return (
    <Line
      points={[x, startY, x, endY]}
      stroke={color}
      strokeWidth={1}
    />
  );
};

export default BScan; 