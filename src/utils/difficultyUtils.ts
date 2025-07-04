import { useEffect, useRef, useState } from 'react';

/**
 * 自定义hook：检测难度变化并管理弹窗显示
 * @param currentDifficulty 当前难度
 * @param isAIActive AI是否激活
 * @returns 包含弹窗显示状态和关闭弹窗函数的对象
 */
export const useDifficultyChangeDetection = (
  currentDifficulty: string | undefined,
  isAIActive: boolean
) => {
  const [showDifficultyChangeModal, setShowDifficultyChangeModal] = useState(false);
  const previousDifficultyRef = useRef<string | undefined>(undefined);

  // 监听难度变化并发送通知
  useEffect(() => {
    // 仅当难度从一个已定义的值变为另一个已定义的值时，才显示通知
    if (
      previousDifficultyRef.current &&
      currentDifficulty &&
      currentDifficulty !== previousDifficultyRef.current &&
      !isAIActive
    ) {
      setShowDifficultyChangeModal(true);
    }

    // 更新上一个难度的引用
    previousDifficultyRef.current = currentDifficulty;
  }, [currentDifficulty, isAIActive]);

  // 关闭弹窗的函数
  const closeDifficultyChangeModal = () => {
    setShowDifficultyChangeModal(false);
  };

  return {
    showDifficultyChangeModal,
    closeDifficultyChangeModal,
    previousDifficulty: previousDifficultyRef.current
  };
};

/**
 * 工具函数：检查难度是否发生变化
 * @param previousDifficulty 上一个难度
 * @param currentDifficulty 当前难度
 * @param isAIActive AI是否激活
 * @returns 是否应该显示难度变化通知
 */
export const shouldShowDifficultyChange = (
  previousDifficulty: string | undefined,
  currentDifficulty: string | undefined,
  isAIActive: boolean
): boolean => {
  return !!(
    previousDifficulty &&
    currentDifficulty &&
    currentDifficulty !== previousDifficulty &&
    !isAIActive
  );
}; 