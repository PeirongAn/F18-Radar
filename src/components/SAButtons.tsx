import React from 'react';
import { Group, Rect, Text } from 'react-konva';

interface SAButtonsProps {
  position: 'top' | 'left' | 'right';
  framePositions: {
    startX: number;
    startY: number;
    endX: number;
    endY: number;
  };
  radarConfig: any;
  stageWidth: number; // 添加舞台宽度属性
  stageHeight: number; // 添加舞台高度属性
  onResetSA?: () => void; // 新增重置回调
}

const SAButtons: React.FC<SAButtonsProps> = ({ 
  position, 
  framePositions, 
  radarConfig,
  stageWidth, 
  stageHeight,
  onResetSA
}) => {
  const { textColor = '#00ff00' } = radarConfig;
  
  // 按钮样式 - 增强按钮可见性
  const buttonStyle = {
    fill: '#1a1a1a',
    stroke: '#fff', // 绿色边框
    strokeWidth: 3, // 增加边框宽度
    cornerRadius: 5
  };
  
  // 按钮尺寸 - 增大按钮大小
  const buttonWidth = 50; // 从40增大到50
  const buttonHeight = 40; // 从30/40增大到40
  const buttonSpacing = 15; // 按钮间距
  const buttonMargin = 30; // 增加按钮与边框之间的边距
  
  // 每个位置的5个按钮
  const buttons = Array(5).fill(0).map((_, index) => {
    // 按钮标签
    let label = '';
    switch (position) {
      case 'top':
        label = `T${index + 1}`;
        break;
      case 'left':
        label = `L${index + 1}`;
        break;
      case 'right':
        label = `R${index + 1}`;
        break;
    }

    return { label, index };
  });

  // 计算按钮位置
  const getButtonPosition = (index: number) => {
    const totalButtons = 5;
    
    switch (position) {
      case 'top':
        // 上方按钮水平排列 - 放在边框上方
        const totalWidth = totalButtons * buttonWidth + (totalButtons - 1) * buttonSpacing; // 总宽度
        const startX = (framePositions.endX + framePositions.startX) / 2 - totalWidth / 2; // 水平居中
        
        return {
          x: startX + index * (buttonWidth + buttonSpacing),
          y: Math.max(20, framePositions.startY - buttonHeight - buttonMargin) // 确保按钮在可见区域内
        };
      
      case 'left':
        // 左侧按钮垂直排列 - 放在边框左侧
        const totalHeight = totalButtons * buttonHeight + (totalButtons - 1) * buttonSpacing; // 总高度
        const startY = (framePositions.endY + framePositions.startY) / 2 - totalHeight / 2; // 垂直居中
        
        return {
          x: Math.max(20, framePositions.startX - buttonWidth - buttonMargin), // 确保按钮在可见区域内
          y: startY + index * (buttonHeight + buttonSpacing)
        };
      
      case 'right':
        // 右侧按钮垂直排列 - 放在边框右侧
        const rightTotalHeight = totalButtons * buttonHeight + (totalButtons - 1) * buttonSpacing; // 总高度
        const rightStartY = (framePositions.endY + framePositions.startY) / 2 - rightTotalHeight / 2; // 垂直居中
        
        return {
          x: Math.min(stageWidth - buttonWidth - 20, framePositions.endX + buttonMargin), // 确保按钮在可见区域内
          y: rightStartY + index * (buttonHeight + buttonSpacing)
        };
        
      default:
        return { x: 0, y: 0 };
    }
  };

  return (
    <>
      {buttons.map(({ label, index }) => {
        const { x, y } = getButtonPosition(index);
        
        // 左侧第2个按钮（L2）点击时触发onResetSA
        const handleClick = () => {
          if (position === 'left' && index === 1 && onResetSA) {
            onResetSA();
          }
        };
        
        return (
          <Group key={`${position}-btn-${index}`} onClick={handleClick}>
            <Rect
              x={x}
              y={y}
              width={buttonWidth}
              height={buttonHeight}
              fill={buttonStyle.fill}
              stroke={buttonStyle.stroke}
              strokeWidth={buttonStyle.strokeWidth}
              cornerRadius={buttonStyle.cornerRadius}
            />
           
          </Group>
        );
      })}
    </>
  );
};

export default SAButtons; 