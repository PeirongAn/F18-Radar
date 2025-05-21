import { useEffect, useRef } from "react";
import agentStore from "../stores/AgentStore";

interface UseAIAgentOptions {
  isActive: boolean; // 当前是否AI自动处理
  emergency: any;    // 当前临机事件
  onHandleEmergency: (event: any) => void; // 处理临机事件的回调
  getBestThreat?: () => any; // 获取最具威胁项的方法（可选）
}

export function useAIAgent({
  isActive,
  emergency,
  onHandleEmergency,
  getBestThreat
}: UseAIAgentOptions) {
  const timerRef = useRef<number | null>(null);
  const lastHandledRef = useRef<string | null>(null);

  // 生成emergency唯一标识
  const emergencyId = emergency ? JSON.stringify({ event: emergency.event, missileType: emergency.missileType }) : '';

  useEffect(() => {
    if (isActive && emergency && lastHandledRef.current !== emergencyId) {
      // 从 agentStore.currentAILevelConfig 获取延迟，并提供默认值
      const delay = agentStore.currentAILevelConfig?.sa_emergency_delay_ms ?? 1500; // 默认1500ms

      timerRef.current = window.setTimeout(() => {
        if (getBestThreat) {
          const threat = getBestThreat();
          if (threat) onHandleEmergency(threat);
        } else {
          onHandleEmergency(emergency);
        }
        lastHandledRef.current = emergencyId;
      }, delay);
      return () => {
        if (timerRef.current) clearTimeout(timerRef.current);
      };
    }
  }, [isActive, emergencyId, onHandleEmergency, getBestThreat]);
} 