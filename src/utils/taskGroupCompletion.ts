export const clearTaskCompletionForStart = <T extends object, K extends keyof T>(
  state: T,
  taskType: K,
): T => ({
  ...state,
  [taskType]: null,
});

export const getTaskGroupIdFromMessage = (source?: any): string | null => {
  const taskGroupId = source?.task_group_id ?? source?.repetition_info?.task_group_id;
  return taskGroupId === undefined || taskGroupId === null ? null : String(taskGroupId);
};

export const isCompletionForActiveTaskGroup = (
  source: any,
  activeTaskGroupId?: string | null,
): boolean => {
  const completedTaskGroupId = getTaskGroupIdFromMessage(source);
  if (!completedTaskGroupId) return false;
  return !activeTaskGroupId || completedTaskGroupId === String(activeTaskGroupId);
};
