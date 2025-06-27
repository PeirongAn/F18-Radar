import { useEffect, useRef, useState, useMemo } from "react";
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
  const prevIsActiveRef = useRef(isActive);
  const callCountRef = useRef(0);

  // 生成emergency唯一标识，使用稳定的标识符
  const emergencyId = useMemo(() => {
    if (!emergency) return '';
    
    // 使用receivedAt作为唯一标识符，这是每次接收时生成的唯一时间戳
    const timestamp = emergency.receivedAt || emergency.timestamp || emergency.id || `${emergency.event}_${emergency.missileType}`;
    
    const id = JSON.stringify({ 
      event: emergency.event, 
      missileType: emergency.missileType,
      timestamp: timestamp
    });
    
    // console.log("[AI Agent] Generated emergencyId:", id, "for emergency:", emergency);
    return id;
  }, [emergency?.event, emergency?.missileType, emergency?.timestamp, emergency?.id, emergency?.receivedAt]);

  useEffect(() => {
    // 当AI从 `false` 变为 `true` 时触发
    if (isActive && !prevIsActiveRef.current && getBestThreat) {
      const delay = agentStore.currentAILevelConfig?.threat_select_delay_ms ?? 1500;
      console.log("[AI Agent] AI activated. Performing initial threat assessment.2 WITH", delay);
      
      timerRef.current = window.setTimeout(() => {
        const threat = getBestThreat();
        if (threat) {
          onHandleEmergency(threat);
          console.log("[AI Agent] Initial threat handled:", threat);
        } else {
          console.log("[AI Agent] No threats found for initial assessment.");
        }
      }, delay);
    }

    // 更新上一个状态
    prevIsActiveRef.current = isActive;

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [isActive, getBestThreat, onHandleEmergency]);

  useEffect(() => {
    // 添加调用计数
    const callCount = callCountRef.current;
    callCountRef.current += 1;
    console.log(`[AI Agent] useEffect #2 called ${callCount} times, emergencyId: ${emergencyId}, lastHandledRef: ${lastHandledRef.current}`);
    
    if (isActive && emergency && lastHandledRef.current !== emergencyId) {
      console.log("[AI Agent] AI activated. Performing initial threat assessment. 1 WITH", isActive, emergencyId, lastHandledRef.current);
      // 从 agentStore.currentAILevelConfig 获取延迟，并提供默认值
      const delay = agentStore.currentAILevelConfig?.threat_select_delay_ms ?? 1500; // 默认1500ms
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