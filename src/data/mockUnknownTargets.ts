import { UnknownTargetData } from '../components/UnknownTarget';

/**
 * 以下是服务端返回的目标数据格式示例
 * 当前这些数据已不再被前端使用
 * 仅作为服务端实现的参考
 */
export const mockUnknownTargets: UnknownTargetData[] = [
  {
    id: 'target-1',
    position: { x: 0, y: 0 }, // 这个位置应由服务端计算
    history: [],              // 历史位置记录可由服务端维护
    speed: 5,                 // 目标速度
    direction: -Math.PI / 2,  // 向上（飞向飞机）
    type: 'army',             // 飞向飞机的目标是敌军
  },
  {
    id: 'target-2',
    position: { x: 0, y: 0 },
    history: [],
    speed: 8,
    direction: -Math.PI / 4,  // 右上方（飞向飞机）
    type: 'army',
  },
  {
    id: 'target-3',
    position: { x: 0, y: 0 },
    history: [],
    speed: 0,                 // 静止的目标
    direction: 0,
    type: 'friend',
  },
  {
    id: 'target-4',
    position: { x: 0, y: 0 },
    history: [],
    speed: 10,
    direction: Math.PI / 4,   // 右下方（飞离飞机）
    type: 'friend',
  },
  {
    id: 'target-5',
    position: { x: 0, y: 0 },
    history: [],
    speed: 12,
    direction: Math.PI * 3 / 4, // 左下方（飞离飞机）
    type: 'friend',
  }
];

/**
 * 服务端示例实现 - 计算目标绝对位置
 * 这个函数已不再被前端使用
 * 仅作为服务端实现的参考
 */
export const calculateTargetPositions = (
  centerX: number, 
  centerY: number,
  offsetsArray: Array<[number, number]> = [
    [-80, -40],  // 目标1偏移 - 飞向飞机
    [20, -60],   // 目标2偏移 - 飞向飞机
    [0, 20],     // 目标3偏移 - 静止
    [-40, 60],   // 目标4偏移 - 飞离飞机 
    [70, 30]     // 目标5偏移 - 飞离飞机
  ]
): UnknownTargetData[] => {
  return mockUnknownTargets.map((target, index) => {
    const [offsetX, offsetY] = offsetsArray[index];
    return {
      ...target,
      position: {
        x: centerX + offsetX,
        y: centerY + offsetY
      }
    };
  });
}; 