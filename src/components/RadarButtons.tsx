import React from 'react';

interface RadarButtonsProps {
  position: 'top' | 'bottom' | 'left' | 'right';
  framePositions: {
    startX: number;
    startY: number;
    endX: number;
    endY: number;
  };
  radarConfig: any;
  onButtonClick?: (position: string, buttonIndex: number) => void;
}

const RadarButtons: React.FC<RadarButtonsProps> = ({ position, framePositions, radarConfig, onButtonClick }) => {
  const { startX, startY, endX, endY } = framePositions;
  const isVertical = position === 'left' || position === 'right';
  
  // 计算按钮容器的样式，增加padding来扩大整体尺寸
  const containerStyle: React.CSSProperties = {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    ...(isVertical ? {
      flexDirection: 'column',
      height: `${endY - startY + 80}px`, // 增加高度以增加按钮间距
      width: '40px',
      margin: position === 'left' ? '0 15px 0 0' : '0 0 0 15px',
      padding: '15px 0' // 垂直方向增加内边距
    } : {
      width: `${endX - startX + 80}px`, // 增加宽度以增加按钮间距
      height: '40px',
      margin: position === 'top' ? '0 0 15px 0' : '15px 0 0 0'
    })
  };

  // 按钮样式
  const buttonStyle: React.CSSProperties = {
    width: '36px',
    height: '36px',
    backgroundColor: '#333333',
    border: '1px solid #444444',
    borderRadius: '2px',
    cursor: 'pointer'
  };

  // 处理按钮点击事件
  const handleClick = (buttonIndex: number) => {
    if (onButtonClick) {
      onButtonClick(position, buttonIndex);
    }
    console.log(`${position} button ${buttonIndex} clicked`);
  };

  return (
    <div style={containerStyle}>
      {[1, 2, 3, 4, 5].map((i) => (
        <button 
          key={`${position}-${i}`}
          style={buttonStyle}
          onClick={() => handleClick(i)}
        />
      ))}
    </div>
  );
};

export default RadarButtons; 