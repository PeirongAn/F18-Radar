import React, { useEffect, useCallback } from 'react';
import { Group, Line } from 'react-konva';
import { observer } from 'mobx-react-lite';
import { useKeyboardControl } from '../hooks/useKeyboardControl';
import radarStore from '../stores/RadarStore';
import agentStore from '../stores/AgentStore';

interface AntennaElevationMarkerProps {
  x: number;
  minY: number;  // 最小Y位置（对应-3度或最低逻辑值）
  maxY: number;  // 最大Y位置（对应3度或最高逻辑值）
  color: string;
  sendMessage: (message: any) => void;
  joystickEnabled?: boolean; // 是否启用摇杆控制
}

// Helper to map elevation value to Y coordinate
const mapElevationToY = (elevation: number, minY: number, maxY: number, minVal: number = -3, maxVal: number = 3): number => {
  const totalHeight = maxY - minY;
  const totalValueRange = maxVal - minVal;
  if (totalValueRange === 0) return minY + totalHeight / 2; // Avoid division by zero
  const valueRatio = (elevation - minVal) / totalValueRange;
  return maxY - (valueRatio * totalHeight); // Inverted: higher value means lower Y on screen typically
};

// Helper to map Y coordinate to elevation value
const mapYToElevation = (yPos: number, minY: number, maxY: number, minVal: number = -3, maxVal: number = 3): number => {
  const totalHeight = maxY - minY;
  if (totalHeight === 0) return minVal + (maxVal - minVal) / 2; // Avoid division by zero
  const positionRatio = (maxY - yPos) / totalHeight; // Inverted from mapElevationToY
  return Math.round(minVal + (positionRatio * (maxVal - minVal))); // Round to nearest integer degree
}

const AntennaElevationMarker: React.FC<AntennaElevationMarkerProps> = observer(({
  x,
  minY,
  maxY,
  color,
  sendMessage,
  joystickEnabled = false,
}) => {
  // Marker Y position is now derived from the store's currentAntennaElevation
  const currentElevation = radarStore.currentAntennaElevation;
  // Convert store's elevation value (-3 to 3) to a Y coordinate for the marker
  const markerY = mapElevationToY(currentElevation, minY, maxY);

  const handleKeyAction = useCallback((action: 'up' | 'down' | 'left' | 'right') => {
    let newElevation = radarStore.currentAntennaElevation;
    if (action === 'up') { // 't' key
      newElevation = Math.min(3, radarStore.currentAntennaElevation + 1); // Max +3 degrees
    } else if (action === 'down') { // 'b' key
      newElevation = Math.max(-3, radarStore.currentAntennaElevation - 1); // Min -3 degrees
    } else {
      return; // Ignore left/right for this marker
    }

    // Pass 'user' as source and the sendMessage callback
    radarStore.setCurrentAntennaElevation(newElevation, 'user', sendMessage);
    // No need to reset owner to manual here as it should persist for user actions unless AI takes over

  }, [sendMessage]); // radarStore is a singleton, stable. Dependencies are implicit.

  // 只有在摇杆控制未启用时才启用键盘控制
  useKeyboardControl({
    // moveStep is now conceptual, actual step is +1 or -1 degree in handleKeyAction
    // We can pass a nominal moveStep if the hook expects it, but it won't be used to calculate position directly here.
    moveStep: 1, // Placeholder, actual logic is in handleKeyAction
    boundaries: { // Boundaries for context if hook uses them, not for position clamping here
      minY: minY, // Logical min Y
      maxY: maxY, // Logical max Y
    },
    controls: {
      up: 't',
      down: 'b',
      // Left/Right are ignored by handleKeyAction
    },
    onKeyAction: joystickEnabled ? () => {} : handleKeyAction, // 摇杆控制启用时禁用键盘控制
  });

  // No useEffect to update store from markerY, as markerY is derived from store.
  // The store is the source of truth.

  return (
    <>
      {/* 刻度线 - 6等分, assuming -3 to +3 degrees (7 lines) */}
      {Array.from({ length: 7 }, (_, i) => {
        const val = 3 - i; // Values from 3 down to -3
        const scaleY = mapElevationToY(val, minY, maxY);
        return (
          <Group key={`scale-${val}`} y={scaleY} x={x}>
            <Line
              points={[-30, 0, -20, 0]}
              stroke={color}
              strokeWidth={1}
            />
            {/* Optional: Add text labels for degrees here */}
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
});

export default AntennaElevationMarker; 