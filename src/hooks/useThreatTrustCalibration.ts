import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ThreatCandidateEvidence,
  ThreatTrustDecision,
  TrustInteractionEvent,
  TrustCalibrationConfig,
  TrustState,
} from "../types/trustCalibration";
import {
  buildTrustCalibrationLogPayload,
  buildTrustBehaviorMetricsFromEvents,
  createTrustInteractionEvent,
  debugTrustInteractionEvent,
  evaluateThreatTrustDecision,
  mergeTrustCalibrationConfig,
} from "../utils/trustCalibration";

type RankingChange = {
  previousTopThreatId: string | null;
  previousTopThreatRank?: number;
};

type ThreatInput = {
  id: string;
  label?: string;
  source?: string;
  score?: number;
  is_missile?: boolean;
  type?: string;
  priority?: string;
  [key: string]: unknown;
};

function mapThreatCandidate(threat: ThreatInput): ThreatCandidateEvidence {
  return {
    id: threat.id,
    label: threat.label || threat.source || threat.id || "未知威胁",
    score: typeof threat.score === "number" ? threat.score : 0,
    reason: threat.is_missile || threat.type?.toLowerCase?.().includes("missile")
      ? "临机事件 / 导弹威胁"
      : threat.priority === "high" || threat.type?.includes("Primary")
        ? "高优先级目标"
        : "候选威胁目标",
    threat,
  };
}

export function useThreatTrustCalibration({
  config,
  threats,
  generationTimestamp,
  taskKey,
}: {
  config?: Partial<TrustCalibrationConfig> | null;
  threats: ThreatInput[];
  generationTimestamp?: number | null;
  taskKey?: string | number | null;
}) {
  const mergedConfig = useMemo(() => mergeTrustCalibrationConfig(config), [config]);
  const [trustEventHistory, setTrustEventHistory] = useState<TrustInteractionEvent[]>([]);
  const [evidenceViewed, setEvidenceViewed] = useState(false);
  const [manualReviewDone, setManualReviewDone] = useState(false);
  const [tick, setTick] = useState(Date.now());
  const previousRankByIdRef = useRef<Record<string, number>>({});
  const previousTopThreatIdRef = useRef<string | null>(null);
  const presentedAtRef = useRef<number>(Date.now());
  const [rankingChange, setRankingChange] = useState<RankingChange>({ previousTopThreatId: null });
  const previousTrustStateRef = useRef<TrustState>("normal");
  const latestTrustEventsRef = useRef<TrustInteractionEvent[]>([]);

  useEffect(() => {
    setTrustEventHistory([]);
    setEvidenceViewed(false);
    setManualReviewDone(false);
    setRankingChange({ previousTopThreatId: null });
    previousRankByIdRef.current = {};
    previousTopThreatIdRef.current = null;
    presentedAtRef.current = Date.now();
    previousTrustStateRef.current = "normal";
    latestTrustEventsRef.current = [];
  }, [taskKey]);

  useEffect(() => {
    const timer = window.setInterval(() => setTick(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const candidates = useMemo(() => {
    return [...threats]
      .filter(threat => threat?.id)
      .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
      .slice(0, 3)
      .map(mapThreatCandidate);
  }, [threats]);

  const rememberTrustEvents = useCallback((events: TrustInteractionEvent | TrustInteractionEvent[]) => {
    const nextEvents = Array.isArray(events) ? events : [events];
    latestTrustEventsRef.current = nextEvents;
    nextEvents.forEach(debugTrustInteractionEvent);
    setTrustEventHistory(history => {
      const historyLimit = Math.max(20, mergedConfig.threat.window_size * 6);
      return [...history, ...nextEvents].slice(-historyLimit);
    });
  }, [mergedConfig.threat.window_size]);

  const threatTrustDecision: ThreatTrustDecision = useMemo(() => {
    return evaluateThreatTrustDecision({
      config: mergedConfig,
      candidates,
      generationTimestamp,
      previousTopThreatId: rankingChange.previousTopThreatId,
      previousTopThreatRank: rankingChange.previousTopThreatRank,
      behaviorMetrics: buildTrustBehaviorMetricsFromEvents(trustEventHistory, mergedConfig.threat.window_size),
      evidenceViewed,
      manualReviewDone,
      previousTrustState: previousTrustStateRef.current,
      now: tick,
    });
  }, [
    mergedConfig,
    candidates,
    generationTimestamp,
    rankingChange,
    trustEventHistory,
    evidenceViewed,
    manualReviewDone,
    tick,
  ]);

  useEffect(() => {
    if (threatTrustDecision.enabled) {
      previousTrustStateRef.current = threatTrustDecision.trustState;
    }
  }, [threatTrustDecision]);

  useEffect(() => {
    const nextTopThreatId = candidates[0]?.id ?? null;
    const previousTopThreatId = previousTopThreatIdRef.current;
    const previousRankById = previousRankByIdRef.current;
    if (nextTopThreatId && nextTopThreatId !== previousTopThreatId) {
      presentedAtRef.current = Date.now();
    }
    setRankingChange({
      previousTopThreatId,
      previousTopThreatRank: nextTopThreatId ? previousRankById[nextTopThreatId] : undefined,
    });
    previousTopThreatIdRef.current = nextTopThreatId;
    previousRankByIdRef.current = candidates.reduce<Record<string, number>>((rankById, candidate, index) => {
      rankById[candidate.id] = index + 1;
      return rankById;
    }, {});
  }, [candidates]);

  const recordThreatSelection = useCallback((threatId?: string, eventOwner: "AI" | "manual" = "manual") => {
    if (!threatId || !candidates[0]?.id) return;
    const now = Date.now();
    const isHuman = eventOwner !== "AI";
    const acceptedTopThreat = threatId === candidates[0].id;
    const latencyMs = Math.max(0, now - presentedAtRef.current);
    const trustEvent = createTrustInteractionEvent({
      actor: isHuman ? "human" : "ai",
      task: "threat",
      eventType: isHuman
        ? acceptedTopThreat
          ? "human_accept"
          : "human_reject"
        : "ai_auto_action",
      recommendationId: candidates[0].id,
      selectedId: threatId,
      confidence: candidates[0].score,
      candidateGap: candidates.length > 1 ? Math.abs(candidates[0].score - candidates[1].score) : undefined,
      latencyMs,
      riskFlags: threatTrustDecision.triggers,
      source: "threat.recordThreatSelection",
      metadata: { evidenceViewed, eventOwner },
    });
    rememberTrustEvents(trustEvent);
  }, [candidates, evidenceViewed, rememberTrustEvents, threatTrustDecision]);

  const recordResultConfirmed = useCallback((selectedThreatId?: string) => {
    const selectedId = selectedThreatId ?? candidates[0]?.id;
    if (!selectedId || !candidates[0]?.id) return;
    const now = Date.now();
    const latencyMs = Math.max(0, now - presentedAtRef.current);
    const trustEvent = createTrustInteractionEvent({
      actor: "human",
      task: "threat",
      eventType: "human_result_confirmed",
      recommendationId: candidates[0].id,
      selectedId,
      confidence: candidates[0].score,
      candidateGap: candidates.length > 1 ? Math.abs(candidates[0].score - candidates[1].score) : undefined,
      latencyMs,
      riskFlags: threatTrustDecision.triggers,
      source: "threat.recordResultConfirmed",
      metadata: {
        evidenceViewed,
        acceptedTopThreat: selectedId === candidates[0].id,
      },
    });
    rememberTrustEvents(trustEvent);
  }, [candidates, evidenceViewed, rememberTrustEvents, threatTrustDecision]);

  const markEvidenceViewed = useCallback(() => {
    const trustEvent = createTrustInteractionEvent({
      actor: "human",
      task: "threat",
      eventType: "evidence_viewed",
      recommendationId: candidates[0]?.id,
      selectedId: candidates[0]?.id,
      confidence: candidates[0]?.score,
      candidateGap: candidates.length > 1 ? Math.abs(candidates[0].score - candidates[1].score) : undefined,
      riskFlags: threatTrustDecision.triggers,
      source: "threat.markEvidenceViewed",
    });
    rememberTrustEvents(trustEvent);
    setEvidenceViewed(true);
  }, [candidates, rememberTrustEvents, threatTrustDecision]);

  const markManualReviewDone = useCallback(() => {
    const trustEvent = createTrustInteractionEvent({
      actor: "human",
      task: "threat",
      eventType: "manual_review_done",
      recommendationId: candidates[0]?.id,
      selectedId: candidates[0]?.id,
      confidence: candidates[0]?.score,
      candidateGap: candidates.length > 1 ? Math.abs(candidates[0].score - candidates[1].score) : undefined,
      riskFlags: threatTrustDecision.triggers,
      source: "threat.markManualReviewDone",
    });
    rememberTrustEvents(trustEvent);
    setManualReviewDone(true);
  }, [candidates, rememberTrustEvents, threatTrustDecision]);

  const buildLogExtra = useCallback(() => ({
    trust_calibration: buildTrustCalibrationLogPayload(threatTrustDecision),
    trust_events: latestTrustEventsRef.current,
  }), [threatTrustDecision]);

  return {
    threatTrustDecision,
    recordThreatSelection,
    recordResultConfirmed,
    markEvidenceViewed,
    markManualReviewDone,
    buildLogExtra,
  };
}
