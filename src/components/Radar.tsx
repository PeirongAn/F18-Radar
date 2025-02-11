import React from 'react';
import RadarButtons from './RadarButtons';
import RadarDisplay from './RadarDisplay';
import { useKeyboardControl } from '../hooks/useKeyboardControl';

interface RadarProps {
  width?: number;
  height?: number;
}

const Radar: React.FC<RadarProps> = ({ width = 600, height = 600 }) => {
  const radarConfig = {
    backgroundColor: '#000000',
    gridColor: '#00ff00',
    textColor: '#00ff00',
    padding: 40,
    mainBoxWidth: 480,
    mainBoxHeight: 480,
    buttonSize: 30,  // 增大按钮尺寸
    buttonOffset: 15 // 按钮到显示区域的距离
  };

  // 计算主显示区域的边界位置
  const framePositions = {
    startX: (width - radarConfig.mainBoxWidth) / 2,
    startY: (height - radarConfig.mainBoxHeight) / 2,
    endX: (width + radarConfig.mainBoxWidth) / 2,
    endY: (height + radarConfig.mainBoxHeight) / 2
  };

  const tdcPosition = useKeyboardControl({
    initialPosition: { x: width / 2, y: height / 2 },
    moveStep: 5,
    boundaries: {
      minX: framePositions.startX + radarConfig.padding,
      maxX: framePositions.endX - radarConfig.padding,
      minY: framePositions.startY + radarConfig.padding,
      maxY: framePositions.endY - radarConfig.padding
    }
  });

  return (
    <div className="flex flex-col items-center gap-4 p-8 bg-neutral-900 rounded-lg shadow-lg mx-auto my-8">
      <RadarButtons position="top" framePositions={framePositions} radarConfig={radarConfig} />
      <div className="flex items-center gap-4">
        <RadarButtons position="left" framePositions={framePositions} radarConfig={radarConfig} />
        <RadarDisplay
          width={width}
          height={height}
          radarConfig={radarConfig}
          framePositions={framePositions}
          tdcPosition={tdcPosition}
        />
        <RadarButtons position="right" framePositions={framePositions} radarConfig={radarConfig} />
      </div>
      <RadarButtons position="bottom" framePositions={framePositions} radarConfig={radarConfig} />
    </div>
  );
};

export default Radar; 