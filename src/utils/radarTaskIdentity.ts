export interface RadarInitSettingsIdentity {
  __task_id?: string | number | null;
}

/**
 * AI target selection must wait for the task id acknowledged by the server.
 * The client creates a temporary id while task_start is in flight; treating
 * that id as authoritative lets the first recommendation race with the later
 * init_settings response and then get cleared as if the task had changed.
 */
export const hasAuthoritativeRadarTaskIdentity = (
  taskId: string | number | null | undefined,
  initSettings: RadarInitSettingsIdentity | null | undefined,
): boolean => {
  const serverTaskId = initSettings?.__task_id;
  if (taskId === null || taskId === undefined || serverTaskId === null || serverTaskId === undefined) {
    return false;
  }
  return String(taskId) === String(serverTaskId);
};
