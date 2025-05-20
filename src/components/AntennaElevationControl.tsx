import React, { useState, useEffect } from 'react';

interface AntennaElevationControlProps {
  currentElevation: number;
  onElevationChange: (elevation: number) => void;
  onConfirm: () => void;
  adjustmentRequired: boolean;
  targetElevation?: number; // 可选，用于显示目标高度
}

const AntennaElevationControl: React.FC<AntennaElevationControlProps> = ({
  currentElevation,
  onElevationChange,
  onConfirm,
  adjustmentRequired,
  targetElevation
}) => {
  // 使用本地状态跟踪当前高度，以便在拖动滑块时平滑更新UI
  const [localElevation, setLocalElevation] = useState(currentElevation);
  
  // 当外部currentElevation改变时，更新本地状态
  useEffect(() => {
    setLocalElevation(currentElevation);
  }, [currentElevation]);
  
  // 高度范围
  const minElevation = -30;
  const maxElevation = 50;
  
  // 处理滑块变化
  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = Number(e.target.value);
    setLocalElevation(newValue);
  };
  
  // 处理滑块拖动完成
  const handleSliderRelease = () => {
    onElevationChange(localElevation);
  };
  
  // 处理递增/递减按钮
  const handleIncrement = () => {
    const newValue = Math.min(maxElevation, localElevation + 1);
    setLocalElevation(newValue);
    onElevationChange(newValue);
  };
  
  const handleDecrement = () => {
    const newValue = Math.max(minElevation, localElevation - 1);
    setLocalElevation(newValue);
    onElevationChange(newValue);
  };
  
  // 计算高度差（若有目标高度）
  const elevationDifference = targetElevation !== undefined 
    ? localElevation - targetElevation
    : 0;
  
  // 确定颜色，根据与目标的接近度
  const getValueColor = () => {
    if (!adjustmentRequired || targetElevation === undefined) return 'text-green-400';
    
    const difference = Math.abs(elevationDifference);
    if (difference <= 2) return 'text-green-400'; // 在允许误差范围内
    if (difference <= 5) return 'text-yellow-300'; // 接近
    return 'text-red-400'; // 偏离较大
  };
  
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg p-3 w-full max-w-xs">
      <div className="text-center mb-2">
        <h3 className="text-green-400 font-mono text-lg">天线高度控制</h3>
        {adjustmentRequired && targetElevation !== undefined && (
          <div className="text-yellow-300 text-sm mt-1">
            请调整天线高度到 {targetElevation}°
          </div>
        )}
      </div>
      
      <div className="flex items-center justify-center mb-3">
        <button
          className="bg-gray-800 hover:bg-gray-700 text-white font-bold py-1 px-3 rounded-l"
          onClick={handleDecrement}
        >
          -
        </button>
        <div className={`text-xl font-bold mx-4 ${getValueColor()}`}>
          {localElevation}°
        </div>
        <button
          className="bg-gray-800 hover:bg-gray-700 text-white font-bold py-1 px-3 rounded-r"
          onClick={handleIncrement}
        >
          +
        </button>
      </div>
      
      <div className="mb-4">
        <input
          type="range"
          min={minElevation}
          max={maxElevation}
          step="1"
          value={localElevation}
          onChange={handleSliderChange}
          onMouseUp={handleSliderRelease}
          onTouchEnd={handleSliderRelease}
          className="w-full"
        />
        <div className="flex justify-between text-xs text-gray-500">
          <span>{minElevation}°</span>
          <span>0°</span>
          <span>{maxElevation}°</span>
        </div>
      </div>
      
      {adjustmentRequired && (
        <div className="text-center">
          <button
            className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded"
            onClick={onConfirm}
          >
            确认高度调整
          </button>
          {targetElevation !== undefined && (
            <div className="mt-2 text-sm">
              <span className="text-gray-400">当前误差: </span>
              <span className={Math.abs(elevationDifference) <= 2 ? 'text-green-400' : 'text-red-400'}>
                {elevationDifference > 0 ? '+' : ''}{elevationDifference.toFixed(1)}°
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default AntennaElevationControl; 