import React from 'react';
import { Group, Line } from 'react-konva';
import { useKeyboardControl } from '../hooks/useKeyboardControl';

interface AntennaElevationMarkerProps {
  x: number;
  y: number;
  color: string;
  minY: number;  // 最小Y位置（对应第一个刻度）
  maxY: number;  // 最大Y位置（对应第三个刻度）
}

const AntennaElevationMarker: React.FC<AntennaElevationMarkerProps> = ({
  x,
  y,
  color,
  minY,
  maxY
}) => {
  const { y: markerY } = useKeyboardControl({
    initialPosition: { x, y },
    moveStep: 5,
    boundaries: {
      minX: x,
      maxX: x,
      minY: minY,
      maxY: maxY
    },
    controls: {
      up: 'b',     // 使用b键向上移动
      down: 't',   // 使用t键向下移动
      left: '',    // 禁用左右移动
      right: ''
    }
  });

  return (
    <>
      {/* 刻度线 - 8等分 */}
      {Array.from({ length: 9 }, (_, i) => {
        const scaleY = minY + ((maxY - minY) * i) / 8;
        return (
          <Group key={i} y={scaleY} x={x}>
            <Line
              points={i%4 === 0 ? [-30, 0, -20, 0] : [-25, 0, -20, 0]}
              stroke={color}
              strokeWidth={1}
            />
          </Group>
        );
      })}

      {/* 箭头标记 */}
      <Group x={x} y={markerY}>
        {/* 箭头（只有两条斜线，指向左侧） */}
        <Line
          points={[-10, -5, -20, 0, -10, 5]}
          stroke={color}
          strokeWidth={1}
        />
      </Group>
    </>
  );
};

export default AntennaElevationMarker; 