import React, { useEffect } from 'react';
import { Group, Line } from 'react-konva';
import UnknownTarget, { UnknownTargetData } from './UnknownTarget';

/**
 * UnknownTargetManager组件的属性接口
 */
interface UnknownTargetManagerProps {
  /**
   * 是否显示目标
   */
  showTargets: boolean;
  /**
   * 从服务端接收的目标数据
   */
  externalTargets?: UnknownTargetData[];
  /**
   * 目标显示颜色
   */
  color?: string;
  /**
   * 被选中的目标ID
   */
  selectedTargetId?: string;
  /**
   * 垂直线的位置（TDC的X坐标）
   */
  verticalLineX?: number;
  /**
   * 雷达显示区域的边界
   */
  framePositions?: {
    startX: number;
    startY: number;
    endX: number;
    endY: number;
  };
  /**
   * 是否启用IFF模式（敌我识别）
   */
  iffMode?: boolean;
  /**
   * 当前的雷达扫描角度
   */
  scanAngle?: number;
}

/**
 * 未知目标管理器组件
 * 根据服务端提供的目标数据渲染未知目标
 */
export const UnknownTargetManager: React.FC<UnknownTargetManagerProps> = ({
  showTargets,
  externalTargets = [],
  color = '#00FF00',
  selectedTargetId,
  verticalLineX,
  framePositions,
  iffMode = false,
  scanAngle = 60 // 默认值为60
}) => {
  // 如果不显示目标或者没有目标数据，但有垂直线需要显示
  if ((!showTargets || !externalTargets || externalTargets.length === 0) && verticalLineX === undefined) {
    return null;
  }
  
  // 确定垂直线的起点和终点
  const lineStartY = framePositions ? framePositions.startY : -1000;
  const lineEndY = framePositions ? framePositions.endY : 1000;
  
  // 记录目标数据变化
  useEffect(() => {
    if (externalTargets && externalTargets.length > 0) {
      console.log(`UnknownTargetManager: 渲染 ${externalTargets.length} 个目标`);
    } else {
      console.log('UnknownTargetManager: 清除所有目标');
    }
  }, [externalTargets]);

  // IFF模式下根据目标类型获取颜色
  const getTargetColor = (target: UnknownTargetData): string => {
    if (!iffMode) return color; // 非IFF模式使用默认颜色
    
    // IFF模式下根据目标类型返回不同颜色
    if (target.type === 'friend') {
      return '#00FF00'; // 绿色 - 友军
    } else if (target.type === 'army') {
      return '#FF0000'; // 红色 - 敌军
    }
    return color; // 默认颜色
  };
  
  return (
    <Group>
      {/* 渲染垂直锁定线 */}
      {verticalLineX !== undefined && (
        <Line
          points={[verticalLineX, lineStartY, verticalLineX, lineEndY]} // 限制在雷达显示区域内
          stroke={color}
          strokeWidth={1.5}
        />
      )}
      
      {/* 渲染目标 - 只在showTargets为true且目标数组不为空时渲染 */}
      {showTargets && externalTargets && externalTargets.length > 0 && externalTargets.map((target) => {
        // 确保目标数据有效
        if (!target || !target.id) return null;
        
        const targetColor = getTargetColor(target);
        return (
          <UnknownTarget 
            key={target.id} 
            data={{
              ...target,
              selected: target.id === selectedTargetId
            }} 
            color={targetColor} 
            framePositions={framePositions}
            scanAngle={scanAngle}
          />
        );
      })}
    </Group>
  );
}; 