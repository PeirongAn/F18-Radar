import React from 'react';
import { Group, Line, Circle } from 'react-konva';

interface MissileUpIconProps {
  x: number;
  y: number;
  size?: number;
  color?: string;
  strokeWidth?: number;
}

const MissileUpIcon: React.FC<MissileUpIconProps> = ({
  x,
  y,
  size = 20,
  color = '#ff0000',
  strokeWidth = 3,
}) => {
  // 计算导弹主体尺寸
  const bodyWidth = size * 0.4;
  const bodyHeight = size * 0.8;
  
  // 计算导弹头部尺寸
  const headWidth = size * 0.6;
  const headHeight = size * 0.3;
  
  // 计算导弹尾部尺寸
  const tailWidth = size * 0.3;
  const tailHeight = size * 0.2;

  return (
    <Group x={x} y={y}>
      {/* 导弹主体 */}
      <Line
        points={[
          -bodyWidth/2, bodyHeight/2,
          -bodyWidth/2, -bodyHeight/2,
          bodyWidth/2, -bodyHeight/2,
          bodyWidth/2, bodyHeight/2,
        ]}
        closed
        stroke={color}
        strokeWidth={strokeWidth}
      />
      
      {/* 导弹头部 */}
      <Line
        points={[
          -headWidth/2, -bodyHeight/2,
          0, -bodyHeight/2 - headHeight,
          headWidth/2, -bodyHeight/2,
        ]}
        closed
        stroke={color}
        strokeWidth={strokeWidth}
      />
      
      {/* 导弹尾部 */}
      <Line
        points={[
          -tailWidth/2, bodyHeight/2,
          0, bodyHeight/2 + tailHeight,
          tailWidth/2, bodyHeight/2,
        ]}
        closed
        stroke={color}
        strokeWidth={strokeWidth}
      />
      
      {/* 导弹尾焰 */}
      <Line
        points={[
          -tailWidth/3, bodyHeight/2 + tailHeight,
          0, bodyHeight/2 + tailHeight * 1.5,
          tailWidth/3, bodyHeight/2 + tailHeight,
        ]}
        stroke={color}
        strokeWidth={strokeWidth}
      />
    </Group>
  );
};

export default MissileUpIcon; 