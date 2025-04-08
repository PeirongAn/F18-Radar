import React from 'react';
import { Line } from 'react-konva';

interface HorizonHUDProps {
  x: number;
  y: number;
  color: string;
}

const HorizonHUD: React.FC<HorizonHUDProps> = ({ x, y, color }) => {
  const lineLength = 60; // 每段线的长度
  const gapWidth = 30;   // 中间空档的宽度
  const dropLength = 8;  // 垂线长度
  
  return (
    <>
      {/* 左侧水平线 */}
      <Line
        points={[
          x - lineLength - gapWidth/2, y,  // 起点
          x - gapWidth/2, y               // 终点
        ]}
        stroke={color}
        strokeWidth={1}
      />
      
      {/* 右侧水平线 */}
      <Line
        points={[
          x + gapWidth/2, y,             // 起点
          x + lineLength + gapWidth/2, y  // 终点
        ]}
        stroke={color}
        strokeWidth={1}
      />

      {/* 左侧垂线 */}
      <Line
        points={[
          x - lineLength - gapWidth/2, y,     // 起点
          x - lineLength - gapWidth/2, y + dropLength  // 终点
        ]}
        stroke={color}
        strokeWidth={1}
      />

      {/* 右侧垂线 */}
      <Line
        points={[
          x + lineLength + gapWidth/2, y,     // 起点
          x + lineLength + gapWidth/2, y + dropLength  // 终点
        ]}
        stroke={color}
        strokeWidth={1}
      />
    </>
  );
};

export default HorizonHUD; 