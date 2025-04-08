import React from 'react';
import { Stage, Layer, Circle, Line, Text, Group, Rect, Arc } from 'react-konva';

interface NavigationHUDProps {
  width: number;
  height: number;
}

const NavigationHUD: React.FC<NavigationHUDProps> = ({ width, height }) => {
  const hudConfig = {
    backgroundColor: '#000000',
    textColor: '#00ff00',
    lineColor: '#00ff00',
    centerX: width / 2,
    centerY: height / 2,
    padding: 60, // 增加内边距，使内容更居中
  };

  // 计算实际可用区域
  const contentWidth = width - (hudConfig.padding * 2);
  const contentHeight = height - (hudConfig.padding * 2);
  const contentStartX = hudConfig.padding;
  const contentStartY = hudConfig.padding;

  // 生成圆形刻度
  const renderCircularScale = () => {
    const radius = Math.min(contentWidth, contentHeight) / 2 - 20;
    const tickCount = 36; // 每10度一个刻度
    const elements = [];
    
    // 添加主圆
    elements.push(
      <Circle
        key="main-circle"
        x={hudConfig.centerX}
        y={hudConfig.centerY}
        radius={radius}
        stroke={hudConfig.lineColor}
        strokeWidth={1}
      />
    );
    
    // 添加刻度线
    for (let i = 0; i < tickCount; i++) {
      const angle = (i * 360) / tickCount;
      const radian = (angle * Math.PI) / 180;
      const tickLength = i % 3 === 0 ? 10 : 5; // 每30度的刻度线更长
      
      const innerX = hudConfig.centerX + (radius - tickLength) * Math.sin(radian);
      const innerY = hudConfig.centerY - (radius - tickLength) * Math.cos(radian);
      const outerX = hudConfig.centerX + radius * Math.sin(radian);
      const outerY = hudConfig.centerY - radius * Math.cos(radian);
      
      elements.push(
        <Line
          key={`tick-${i}`}
          points={[innerX, innerY, outerX, outerY]}
          stroke={hudConfig.lineColor}
          strokeWidth={1}
        />
      );
      
      // 每30度添加数字标签
      if (i % 3 === 0) {
        const labelRadius = radius + 15;
        const labelX = hudConfig.centerX + labelRadius * Math.sin(radian);
        const labelY = hudConfig.centerY - labelRadius * Math.cos(radian);
        const heading = (i * 10) % 360; // 0-350度
        
        elements.push(
          <Text
            key={`label-${i}`}
            text={heading.toString().padStart(3, '0')}
            x={labelX - 12}
            y={labelY - 8}
            fill={hudConfig.textColor}
            fontSize={12}
            align="center"
          />
        );
      }
    }
    
    return elements;
  };

  return (
    <div className="navigation-hud" style={{ width, height, backgroundColor: hudConfig.backgroundColor }}>
      <Stage width={width} height={height}>
        <Layer>
          {/* 圆形刻度 */}
          {renderCircularScale()}
          
          {/* 顶部菜单 */}
          <Text text="MAP" x={contentStartX + 30} y={contentStartY + 10} fill={hudConfig.textColor} fontSize={16} />
          <Text text="DCLTR" x={contentStartX + contentWidth/4} y={contentStartY + 10} fill={hudConfig.textColor} fontSize={16} />
          <Text text="SCL/20" x={contentStartX + contentWidth/2} y={contentStartY + 10} fill={hudConfig.textColor} fontSize={16} />
          <Text text="MK2" x={contentStartX + (contentWidth*3)/4} y={contentStartY + 10} fill={hudConfig.textColor} fontSize={16} />
          
          {/* 右上角信息 */}
          <Text text="DCNTR" x={contentStartX + contentWidth - 100} y={contentStartY + 10} fill={hudConfig.textColor} fontSize={16} />
          <Text text="173/" x={contentStartX + contentWidth - 100} y={contentStartY + 30} fill={hudConfig.textColor} fontSize={16} />
          <Text text="00:00:45" x={contentStartX + contentWidth - 100} y={contentStartY + 50} fill={hudConfig.textColor} fontSize={16} />
          
          {/* 方向指示器 */}
          <Text text="N" x={hudConfig.centerX} y={contentStartY + 20} fill={hudConfig.textColor} fontSize={16} align="center" />
          <Text text="E" x={contentStartX + contentWidth - 20} y={hudConfig.centerY} fill={hudConfig.textColor} fontSize={16} />
          <Text text="S" x={hudConfig.centerX} y={contentStartY + contentHeight - 20} fill={hudConfig.textColor} fontSize={16} align="center" />
          <Text text="W" x={contentStartX + 20} y={hudConfig.centerY} fill={hudConfig.textColor} fontSize={16} />
          
          {/* 刻度标记 - 更均匀分布 */}
          <Text text="33" x={hudConfig.centerX} y={contentStartY + 60} fill={hudConfig.textColor} fontSize={16} align="center" />
          <Text text="3" x={contentStartX + contentWidth - 60} y={contentStartY + 60} fill={hudConfig.textColor} fontSize={16} />
          <Text text="6" x={contentStartX + contentWidth - 60} y={hudConfig.centerY - 60} fill={hudConfig.textColor} fontSize={16} />
          <Text text="12" x={contentStartX + contentWidth - 60} y={contentStartY + contentHeight - 100} fill={hudConfig.textColor} fontSize={16} />
          <Text text="15" x={hudConfig.centerX + 60} y={contentStartY + contentHeight - 60} fill={hudConfig.textColor} fontSize={16} />
          <Text text="21" x={contentStartX + 60} y={contentStartY + contentHeight - 100} fill={hudConfig.textColor} fontSize={16} />
          <Text text="24" x={contentStartX + 60} y={hudConfig.centerY - 60} fill={hudConfig.textColor} fontSize={16} />
          <Text text="30" x={contentStartX + 60} y={contentStartY + 60} fill={hudConfig.textColor} fontSize={16} />
          
          {/* 右侧高度指示器 */}
          <Group x={contentStartX + contentWidth + 10} y={hudConfig.centerY - 100}>
            <Text text="A" x={0} y={0} fill={hudConfig.textColor} fontSize={16} />
            <Text text="L" x={0} y={20} fill={hudConfig.textColor} fontSize={16} />
            <Text text="T" x={0} y={40} fill={hudConfig.textColor} fontSize={16} />
            
            <Line
              points={[0, 60, 0, 200]}
              stroke={hudConfig.lineColor}
              strokeWidth={2}
            />
            
            <Circle
              x={0}
              y={80}
              radius={5}
              stroke={hudConfig.lineColor}
              strokeWidth={1}
            />
            
            <Text text="0" x={10} y={80} fill={hudConfig.textColor} fontSize={16} />
          </Group>
          
          {/* 右侧速度指示器 */}
          <Group x={contentStartX + contentWidth + 10} y={hudConfig.centerY + 120}>
            <Text text="V" x={0} y={0} fill={hudConfig.textColor} fontSize={16} />
            <Text text="E" x={0} y={20} fill={hudConfig.textColor} fontSize={16} />
            <Text text="L" x={0} y={40} fill={hudConfig.textColor} fontSize={16} />
            
            <Line
              points={[0, -80, 0, 60]}
              stroke={hudConfig.lineColor}
              strokeWidth={2}
            />
            
            <Circle
              x={0}
              y={0}
              radius={5}
              stroke={hudConfig.lineColor}
              strokeWidth={1}
            />
            
            <Text text="S" x={0} y={80} fill={hudConfig.textColor} fontSize={16} />
            <Text text="C" x={0} y={100} fill={hudConfig.textColor} fontSize={16} />
            <Text text="A" x={0} y={120} fill={hudConfig.textColor} fontSize={16} />
            <Text text="L" x={0} y={140} fill={hudConfig.textColor} fontSize={16} />
            <Text text="E" x={0} y={160} fill={hudConfig.textColor} fontSize={16} />
          </Group>
          
          {/* 中心十字准线 */}
          <Group x={hudConfig.centerX} y={hudConfig.centerY}>
            <Line
              points={[-15, 0, 15, 0]}
              stroke={hudConfig.lineColor}
              strokeWidth={1}
            />
            <Line
              points={[0, -15, 0, 15]}
              stroke={hudConfig.lineColor}
              strokeWidth={1}
            />
          </Group>
          
          {/* 中心圆形标记 */}
          <Circle
            x={hudConfig.centerX}
            y={hudConfig.centerY - 50}
            radius={15}
            stroke={hudConfig.lineColor}
            strokeWidth={1}
          />
          
          {/* 三角形飞机标记 */}
          <Group x={hudConfig.centerX} y={hudConfig.centerY - 150}>
            <Line
              points={[0, -15, 15, 15, -15, 15, 0, -15]}
              stroke={hudConfig.lineColor}
              strokeWidth={1}
              closed={true}
              fill="#000000"
            />
            <Line
              points={[0, 15, 0, 30]}
              stroke="#ff0000"
              strokeWidth={1}
            />
          </Group>
          
          {/* 目标标记 */}
          <Group x={hudConfig.centerX} y={hudConfig.centerY + 80}>
            <Circle
              radius={20}
              stroke={hudConfig.lineColor}
              strokeWidth={1}
            />
            <Text text="029" x={-15} y={-8} fill={hudConfig.textColor} fontSize={14} />
            <Line
              points={[25, 0, 40, 0]}
              stroke={hudConfig.lineColor}
              strokeWidth={1}
            />
            <Text text="19" x={45} y={-8} fill={hudConfig.textColor} fontSize={14} />
          </Group>
          
          {/* 底部状态栏 */}
          <Group x={contentStartX + 20} y={contentStartY + contentHeight - 100}>
            <Text text="C: 60" x={0} y={0} fill={hudConfig.textColor} fontSize={14} />
            <Text text="F: 30" x={0} y={20} fill={hudConfig.textColor} fontSize={14} />
            <Rect x={60} y={0} width={60} height={15} fill={hudConfig.textColor} />
            <Rect x={60} y={20} width={30} height={15} fill={hudConfig.textColor} />
          </Group>
          
          <Group x={contentStartX + 20} y={contentStartY + contentHeight - 60}>
            <Text text="Q1: 01" x={0} y={0} fill={hudConfig.textColor} fontSize={14} />
            <Text text="Q2: 01" x={0} y={20} fill={hudConfig.textColor} fontSize={14} />
            <Rect x={60} y={0} width={15} height={15} fill={hudConfig.textColor} />
            <Rect x={60} y={20} width={15} height={15} fill={hudConfig.textColor} />
          </Group>
          
          {/* 底部菜单 */}
          <Text text="EXP" x={contentStartX + 30} y={contentStartY + contentHeight - 20} fill={hudConfig.textColor} fontSize={16} />
          <Text text="STEP" x={contentStartX + contentWidth/5} y={contentStartY + contentHeight - 20} fill={hudConfig.textColor} fontSize={16} />
          <Text text="4405" x={contentStartX + (contentWidth*2)/5} y={contentStartY + contentHeight - 20} fill={hudConfig.textColor} fontSize={16} />
          <Text text="TXDSG" x={contentStartX + (contentWidth*3)/5} y={contentStartY + contentHeight - 20} fill={hudConfig.textColor} fontSize={16} />
          <Text text="AUTO" x={contentStartX + (contentWidth*4)/5} y={contentStartY + contentHeight - 20} fill={hudConfig.textColor} fontSize={16} />
          
          {/* 右下角信息 */}
          <Text text="F15" x={contentStartX + contentWidth - 100} y={contentStartY + contentHeight - 80} fill={hudConfig.textColor} fontSize={14} />
          <Text text="ED11 / 13.4" x={contentStartX + contentWidth - 100} y={contentStartY + contentHeight - 60} fill={hudConfig.textColor} fontSize={14} />
          <Text text="BRA 153/6" x={contentStartX + contentWidth - 100} y={contentStartY + contentHeight - 40} fill={hudConfig.textColor} fontSize={14} />
        </Layer>
      </Stage>
    </div>
  );
};

export default NavigationHUD; 