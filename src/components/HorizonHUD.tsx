import React from 'react';
import { Group, Line } from 'react-konva';

interface HorizonHUDProps {
  x: number;
  y: number;
  color: string;
}

const HorizonHUD: React.FC<HorizonHUDProps> = ({ x, y, color }) => {
  const width = 180;  // 主线段长度
  const dropLength = 8;  // 下垂线段长度

  return (
    <Group x={x} y={y}>
      {/* 主水平线 */}
      <Line
        points={[-width/2, 0, width/2, 0]}
        stroke={color}
        strokeWidth={1}
      />
      
      {/* 左侧下垂线 */}
      <Line
        points={[-width/2, 0, -width/2, dropLength]}
        stroke={color}
        strokeWidth={1}
      />
      
      {/* 右侧下垂线 */}
      <Line
        points={[width/2, 0, width/2, dropLength]}
        stroke={color}
        strokeWidth={1}
      />
    </Group>
  );
};

export default HorizonHUD; 