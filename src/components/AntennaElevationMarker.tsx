import React, { useEffect } from 'react';
import { Group, Line } from 'react-konva';
import { useKeyboardControl } from '../hooks/useKeyboardControl';
import radarStore from '../stores/RadarStore';

interface AntennaElevationMarkerProps {
  x: number;
  y: number;
  color: string;
  minY: number;  // 最小Y位置（对应-3）
  maxY: number;  // 最大Y位置（对应3）
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
    moveStep: (maxY - minY) / 60, // 每次移动一个刻度
    boundaries: {
      minX: x,
      maxX: x,
      minY: minY,
      maxY: maxY
    },
    controls: {
      up: 't',     // 使用t键向上移动
      down: 'b',   // 使用b键向下移动
      left: '',    // 禁用左右移动
      right: ''
    }
  });

  // 计算当前值并更新store
  useEffect(() => {
    const totalHeight = maxY - minY;
    const position = markerY - minY;
    const value = -Math.round((position / totalHeight) * 6 - 3);
    radarStore.setCurrentAntennaElevation(value);
  }, [markerY, minY, maxY]);

  return (
    <>
      {/* 刻度线 - 6等分 */}
      {Array.from({ length: 7 }, (_, i) => {
        const scaleY = minY + ((maxY - minY) * i) / 6;
        return (
          <Group key={i} y={scaleY} x={x}>
            <Line
              points={[-30, 0, -20, 0]}
              stroke={color}
              strokeWidth={1}
            />
          </Group>
        );
      })}

      {/* 箭头标记 */}
      <Group x={x} y={markerY}>
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