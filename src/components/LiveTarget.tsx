import React from 'react';
import { Group, Line, Text } from 'react-konva';
import { RadarTarget } from '../hooks/useRadarData';

// 创建一个新的类型来代表传递给LiveTarget的 "扁平化" 后的对象
// 它继承了RadarTarget的所有属性，但保证x, y, quality, threat_level, relative_heading是存在的
interface LiveTargetObject extends RadarTarget {
  x: number;
  y: number;
  quality: number;
  threat_level: number;
  relative_heading: number;
}

interface LiveTargetProps {
  target: LiveTargetObject;
  radarConfig: any;
  scanAngle?: number;
}

const LiveTarget: React.FC<LiveTargetProps> = ({ target, radarConfig, scanAngle = 60 }) => {
  // 根据威胁等级选择不同颜色
  const getThreatColor = (level: number) => {
    switch (level) {
      case 3: return '#ff0000'; // 高威胁 - 红色
      case 2: return '#ff9900'; // 中等威胁 - 橙色
      case 1: return '#ffff00'; // 低威胁 - 黄色
      default: return '#ffffff'; // 未知威胁 - 白色
    }
  };

  // 根据scanAngle计算缩放比例
  const getScale = () => {
    switch (scanAngle) {
      case 15: return 1.2;
      case 30: return 1.0;
      case 60: return 0.8;
      default: return 1.0;
    }
  };
  const scale = getScale();

  // 根据目标质量计算透明度
  // 由于LiveTargetObject中quality是必须的，所以无需担心undefined
  const alpha = 0.5 + target.quality * 0.5;
  const color = getThreatColor(target.threat_level);

  // 将后端的笛卡尔坐标系角度 (direction) 转换为屏幕坐标系下的旋转角度（单位：度）
  // 我们的基础图标(>)的朝向是左边, 所以需要增加180度来对齐0度朝右的标准。
  const rotationDegrees = -target.direction * 180 / Math.PI + 180;

  // 新增：计算相对航向指示器的旋转角度
  // relative_heading 是后端算好的，直接使用即可。0度代表同向。
  const relativeRotationDegrees = target.relative_heading;

  return (
    <Group 
      x={target.x} 
      y={target.y} 
      rotation={rotationDegrees}
      opacity={alpha}
      scaleX={scale}
      scaleY={scale}
    >
      {/* 速度矢量线 / 拖尾 - 从顶点向后延伸 */}
      <Line
        points={[-15, 0, -15 - target.speed * 2, 0]} // 长度与速度相关
        stroke={color}
        strokeWidth={1.5}
      />
      
      {/* 目标三角形 - 底边朝前 */}
      <Line
        points={[
           0, 7,   // 底边上端点
           0, -7,  // 底边下端点
           -15, 0  // 顶点
        ]}
        closed={true}
        fill={color}
        stroke={color}
        strokeWidth={1}
      />

      {/* 新增：相对航向指示器 */}
      {/* 这个Group是相对于父Group旋转的，所以它的旋转是基于目标的朝向的 */}
      <Group rotation={relativeRotationDegrees}>
         {/* 在目标三角形前方绘制一条短线作为指示器 */}
         <Line
            points={[5, 0, 15, 0]} // 从目标前方延伸出一条线
            stroke="#00ff00" // 使用亮绿色以示区别
            strokeWidth={2}
         />
      </Group>

    </Group>
  );
};

export default LiveTarget; 