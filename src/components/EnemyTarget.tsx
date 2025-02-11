import React from 'react';
import { Rect } from 'react-konva';

interface EnemyTargetProps {
  x: number;
  y: number;
  color: string;
  size?: number;  // 可选的尺寸参数
}

const EnemyTarget: React.FC<EnemyTargetProps> = ({ 
  x, 
  y, 
  color, 
  size = 10  // 默认大小为10x10
}) => {
  return (
    <Rect
      x={x - size/2}  // 居中显示
      y={y - size/2}
      width={size}
      height={size}
      fill={color}
    />
  );
};

export default EnemyTarget; 