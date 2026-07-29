import { useEffect, useRef } from "react";
import agentStore from "../stores/AgentStore";
import { AIAgentScheduler } from "../utils/aiAgentScheduler";

interface AIAgentEmergency {
  event?: string;
  missileType?: string;
  receivedAt?: string | number;
  timestamp?: string | number;
  id?: string | number;
}

interface UseAIAgentOptions {
  isActive: boolean; // 当前是否AI自动处理
  emergency?: AIAgentEmergency | null; // 当前临机事件
  onHandleEmergency: (event: unknown) => void; // 处理临机事件的回调
  getBestThreat?: () => unknown; // 获取最具威胁项的方法（可选）
}

export const getAIEmergencyId = (emergency?: AIAgentEmergency | null): string => {
  if (!emergency) return '';

  const timestamp = emergency.receivedAt
    ?? emergency.timestamp
    ?? emergency.id
    ?? `${emergency.event}_${emergency.missileType}`;

  return JSON.stringify({
    event: emergency.event,
    missileType: emergency.missileType,
    timestamp,
  });
};

export function useAIAgent({
  isActive,
  emergency,
  onHandleEmergency,
  getBestThreat
}: UseAIAgentOptions) {
  const prevIsActiveRef = useRef(isActive);

  const emergencyId = getAIEmergencyId(emergency);

  const schedulerRef = useRef<AIAgentScheduler | null>(null);
  if (!schedulerRef.current) {
    schedulerRef.current = new AIAgentScheduler<unknown>({
      getDelayMs: () => agentStore.currentAILevelConfig?.threat_select_delay_ms ?? 1500,
      getBestThreat: () => getBestThreat?.() ?? null,
      onHandleEmergency,
    });
  }
  const scheduler = schedulerRef.current!;

  useEffect(() => {
    scheduler.updateCallbacks({
      getDelayMs: () => agentStore.currentAILevelConfig?.threat_select_delay_ms ?? 1500,
      getBestThreat: () => getBestThreat?.() ?? null,
      onHandleEmergency,
    });
  }, [getBestThreat, onHandleEmergency, scheduler]);

  useEffect(() => {
    scheduler.setActive(isActive);
    if (isActive && !prevIsActiveRef.current && !emergencyId) {
      scheduler.scheduleInitialAssessment();
    }
    prevIsActiveRef.current = isActive;
  }, [emergencyId, isActive, scheduler]);

  useEffect(() => {
    if (isActive && emergencyId) {
      scheduler.scheduleEmergency(emergencyId);
    }
  }, [emergencyId, isActive, scheduler]);

  useEffect(() => () => {
    scheduler.dispose();
  }, [scheduler]);
}
