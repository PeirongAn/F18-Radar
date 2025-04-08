import React, { useState } from 'react';
import { Stage, Layer, Circle, Line, Group, Text, Rect } from 'react-konva';

interface SAPageProps {
  width?: number;
  height?: number;
}

// 添加威胁数据接口
interface ThreatData {
  id: string;
  type: string;
  source: string;
  distance: number;
  heading: number;
  priority: 'high' | 'medium' | 'low';
}

// 按钮组件 - 使用普通DOM元素而非Konva
interface ButtonProps {
  label: string;
  onClick?: () => void;
}

const Button: React.FC<ButtonProps> = ({ label, onClick }) => {
  return (
    <button
      className="w-12 h-10 bg-gray-900 text-green-400 border-2 border-white rounded font-mono hover:bg-gray-800 focus:outline-none"
      onClick={onClick}
    >
    
    </button>
  );
};

const SAPage: React.FC<SAPageProps> = ({ width = 900, height = 900}) => {
  // 模拟威胁数据
  const [threats] = useState<ThreatData[]>([
    {
      id: 'threat-1',
      type: 'xxx',
      source: 'MiG-29',
      distance: 28.5,
      heading: 315,
      priority: 'high'
    },
    {
      id: 'threat-2',
      type: 'xxx',
      source: 'SA-10',
      distance: 42.3,
      heading: 45,
      priority: 'medium'
    },
    {
      id: 'threat-3',
      type: 'xxx',
      source: 'Su-27',
      distance: 15.7,
      heading: 270,
      priority: 'low'
    }
  ]);

  // 获取优先级对应的颜色
  const getPriorityColor = (priority: string): string => {
    switch (priority) {
      case 'high': return '#ff0000';
      case 'medium': return '#ffff00';
      case 'low': return '#00ffff';
      default: return '#ffffff';
    }
  };

  // 配置
  const config = {
    backgroundColor: '#000000',
    lineColor: '#00ff00',    // 绿色线条
    accentColor: '#ff0000',  // 红色强调线
    textColor: '#00ff00',    // 绿色文本
    centerX: width / 2,
    // 将圆心向下移动，将原来的centerY从height/2移动到更低的位置
    centerY: height * 0.6,   // 向下移动圆心位置到60%的高度位置
  };

  // 圆的半径 - 增大所有圆的半径
  const radius1 = 100; // 原来是70，增大到100
  // 计算第二个圆的半径，使其与底部白线相切
  // 底部线的位置约在stageHeight减去一定边距，这里设置为高度的90%
  const bottomLineY = height * 0.9;
  const radius2 = bottomLineY - config.centerY + 50; // 使第二个圆与底部线相切
  const radius3 = radius2 * 1.6; // 第三个圆的半径，原来是1.5倍，现在增大到1.6倍
  
  // 计算弧线角度
  const arcStartAngle = 210; // 开始角度 (210度)
  const arcEndAngle = 330;   // 结束角度 (330度)
  
  // 转换为弧度
  const startRad = (arcStartAngle * Math.PI) / 180;
  const endRad = (arcEndAngle * Math.PI) / 180;
  
  // 计算弧线端点
  const arcStartX = config.centerX + radius3 * Math.cos(startRad);
  const arcStartY = config.centerY + radius3 * Math.sin(startRad);
  const arcEndX = config.centerX + radius3 * Math.cos(endRad);
  const arcEndY = config.centerY + radius3 * Math.sin(endRad);

  // 计算主显示区域的边界位置
  const framePositions = {
    startX: config.centerX - radius3,
    startY: config.centerY - radius3,
    endX: config.centerX + radius3,
    endY: config.centerY + radius3
  };

  // 方向标记位置
  const directions = [
    { label: 'N', angle: 270 },
    { label: 'E', angle: 0 },
    { label: 'S', angle: 90 },
    { label: 'W', angle: 180 }
  ];

  // 第一个圆上的方向标记
  const circleMarkers = [
    { label: 'W', angle: 30 },
    { label: 'N', angle: 120 },
    { label: 'E', angle: 210 },
    { label: 'S', angle: 320 }
  ];

  // 计算第一个圆上标记的位置和短线
  const circleMarkerLines = circleMarkers.map(({ label, angle }) => {
    const rad = (angle * Math.PI) / 180;
    const centerX = config.centerX;
    const centerY = config.centerY - 50; // 第一个圆的Y坐标
    
    // 短线的内外端点
    const innerX = centerX + (radius1 - 10) * Math.cos(rad);
    const innerY = centerY + (radius1 - 10) * Math.sin(rad);
    const outerX = centerX + (radius1 + 10) * Math.cos(rad);
    const outerY = centerY + (radius1 + 10) * Math.sin(rad);
    
    // 文本位置 - 在短线外侧
    const textX = centerX + (radius1 + 20) * Math.cos(rad);
    const textY = centerY + (radius1 + 20) * Math.sin(rad);
    
    return {
      label,
      line: [innerX, innerY, outerX, outerY],
      textX,
      textY
    };
  });

  // 第三段圆弧刻度线 - 11等分
  const arcScaleLines = [];
  // 弧线总角度
  const totalArcAngle = 100; // 修改为100度，与Arc组件的angle值保持一致
  // 计算每一等分的角度
  const divisionAngle = totalArcAngle / 11; // 10个间隔产生11个刻度点
  
  // 弧线起始角度 (根据rotation值计算)
  const arcBaseAngle = -140; // 与Arc组件的rotation值相同
  
  // 生成11个刻度点
  for (let i = 0; i <= 10; i++) {
    const angle = arcBaseAngle + i * divisionAngle;
    const rad = (angle * Math.PI) / 180;
    
    arcScaleLines.push({
      innerX: config.centerX + (radius3 + 10) * Math.cos(rad), // 向内延伸
      innerY: config.centerY + (radius3 + 10) * Math.sin(rad),
      outerX: config.centerX + radius3 * Math.cos(rad),
      outerY: config.centerY + radius3 * Math.sin(rad)
    });
  }

  // 刻度线位置计算（第二个圆和第三个圆之间的刻度线）
  const scaleLines = [];
  for (let angle = 0; angle < 360; angle += 30) {
    // 只绘制在弧线范围内的刻度线 (210-330度)
    if (angle >= arcStartAngle - 360 && angle <= arcEndAngle - 360) {
      const rad = (angle * Math.PI) / 180;
      scaleLines.push({
        angle,
        innerX: config.centerX + radius2 * Math.cos(rad),
        innerY: config.centerY + radius2 * Math.sin(rad),
        outerX: config.centerX + (radius3 - 10) * Math.cos(rad),
        outerY: config.centerY + (radius3 - 10) * Math.sin(rad)
      });
    }
  }

  // 方向标记渲染函数
  const renderDirectionMarkers = () => {
    return directions.map(({ label, angle }) => {
      // 只渲染在弧线范围内的方向标记
      if (angle >= arcStartAngle - 360 && angle <= arcEndAngle - 360) {
        const rad = (angle * Math.PI) / 180;
        const x = config.centerX + (radius2 - 25) * Math.cos(rad);
        const y = config.centerY + (radius2 - 25) * Math.sin(rad);
        return (
          <Text
            key={label}
            x={x}
            y={y}
            text={label}
            fill={config.lineColor}
            fontSize={16}
            align="center"
            verticalAlign="middle"
            offsetX={8}
            offsetY={8}
          />
        );
      }
      return null;
    });
  };

  // 创建按钮标签
  const topButtons = Array(5).fill(0).map((_, i) => `T${i + 1}`);
  const leftButtons = Array(5).fill(0).map((_, i) => `L${i + 1}`);
  const rightButtons = Array(5).fill(0).map((_, i) => `R${i + 1}`);
  
  // 按钮点击处理函数
  const handleButtonClick = (label: string) => {
    console.log(`按钮 ${label} 被点击`);
  };

  // 计算按钮容器尺寸
  const topContainerWidth = width; // 使顶部容器宽度与雷达宽度相同
  const sideContainerHeight = height * 0.8; // 侧边容器高度与雷达高度的80%相同

  return (
    <div className="flex flex-col items-center justify-center">
      <div className="flex flex-col items-center">
        {/* 顶部按钮 - 使用justify-between均匀分布 */}
        <div 
          className="flex justify-between mb-4" 
          style={{ width: topContainerWidth, padding: '0 20px' }}
        >
          {topButtons.map(label => (
            <Button key={label} label={label} onClick={() => handleButtonClick(label)} />
          ))}
        </div>
        
        <div className="flex">
          {/* 左侧按钮 - 使用flex-col和justify-between均匀分布 */}
          <div 
            className="flex flex-col justify-between mr-4 mt-12" 
            style={{ height: sideContainerHeight }}
          >
            {leftButtons.map(label => (
              <Button key={label} label={label} onClick={() => handleButtonClick(label)} />
            ))}
          </div>
          
          {/* 雷达显示 - 仅包含雷达相关元素 */}
          <div className="sa-page bg-black" style={{ width, height }}>
            <Stage width={width} height={height}>
              <Layer>
                {/* 第一个圆（中心圆） */}
                <Circle
                  x={config.centerX}
                  y={config.centerY - 50}
                  radius={radius1}
                  stroke={config.lineColor}
                  strokeWidth={1}
                />
                
                {/* 第一个圆上的标记 */}
                {circleMarkerLines && circleMarkerLines.map((marker, i) => (
                  <React.Fragment key={`circle-marker-${i}`}>
                    <Line
                      points={marker.line}
                      stroke={config.lineColor}
                      strokeWidth={1}
                    />
                    <Text
                      text={marker.label}
                      x={marker.textX}
                      y={marker.textY}
                      fill={config.lineColor}
                      fontSize={14}
                      align="center"
                      verticalAlign="middle"
                      offsetX={7}
                      offsetY={7}
                    />
                  </React.Fragment>
                ))}
                
                {/* 第二个圆 */}
                <Circle
                  x={config.centerX}
                  y={config.centerY - 50}
                  radius={radius2}
                  stroke={config.lineColor}
                  strokeWidth={1}
                />
                
                {/* 第三个圆（只显示120度弧线，去掉中心线） */}
                <Group>
                  <Arc
                    x={config.centerX}
                    y={config.centerY}
                    radius={radius3}
                    angle={100}
                    rotation={-140} // 弧线居中于顶部，-150度使120度的弧线位于顶部
                    stroke={config.lineColor}
                    strokeWidth={1}
                  />
                </Group>
                
                {/* 方向和刻度线 */}
                {renderDirectionMarkers && renderDirectionMarkers()}
                
                {/* 第二个和第三个圆之间的刻度线 */}
                {scaleLines && scaleLines.map((line, i) => (
                  <Line
                    key={`scale-${i}`}
                    points={[line.innerX, line.innerY, line.outerX, line.outerY]}
                    stroke={config.lineColor}
                    strokeWidth={1}
                  />
                ))}
                
                {/* 第三个圆上的11等分刻度线 */}
                {arcScaleLines && arcScaleLines.map((line, i) => (
                  <Line
                    key={`arc-scale-${i}`}
                    points={[line.innerX, line.innerY, line.outerX, line.outerY]}
                    stroke={config.lineColor}
                    strokeWidth={1}
                  />
                ))}
                
                {/* 底部横线 */}
                <Line
                  points={[0, bottomLineY, width, bottomLineY]}
                  stroke="#ffffff"
                  strokeWidth={2}
                />
                
                {/* 添加边框线，使边界可见 */}
                {/* <Rect
                  x={framePositions.startX}
                  y={framePositions.startY}
                  width={framePositions.endX - framePositions.startX}
                  height={framePositions.endY - framePositions.startY}
                  stroke={config.accentColor}
                  strokeWidth={2}
                  dash={[5, 5]}
                /> */}
              </Layer>
            </Stage>
          </div>
          
          {/* 右侧按钮 - 使用flex-col和justify-between均匀分布 */}
          <div 
            className="flex flex-col justify-between ml-4 mt-12" 
            style={{ height: sideContainerHeight }}
          >
            {rightButtons.map(label => (
              <Button key={label} label={label} onClick={() => handleButtonClick(label)} />
            ))}
          </div>
        </div>
      </div>
      
      {/* 威胁列表 */}
      <div className="w-full max-w-4xl bg-black border border-gray-700 rounded-md overflow-hidden" style={{marginTop: '-80px'}}>
        <div className="bg-gray-800 p-2 border-b border-gray-700">
          <h3 className="text-green-400 font-mono text-lg text-center">威胁列表</h3>
        </div>
        
        <div className="p-2 bg-gray-900 font-mono text-sm text-gray-300 flex border-b border-gray-800">
          <div className="w-8 text-center">#</div>
          <div className="w-32">类型</div>
          <div className="w-32">来源</div>
          <div className="w-48">距离/方位</div>
          <div className="w-24">优先级</div>
        </div>
        
        {threats.map((threat, index) => (
          <div 
            key={threat.id} 
            className={`p-2 border-b border-gray-800 font-mono text-sm flex items-center ${
              index % 2 === 0 ? 'bg-gray-900' : 'bg-gray-950'
            }`}
          >
            <div className="w-8 text-center text-gray-400">{index + 1}</div>
            <div className="w-32 text-green-400">{threat.type}</div>
            <div className="w-32 text-yellow-400">{threat.source}</div>
            <div className="w-48 text-blue-300">{threat.distance.toFixed(1)}nm/{threat.heading}°</div>
            <div className="w-24 flex items-center">
              <span 
                className="w-3 h-3 rounded-full mr-2" 
                style={{ backgroundColor: getPriorityColor(threat.priority) }}
              ></span>
              <span className="text-white">
                {threat.priority === 'high' ? '高' : threat.priority === 'medium' ? '中' : '低'}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// 自定义弧线组件
interface ArcProps {
  x: number;
  y: number;
  radius: number;
  angle: number;
  rotation?: number;
  stroke: string;
  strokeWidth: number;
}

const Arc: React.FC<ArcProps> = ({ x, y, radius, angle, rotation = 0, stroke, strokeWidth }) => {
  // 转换角度为弧度
  const angleRad = (angle * Math.PI) / 180;
  const rotationRad = (rotation * Math.PI) / 180;
  
  // 生成弧线点
  const points = [];
  const segments = Math.max(30, Math.floor(angle)); // 分段数，越大越平滑
  
  for (let i = 0; i <= segments; i++) {
    const segmentAngle = rotationRad + (i / segments) * angleRad;
    const pointX = x + radius * Math.cos(segmentAngle);
    const pointY = y + radius * Math.sin(segmentAngle);
    points.push(pointX, pointY);
  }
  
  return (
    <Line
      points={points}
      stroke={stroke}
      strokeWidth={strokeWidth}
      lineCap="round"
    />
  );
};

export default SAPage; 