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
    backgroundColor: 'rgba(0,14,6,0.9)',
    border: '1px solid #0d3018',
    borderRadius: '2px',
    cursor: 'pointer',
    boxShadow: 'inset 0 0 5px rgba(0,80,30,0.12)',
    transition: 'background 0.15s, box-shadow 0.15s',
    outline: 'none',
  };

  // 处理按钮点击事件
  const handleClick = (buttonIndex: number) => {
    if (onButtonClick) {
      onButtonClick(position, buttonIndex);
    }
    console.log(`${position} button ${buttonIndex} clicked`);
  };

  // 处理键盘事件，阻止Enter键触发按钮点击
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      // e.stopPropagation();
    }
  };

  return (
    <div style={containerStyle}>
      {[1, 2, 3, 4, 5].map((i) => (
        <button
          key={`${position}-${i}`}
          style={buttonStyle}
          onClick={() => handleClick(i)}
          onKeyDown={handleKeyDown}
          onMouseEnter={e => {
            const btn = e.currentTarget as HTMLButtonElement;
            btn.style.backgroundColor = 'rgba(0,30,12,0.95)';
            btn.style.boxShadow = '0 0 6px rgba(0,160,60,0.18), inset 0 0 5px rgba(0,100,40,0.2)';
            btn.style.borderColor = '#3a9a50';
          }}
          onMouseLeave={e => {
            const btn = e.currentTarget as HTMLButtonElement;
            btn.style.backgroundColor = 'rgba(0,14,6,0.9)';
            btn.style.boxShadow = 'inset 0 0 5px rgba(0,80,30,0.12)';
            btn.style.borderColor = '#0d3018';
          }}
        />
      ))}
    </div>
  );
};

export default RadarButtons; 