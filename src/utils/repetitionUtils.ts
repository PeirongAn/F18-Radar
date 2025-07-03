// 重复次数处理工具函数

export interface RepetitionInfo {
  current: number;
  total: number;
  scenario_index?: number;
  scenario_total?: number;
  is_practice?: boolean;
  audio_enabled?: boolean;
}

/**
 * 检查当前任务是否已完成所有重复次数
 * @param repetitionInfo 重复信息对象
 * @returns 如果已完成所有重复次数返回true，否则返回false
 */
export const isRepetitionCompleted = (repetitionInfo: RepetitionInfo | null): boolean => {
  if (!repetitionInfo) return false;
  return repetitionInfo.current >= repetitionInfo.total;
};

/**
 * 检查当前任务是否还有剩余重复次数
 * @param repetitionInfo 重复信息对象
 * @returns 如果还有剩余重复次数返回true，否则返回false
 */
export const hasRemainingRepetitions = (repetitionInfo: RepetitionInfo | null): boolean => {
  if (!repetitionInfo) return false;
  return repetitionInfo.current < repetitionInfo.total;
};

/**
 * 获取剩余重复次数
 * @param repetitionInfo 重复信息对象
 * @returns 剩余重复次数，如果没有重复信息则返回0
 */
export const getRemainingRepetitions = (repetitionInfo: RepetitionInfo | null): number => {
  if (!repetitionInfo) return 0;
  return Math.max(0, repetitionInfo.total - repetitionInfo.current);
};

/**
 * 获取重复进度百分比
 * @param repetitionInfo 重复信息对象
 * @returns 进度百分比（0-100），如果没有重复信息则返回0
 */
export const getRepetitionProgress = (repetitionInfo: RepetitionInfo | null): number => {
  if (!repetitionInfo || repetitionInfo.total === 0) return 0;
  return Math.min(100, (repetitionInfo.current / repetitionInfo.total) * 100);
};

/**
 * 格式化重复次数显示文本
 * @param repetitionInfo 重复信息对象
 * @returns 格式化的显示文本
 */
export const formatRepetitionText = (repetitionInfo: RepetitionInfo | null): string => {
  if (!repetitionInfo) return '无重复信息';
  return `${repetitionInfo.current} / ${repetitionInfo.total}`;
};

/**
 * 检查是否为最后一次重复
 * @param repetitionInfo 重复信息对象
 * @returns 如果是最后一次重复返回true，否则返回false
 */
export const isLastRepetition = (repetitionInfo: RepetitionInfo | null): boolean => {
  if (!repetitionInfo) return false;
  return repetitionInfo.current === repetitionInfo.total;
};

/**
 * 检查是否为第一次重复
 * @param repetitionInfo 重复信息对象
 * @returns 如果是第一次重复返回true，否则返回false
 */
export const isFirstRepetition = (repetitionInfo: RepetitionInfo | null): boolean => {
  if (!repetitionInfo) return false;
  return repetitionInfo.current === 1;
}; 