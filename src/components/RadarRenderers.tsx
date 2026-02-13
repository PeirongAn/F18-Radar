import { Line, Text, Group, Circle } from 'react-konva';
import TDC from './TDC';
import VerticalText from './VerticalText';
import AntennaElevationMarker from './AntennaElevationMarker';



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
  scanAngle?: number; // 添加扫描角度参数
  centerOffset?: number; // 添加扫描中心位置的偏移量参数
  onTDCPositionSet?: (offset: number) => void; // 添加TDC位置设置回调函数
  range?: number; // 添加雷达范围值参数
  scanCount?: number; // 当前扫描计数
  maxScanCount?: number; // 最大扫描计数
  displayMode?: 'AUTO' | 'HI' | 'MED'; // 扫描模式显示
  hiMedToggle?: 'HI' | 'MED'; // HI/MED切换状态
  isSilent?: boolean; // 雷达静默模式状态
  isStarted?: boolean; // 雷达启动状态
  sendMessage: (message: any) => void; // 发送消息函数
}
  // 抽取刻度线相关的常量
const scaleLineLength = 20;  // 刻度线长度

export const renderMainFrame = ({ 
  sendMessage,
  radarConfig, 
  framePositions,
  tdcPosition,
  scanAngle = 60, // 默认扫描角度为60
  centerOffset = 0, // 默认中心偏移为0
  onTDCPositionSet, // TDC位置设置回调函数
  range = 20, // 当前雷达量程，默认20海里
  scanCount = 0, // 当前扫描计数
  maxScanCount = 4, // 最大扫描计数
  displayMode = 'AUTO', // 默认为AUTO模式
  hiMedToggle = 'HI', // 默认为HI
  isSilent = false, // 默认非静默模式
  isStarted = true // 默认启动状态
}: RenderProps) => {
  const { startX, startY, endX, endY } = framePositions;
  
  // 计算中心位置
  const centerX = startX + radarConfig.mainBoxWidth / 2;
  const centerY = startY + radarConfig.mainBoxHeight / 2;

  // 计算扫描中心位置（应用偏移量）
  const scanCenterX = centerX + centerOffset;

  // 计算俯仰角标记的可移动范围
  const minY = startY + (radarConfig.mainBoxHeight / 4);     // 第一个刻度位置
  const maxY = startY + (radarConfig.mainBoxHeight / 4) * 3; // 第三个刻度位置

  // 计算B扫描线的位置
  const bScanX = endX - (radarConfig.mainBoxWidth / 18) * 3;

  // 根据静默模式和系统启动状态调整颜色
  const mainColor = isSilent ? '#555555' : !isStarted ? '#222222' : radarConfig.gridColor;
  const textColor = isSilent ? '#555555' : !isStarted ? '#222222' : radarConfig.textColor;

  // 计算4分位位置 - 根据scanAngle动态调整
  let quarterX1, quarterX2;
  
  if (scanAngle === 60) {
    // 当扫描角度为60时，四分位线为整个雷达区域
    quarterX1 = startX;
    quarterX2 = endX;
  } else if (scanAngle === 30) {
    // 当扫描角度为30时，四分位线为中心区域的1/2
    quarterX1 = scanCenterX - radarConfig.mainBoxWidth / 4;
    quarterX2 = scanCenterX + radarConfig.mainBoxWidth / 4;
  } else {
    // 当扫描角度为15时，四分位线为中心区域的1/4
    quarterX1 = scanCenterX - radarConfig.mainBoxWidth / 8;
    quarterX2 = scanCenterX + radarConfig.mainBoxWidth / 8;
  }

  // 提取当前的最大扫描计数作为 "4BR" 中的数字
  const brValue = maxScanCount;

  return (
    <>
      {/* 主框架 */}
      <Line
        points={[startX, startY, endX, startY, endX, endY, startX, endY, startX, startY]}
        stroke={mainColor}
        strokeWidth={1}
        closed={true}
      />

      {/* 添加静默模式指示 */}
      {isSilent && (
        <Text
          text="SILENT"
          x={centerX - 30}
          y={centerY - 10}
          fill="#FF0000"
          fontSize={18}
          fontStyle="bold"
        />
      )}

      {/* 添加4分位竖线 */}
      {scanAngle !== 60 && <Line
        points={[quarterX1, startY, quarterX1, endY]}
        stroke={mainColor}
        strokeWidth={1}
        dash={[5, 5]} // 使用虚线样式，类似参考图片
      />}
      
      <Line
        points={[quarterX2, startY, quarterX2, endY]}
        stroke={mainColor}
        strokeWidth={1}
        dash={[5, 5]} // 使用虚线样式，类似参考图片
      />

 

      {/* 顶部刻度线 */}
      {[3, 6, 9, 12, 15].map((i) => (
        <Line
          key={`top-${i}`}
          points={[
            startX + (radarConfig.mainBoxWidth / 18) * i,
            startY,
            startX + (radarConfig.mainBoxWidth / 18) * i,
            startY + scaleLineLength
          ]}
          stroke={mainColor}
          strokeWidth={1}
        />
      ))}

      {/* 底部刻度线 */}
      {[3, 6, 9, 12, 15].map((i) => (
        <Line
          key={`bottom-${i}`}
          points={[
            startX + (radarConfig.mainBoxWidth / 18) * i,
            endY,
            startX + (radarConfig.mainBoxWidth / 18) * i,
            endY - scaleLineLength,
          ]}
          stroke={mainColor}
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
          stroke={mainColor}
          strokeWidth={1}
        />
      ))}

      {/* 左侧刻度线及仰角数字标注：上3、中0、下-3 */}
      {[1, 2, 3].map((i) => {
        const elevationLabels: Record<number, string> = { 1: '3', 2: '0', 3: '-3' };
        const tickY = startY + (radarConfig.mainBoxHeight / 4) * i;
        return (
          <Group key={`left-${i}`}>
            <Line
              points={[
                startX,
                tickY,
                startX + scaleLineLength,
                tickY
              ]}
              stroke={mainColor}
              strokeWidth={1}
            />
            <Text
              text={elevationLabels[i]}
              x={startX + scaleLineLength + 4}
              y={tickY - 7}
              fill={mainColor}
              fontSize={13}
              fontFamily="monospace"
            />
          </Group>
        );
      })}

      {/* 天线俯仰角刻度标记 */}
      <AntennaElevationMarker
        x={startX + 20}  // 向左偏移，使其位于左侧刻度线外
        color={mainColor}
        minY={minY}
        maxY={maxY}
        sendMessage={sendMessage}
      />


      {/* TDC载获游标 */}
      {tdcPosition && (
        <TDC
          x={tdcPosition.x}
          y={tdcPosition.y}
          color={mainColor}
          upperValue="15"
          lowerValue="-3"
          centerX={centerX} // 传递中心X坐标
          onPositionSet={onTDCPositionSet} // 传递回调函数
        />
      )}



      {/* 右侧向上箭头 - 第一个刻度线附近 */}
      <Group x={endX + 80} y={startY }>
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
          stroke={textColor}
          strokeWidth={1}
        />
      </Group>

      {/* 右侧向下箭头 - 第二个刻度线附近 */}
      <Group x={endX + 80} y={startY + (radarConfig.mainBoxHeight / 4)}>
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
          stroke={textColor}
          strokeWidth={1}
        />
      </Group>


  

      {/* 注：中心位置的倒三角形标记已移至UnknownTarget组件中实现 */}

      {/* 渲染 "4BR" 文本，其中4是maxScanCount */}
      <VerticalText
        text={`${brValue}BR`}
        x={startX - 80}  // 位于左侧按钮和雷达面板之间
        y={endY - 20}   // 底部位置
        fontSize={16}
        color={textColor}
      />
      
      {/* 渲染当前扫描计数 */}
      <Text
        text={`${scanCount + 1}`}
        x={startX + 10}
        y={endY - 20}  // 底部位置
        fill={textColor}
        fontSize={16}
      />
      
      {/* 渲染HI/MED，根据显示模式决定 */}
      <Text
        text={displayMode === 'AUTO' ? hiMedToggle : displayMode}
        x={startX + 40}
        y={endY - 20}  // 底部位置
        fill={textColor}
        fontSize={16}
      />
    </>
  );
};

export const renderText = ({ 
  width, 
  height, 
  radarConfig, 
  framePositions,
  heading,  // 添加航向参数
  scanAngle = 60,  // 添加扫描角度参数，默认为60
  range = 20,  // 添加范围值参数，默认为20
  displayMode = 'AUTO', // 默认显示模式为AUTO
  isSilent = false, // 默认非静默模式
  isStarted = true // 默认启动状态
}: RenderProps & { heading?: number, scanAngle?: number, range?: number }) => {  // 扩展Props类型
  const { startX, startY, endX, endY } = framePositions;
  
  // 根据静默模式和系统启动状态调整文本颜色
  const textColor = isSilent ? '#555555' : !isStarted ? '#222222' : radarConfig.textColor;

  return (
    <>
      {/* 左侧竖排文字，自下向上排列 */}
      
      <VerticalText
        text="NOR"
        x={startX - 80}
        y={endY  - 20  - 120}  // 中间位置
        fontSize={16}
        color={textColor}
      />
      
      <Text
        text={scanAngle.toString()} // 使用传入的扫描角度值
        x={startX - 80}
        y={endY  - 20  - 220}  // 顶部位置
        fill={textColor}
        fontSize={16}
      />
      <Text
        text={displayMode} // 显示当前模式
        x={endX + 40}
        y={endY}  // 顶部位置
        fill={textColor}
        fontSize={16}
      />
      <Text
        text={range.toString()} // 使用传入的范围值
        x={endX + 70}
        y={startY + 60 }  // 顶部位置
        fill={textColor}
        fontSize={16}
      />
      <Text
        text={heading ? Math.round(heading).toString() : "278"}  // 使用实时航向
        x={startX}
        y={endY + 10 }  // 顶部位置
        fill={textColor}
        fontSize={16}
      />
     
      <Text
        text="040"
        x={startX + 230}
        y={endY + 10 }  // 顶部位置
        fill={textColor}
        fontSize={16}
      />
      <Text
        text="05980"
        x={endX - 10}
        y={endY + 10 }  // 顶部位置
        fill={textColor}
        fontSize={16}
      />
      <Text
        text="TWS"
        x={startX - 45}
        y={startY - 40 }  // 顶部位置
        fill={textColor}
        fontSize={16}
      />
      <Text
        text="CNTL"
        x={endX }
        y={startY - 40 }  // 顶部位置
        fill={textColor}
        fontSize={16}
      />

      {/* 添加静默状态文本 */}
      <Group x={startX + 180} y={startY - 40}>
        <Text 
          text="SIL" 
          fill={isSilent ? '#FF0000' : textColor} // 在静默模式下使用红色
          fontSize={16}
        />
        {/* 斜向删除线 - 只在非静默模式下显示 */}
        {!isSilent && (
          <Line
            points={[-5, -2, 25, 15]}  // 从左上到右下的斜线
            stroke={textColor}
            strokeWidth={1}
          />
        )}
      </Group>

      {/* STBY文本带删除线 */}
      <Group x={startX + 220} y={startY -40}>
        <Text 
          text="STBY" 
          fill={textColor}
          fontSize={16}
        />
        {/* 斜向删除线 */}
        <Line
          points={[-5, -2, 40, 15]}  // 从左上到右下的斜线
          stroke={textColor}
          strokeWidth={1}
        />
      </Group>
      {/* IFF文本带边框 */}
      <Group x={startX + 290} y={startY - 40}>
        {/* 文本边框 */}
        <Line
          points={[-5, -5, 30, -5, 30, 20, -5, 20, -5, -5]}  // 矩形
          stroke={textColor}
          strokeWidth={1}
          closed={true}
        />
        <Text 
          text="IFF" 
          fill={textColor}
          fontSize={16}
          x={0}
          y={0}
        />
      </Group>
   
    </>
  );
}; 