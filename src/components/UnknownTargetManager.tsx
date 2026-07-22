import React, { useEffect, useRef } from 'react';
import { Group, Line, Rect, Text } from 'react-konva';
import UnknownTarget, { UnknownTargetData } from './UnknownTarget';
import { SensorTrustDecision } from '../types/trustCalibration';

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
  /**
   * 目标点击事件回调
   */
  onTargetClick?: (target: UnknownTargetData) => void;
  /**
   * 认知负荷等级：low=详细信息, medium=概要信息, high=无额外信息
   */
  cognitiveLoad?: 'low' | 'medium' | 'high';
  /**
   * 当前雷达量程（海里），用于距离分档
   */
  range?: number;
  sensorTrustDecision?: SensorTrustDecision;
  trustAiRecommendationId?: string;
  trustGlowActive?: boolean;
  trustManualReviewActive?: boolean;
  trustDisplayNumbers?: Map<string, number>;
  trustFocusedTargetId?: string;
}

const ManualReviewPulse: React.FC<{ x: number; y: number }> = ({ x, y }) => {
  const rectRef = useRef<any>(null);

  useEffect(() => {
    let frameId = 0;
    const animate = (timestamp: number) => {
      const opacity = 0.3 + 0.65 * ((Math.sin(timestamp / 115) + 1) / 2);
      if (rectRef.current) {
        rectRef.current.opacity(opacity);
        rectRef.current.getLayer()?.batchDraw();
      }
      frameId = window.requestAnimationFrame(animate);
    };
    frameId = window.requestAnimationFrame(animate);
    return () => window.cancelAnimationFrame(frameId);
  }, []);

  return (
    <Rect
      ref={rectRef}
      x={x - 31}
      y={y - 31}
      width={62}
      height={62}
      stroke="#91e8f5"
      strokeWidth={2.5}
      cornerRadius={9}
      dash={[7, 4]}
      shadowColor="#69d8ff"
      shadowBlur={20}
      opacity={0.9}
      listening={false}
    />
  );
};

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
  scanAngle = 60, // 默认值为60
  onTargetClick,
  cognitiveLoad = 'low',
  range = 20,
  sensorTrustDecision,
  trustAiRecommendationId,
  trustGlowActive = false,
  trustManualReviewActive = false,
  trustDisplayNumbers,
  trustFocusedTargetId,
}) => {
  // 如果不显示目标或者没有目标数据，但有垂直线需要显示
  if ((!showTargets || !externalTargets || externalTargets.length === 0) && verticalLineX === undefined) {
    return null;
  }
  
  // 确定垂直线的起点和终点
  const lineStartY = framePositions ? framePositions.startY : -1000;
  const lineEndY = framePositions ? framePositions.endY : 1000;
  


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
        const candidateIndex = sensorTrustDecision?.candidates.findIndex(candidate => candidate.id === target.id) ?? -1;
        const isAiRecommendation = sensorTrustDecision?.aiTargetId === target.id;
        const shouldAnnotate = sensorTrustDecision?.enabled && (isAiRecommendation || candidateIndex >= 0);
        const stroke = sensorTrustDecision?.controlLevel === 'review'
          ? '#ff9a2e'
          : isAiRecommendation
            ? '#1ca8ff'
            : '#d6b84a';
        const isReview = sensorTrustDecision?.controlLevel === 'review';
        const displayPosition = target.position;
        const showTrustGlow = trustGlowActive && trustAiRecommendationId === target.id;
        const showManualReviewPulse = trustManualReviewActive && trustAiRecommendationId === target.id;
        const displayNumber = trustDisplayNumbers?.get(target.id);
        const showDisplayNumber = displayNumber !== undefined && (
          selectedTargetId === target.id ||
          trustFocusedTargetId === target.id ||
          showManualReviewPulse
        );
        return (
          <React.Fragment key={target.id}>
            {showManualReviewPulse && displayPosition && (
              <ManualReviewPulse x={displayPosition.x} y={displayPosition.y} />
            )}
            {showTrustGlow && displayPosition && (
              <Rect
                x={displayPosition.x - 28}
                y={displayPosition.y - 28}
                width={56}
                height={56}
                stroke="#69d8ff"
                strokeWidth={2}
                cornerRadius={8}
                dash={[8, 4]}
                shadowColor="#69d8ff"
                shadowBlur={16}
                opacity={0.9}
              />
            )}
            {showDisplayNumber && displayPosition && (
              <Text
                x={displayPosition.x + 14}
                y={displayPosition.y + 12}
                text={`目标${displayNumber}`}
                fill={showManualReviewPulse ? '#c7f8ff' : '#9ddfac'}
                fontSize={11}
                fontFamily="'Share Tech Mono', monospace"
                shadowColor={showManualReviewPulse ? '#69d8ff' : 'transparent'}
                shadowBlur={showManualReviewPulse ? 8 : 0}
                listening={false}
              />
            )}
            {shouldAnnotate && displayPosition && (
              <Group>
                <Rect
                  x={displayPosition.x - 24}
                  y={displayPosition.y - 24}
                  width={48}
                  height={48}
                  stroke={stroke}
                  strokeWidth={isAiRecommendation ? 2 : 1.5}
                  dash={[6, 4]}
                  cornerRadius={4}
                  opacity={0.95}
                />
                <Text
                  x={displayPosition.x + 26}
                  y={displayPosition.y - 24}
                  text={isAiRecommendation
                    ? `${isReview ? 'AI锁定' : 'AI推荐'} ${(sensorTrustDecision.confidence ? sensorTrustDecision.confidence * 100 : 0).toFixed(0)}%`
                    : isReview ? '相似候选' : `备选#${candidateIndex + 1}`}
                  fill={stroke}
                  fontSize={11}
                  fontFamily="monospace"
                />
              </Group>
            )}
            <UnknownTarget
              data={{
                ...target,
                selected: target.id === selectedTargetId
              }}
              color={targetColor}
              framePositions={framePositions}
              scanAngle={scanAngle}
              onTargetClick={onTargetClick}
              cognitiveLoad={cognitiveLoad}
              range={range}
            />
          </React.Fragment>
        );
      })}
    </Group>
  );
};
