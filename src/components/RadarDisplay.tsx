import React from 'react';
import { Stage, Layer } from 'react-konva';
import { renderMainFrame, renderText } from './RadarRenderers';

interface RadarDisplayProps {
  width: number;
  height: number;
  radarConfig: any;
  framePositions: {
    startX: number;
    startY: number;
    endX: number;
    endY: number;
  };
  tdcPosition: { x: number; y: number };
}

const RadarDisplay: React.FC<RadarDisplayProps> = ({ 
  width, 
  height, 
  radarConfig, 
  framePositions,
  tdcPosition 
}) => {
  return (
    <div className="radar-container" style={{ borderRadius: '48px' }}>
      <Stage width={width} height={height}>
        <Layer>
          {renderMainFrame({ width, height, radarConfig, framePositions, tdcPosition })}
          {renderText({ width, height, radarConfig, framePositions })}
        </Layer>
      </Stage>
    </div>
  );
};

export default RadarDisplay; 