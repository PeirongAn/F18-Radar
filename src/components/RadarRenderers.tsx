import { Line, Text, Group, Circle } from 'react-konva';
import TDC from './TDC';
import VerticalText from './VerticalText';
import AntennaElevationMarker from './AntennaElevationMarker';
import VelocityVector from './VelocityVector';
import HorizonHUD from './HorizonHUD';
import BScan from './BScan';
import EnemyTarget from './EnemyTarget';

interface RenderProps {
  width: number;
  height: number;
  radarConfig: any;
  framePositions: {
    startX: number;
    startY: number;
    endX: number;
    endY: number;
  };
  tdcPosition?: { x: number; y: number };
}
  // 抽取刻度线相关的常量
const scaleLineLength = 20;  // 刻度线长度
const topScaleOffset = 30;   // 顶部水平分割线的Y偏移
export const renderMainFrame = ({ 
  radarConfig, 
  framePositions,
  tdcPosition 
}: RenderProps) => {
  const { startX, startY, endX, endY } = framePositions;

  // 计算俯仰角标记的可移动范围
  const minY = startY + (radarConfig.mainBoxHeight / 4);     // 第一个刻度位置
  const maxY = startY + (radarConfig.mainBoxHeight / 4) * 3; // 第三个刻度位置

  // 计算B扫描线的位置
  const bScanX = endX - (radarConfig.mainBoxWidth / 18) * 3;

  return (
    <>
      {/* 主框架 */}
      <Line
        points={[startX, startY, endX, startY, endX, endY, startX, endY, startX, startY]}
        stroke={radarConfig.gridColor}
        strokeWidth={1}
        closed={true}
      />

      {/* B型扫描线 */}
      <BScan
        x={bScanX}
        startY={startY}
        endY={endY}
        color={radarConfig.gridColor}
      />
   
      {/* 水平分割线 */}
      <Line
        points={[startX, startY + topScaleOffset, endX, startY + topScaleOffset]}
        stroke={radarConfig.gridColor}
        strokeWidth={1}
      />

      {/* 顶部刻度线 */}
      {[1, 5, 9, 13, 17].map((i) => (
        <Line
          key={`top-${i}`}
          points={[
            startX + (radarConfig.mainBoxWidth / 18) * i,
            startY + topScaleOffset,
            startX + (radarConfig.mainBoxWidth / 18) * i,
            startY + topScaleOffset + scaleLineLength
          ]}
          stroke={radarConfig.gridColor}
          strokeWidth={1}
        />
      ))}

      {/* 底部刻度线 */}
      {[1, 5, 9, 13, 17].map((i) => (
        <Line
          key={`bottom-${i}`}
          points={[
            startX + (radarConfig.mainBoxWidth / 18) * i,
            endY,
            startX + (radarConfig.mainBoxWidth / 18) * i,
            endY - scaleLineLength,
          ]}
          stroke={radarConfig.gridColor}
          strokeWidth={1}
        />
      ))}

      {/* 右侧刻度线 */}
      {[1, 2, 3].map((i) => (
        <Line
          key={`right-${i}`}
          points={[
            endX - scaleLineLength,
            startY + (radarConfig.mainBoxHeight / 4) * i,
            endX,
            startY + (radarConfig.mainBoxHeight / 4) * i
          ]}
          stroke={radarConfig.gridColor}
          strokeWidth={1}
        />
      ))}

      {/* 左侧刻度线 */}
      {[1, 2, 3].map((i) => (
        <Line
          key={`left-${i}`}
          points={[
            startX,
            startY + (radarConfig.mainBoxHeight / 4) * i,
            startX + scaleLineLength,
            startY + (radarConfig.mainBoxHeight / 4) * i
          ]}
          stroke={radarConfig.gridColor}
          strokeWidth={1}
        />
      ))}

      {/* 天线俯仰角刻度标记 */}
      <AntennaElevationMarker
        x={startX + 20}  // 向左偏移，使其位于左侧刻度线外
        y={minY + (maxY - minY) / 2} // 初始位置在中间
        color={radarConfig.gridColor}
        minY={minY}
        maxY={maxY}
      />

      {/* 目标符号 */}
      <Group
        x={startX + radarConfig.mainBoxWidth * 0.7}
        y={startY + radarConfig.mainBoxHeight * 0.6}
      >
        <Line
          points={[-5, -5, 5, 5]}
          stroke={radarConfig.gridColor}
          strokeWidth={1}
        />
        <Line
          points={[-5, 5, 5, -5]}
          stroke={radarConfig.gridColor}
          strokeWidth={1}
        />
      </Group>

      {/* TDC载获游标 */}
      {tdcPosition && (
        <TDC
          x={tdcPosition.x}
          y={tdcPosition.y}
          color={radarConfig.gridColor}
          upperValue="23"
          lowerValue="16"
        />
      )}

      {/* 右上角菱形标记 */}
      <Group x={endX + 20} y={startY - 20}>
        {/* 菱形轮廓 */}
        <Line
          points={[0, -8, 8, 0, 0, 8, -8, 0]}
          stroke={radarConfig.gridColor}
          strokeWidth={1}
          closed={true}
        />
        {/* 中心圆点 */}
        <Circle
          x={0}
          y={0}
          radius={1}
          fill={radarConfig.gridColor}
        />
      </Group>

      {/* 右侧向上箭头 - 第一个刻度线附近 */}
      <Group x={endX + 40} y={startY + 40}>
        <Line
          points={[
            0, 10,     // 箭头底部中心点（增加拖尾长度）
            0, -10,    // 箭头竖线
            -5, -5,    // 左斜线
            0, -10,    // 回到顶点
            5, -5,     // 右斜线
            0, -10,    // 回到顶点
            0, 10      // 延长拖尾
          ]}
          stroke={radarConfig.gridColor}
          strokeWidth={1}
        />
      </Group>

      {/* 右侧向下箭头 - 第二个刻度线附近 */}
      <Group x={endX + 40} y={startY + (radarConfig.mainBoxHeight / 4) + 20}>
        <Line
          points={[
            0, -10,    // 箭头顶部中心点（增加拖尾长度）
            0, 10,     // 箭头竖线
            -5, 5,     // 左斜线
            0, 10,     // 回到底点
            5, 5,      // 右斜线
            0, 10,     // 回到底点
            0, -10     // 延长拖尾
          ]}
          stroke={radarConfig.gridColor}
          strokeWidth={1}
        />
      </Group>

      {/* 右上角数字40 */}
      <Text 
        text="40" 
        x={endX + 10} 
        y={startY - 5} 
        fill={radarConfig.textColor} 
        fontSize={16}
      />

      {/* 右下角数字0 */}
      <Text 
        text="0" 
        x={endX + 10} 
        y={endY - 5} 
        fill={radarConfig.textColor} 
        fontSize={16}
      />
      <VelocityVector
        x={startX + radarConfig.mainBoxWidth * 0.3}
        y={startY + radarConfig.mainBoxHeight * 0.4}
        color={radarConfig.gridColor}
      />
      <HorizonHUD
        x={startX + radarConfig.mainBoxWidth * 0.3}
        y={startY + radarConfig.mainBoxHeight * 0.4}
        color={radarConfig.gridColor}
      />
      <EnemyTarget
        x={startX + radarConfig.mainBoxWidth * 0.5}
        y={startY + radarConfig.mainBoxHeight * 0.3}
        color={radarConfig.gridColor}
        size={8}
      />
    </>
  );
};

export const renderText = ({ 
  width, 
  height, 
  radarConfig, 
  framePositions 
}: RenderProps) => {
  const { startX, startY, endX, endY } = framePositions;

  return (
    <>
      {/* 顶部文本 - OPR和C11 */}
      <Text 
        text="OPR" 
        x={startX - 25} 
        y={startY - 30} 
        fill={radarConfig.textColor} 
        fontSize={16}
        align="right"
      />
      <Text 
        text="C11" 
        x={startX - 25} 
        y={startY - 15} 
        fill={radarConfig.textColor} 
        fontSize={16}
        align="right"
      />

      {/* 其他顶部文本 */}
      <Text text="4B 1" x={startX + (radarConfig.mainBoxWidth / 18)}  y={startY - 45}  fill={radarConfig.textColor} fontSize={16} />
      <Text text="SIL" x={startX + (radarConfig.mainBoxWidth / 18) * 5} y={startY - 45} fill={radarConfig.textColor} fontSize={16} />
      <Text 
        text="ERASE" 
        x={startX + radarConfig.mainBoxWidth/2 - 20} 
        y={startY - 45}
        fill={radarConfig.textColor}
        fontSize={16} />
      {/* A/A 航路点到 TDC航向和距离 */}
      <Text 
        text="345°/25.0" 
        x={startX + (radarConfig.mainBoxWidth / 18)} 
        y={startY - 15} 
        fill={radarConfig.textColor} 
        fontSize={16}
        align="center"
      />
      <Text 
        text="057°" 
        x={startX + radarConfig.mainBoxWidth/2 - 10} 
        y={startY - 15} 
        fill={radarConfig.textColor} 
        fontSize={16}
        align="center"
      />

      <Text 
        text="7M 0" 
        x={endY - 40} 
        y={startY - 15} 
        fill={radarConfig.textColor} 
        fontSize={16}
        align="center"
      />

      {/* 左侧文本 */}
      <Text text="RWS" x={5} y={startY + topScaleOffset + 10 } fill={radarConfig.textColor} fontSize={16} />

      {/* SURF竖直排列 */}
      <VerticalText
        text="SURF"
        x={5}
        y={startY + radarConfig.mainBoxHeight/2 - 20}
        fontSize={16}
        color={radarConfig.textColor}
      />

      {/* PRI竖直排列 */}
      <VerticalText
        text="PRI"
        x={startX - 15}
        y={startY + (radarConfig.mainBoxHeight / 4) * 3 - 40}
        fontSize={16}
        color={radarConfig.textColor}
      />

      {/* RDR竖直排列 */}
      <VerticalText
        text="RDR"
        x={startX - 35}
        y={startY + (radarConfig.mainBoxHeight / 4) * 3 - 40}
        fontSize={16}
        color={radarConfig.textColor}
      />

      {/* MED和INTL文本 - 放在左侧最后一个刻度线附近 */}
      <Text 
        text="MED" 
        x={startX - 45} 
        y={startY + (radarConfig.mainBoxHeight / 8) * 7} 
        fill={radarConfig.textColor} 
        fontSize={16}
      />
      <Text 
        text="INTL" 
        x={startX - 45} 
        y={startY + (radarConfig.mainBoxHeight / 8) * 7 + 15} 
        fill={radarConfig.textColor} 
        fontSize={16}
      />

      {/* 右侧文本 */}
      <VerticalText
        text="SET"
        x={endX + 35}
        y={startY + (radarConfig.mainBoxHeight / 4) * 2 - 20}
        fontSize={16}
        color={radarConfig.textColor}
      />

      {/* RSET文本 */}
      <VerticalText
        text="RSET"
        x={endX + 35}
        y={startY + (radarConfig.mainBoxHeight / 4) * 3 - 40}
        fontSize={16}
        color={radarConfig.textColor}
      />
      
      {/* NCTR文本和外框 */}
      <Group x={endX + 35} y={startY + radarConfig.mainBoxHeight - 80}>
        {/* 外框 */}
        <Line
          points={[
            -2, -2,  // 左上
            22, -2,  // 右上
            22, 62,  // 右下
            -2, 62,  // 左下
            -2, -2   // 回到左上，闭合
          ]}
          stroke={radarConfig.gridColor}
          strokeWidth={1}
          closed={true}
        />
        {/* NCTR文本 */}
        <VerticalText
          text="NCTR"
          x={0}
          y={0}
          fontSize={16}
          color={radarConfig.textColor}
        />
      </Group>

      {/* 底部文本 */}
      <Text 
        text="451" 
        x={startX + 5} 
        y={endY} 
        fill={radarConfig.textColor} 
        fontSize={16}
      />
      <Text 
        text="0.78" 
        x={startX + 5} 
        y={endY + 10} 
        fill={radarConfig.textColor} 
        fontSize={16}
      />
      <Text 
        text="MODE" 
        x={startX} 
        y={endY + 30} 
        fill={radarConfig.textColor} 
        fontSize={16}
      />
      <Text text="BRA" x={startX + (radarConfig.mainBoxWidth / 18) - 5} y={endY - 35} fill={radarConfig.textColor} fontSize={16} />
      <Text text="322°/36.6" x={startX + (radarConfig.mainBoxWidth / 18) * 5 - 45} y={endY - 35} fill={radarConfig.textColor} fontSize={16} />
      
      <Text 
        text="140°" 
        x={startX + (radarConfig.mainBoxWidth / 18) * 5 -15} 
        y={endY + 30} 
        fill={radarConfig.textColor} 
        fontSize={16}
      />

      <Text 
        text="2805" 
        x={startX + (radarConfig.mainBoxWidth / 18) * 9 -15} 
        y={endY + 25} 
        fill={radarConfig.textColor} 
        fontSize={16}
      />
      {/* A/A 航路点到本机的方位和距离 */}
      <Text 
        text="200°/18.6" 
        x={startX + (radarConfig.mainBoxWidth / 18) * 9 -30} 
        y={endY + 5} 
        fill={radarConfig.textColor} 
        fontSize={16}
      />

      <Text 
        text="CHAN" 
        x={startX + (radarConfig.mainBoxWidth / 18) * 13 -20} 
        y={endY + 30} 
        fill={radarConfig.textColor} 
        fontSize={16}
      />
       <Text 
        text="DATA" 
        x={startX + (radarConfig.mainBoxWidth / 18) * 17  -20} 
        y={endY + 30} 
        fill={radarConfig.textColor} 
        fontSize={16}
      />

      <Text 
        text="7870" 
        x={startX + (radarConfig.mainBoxWidth / 18) * 17  -20} 
        y={endY + 5} 
        fill={radarConfig.textColor} 
        fontSize={16}
      />


    
      
    </>
  );
}; 