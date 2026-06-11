import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  SensorAIRecommendation,
  SensorCandidateEvidence,
  SensorTrustDecision,
  TrustInteractionEvent,
  TrustCalibrationConfig,
  TrustState,
} from "../types/trustCalibration";
import {
  buildTrustCalibrationLogPayload,
  buildTrustBehaviorMetricsFromEvents,
  createTrustInteractionEvent,
  createSensorCandidates,
  debugTrustInteractionEvent,
  evaluateSensorTrustDecision,
  mergeTrustCalibrationConfig,
  normalizeConfidence,
} from "../utils/trustCalibration";

type SensorCandidateInput = NonNullable<SensorCandidateEvidence["target"]>;

export function useSensorTrustCalibration({
  config,
  externalTargets,
  iffMode,
  taskKey,
}: {
  config?: Partial<TrustCalibrationConfig> | null;
  externalTargets: SensorCandidateInput[];
  iffMode: boolean;
  taskKey?: string | number | null;
}) {
  const mergedConfig = useMemo(() => mergeTrustCalibrationConfig(config), [config]);
  const [recommendation, setRecommendation] = useState<SensorAIRecommendation | null>(null);
  const [trustEventHistory, setTrustEventHistory] = useState<TrustInteractionEvent[]>([]);
  const [evidenceViewed, setEvidenceViewed] = useState(false);
  const [manualReviewRequested, setManualReviewRequested] = useState(false);
  const [manualReviewDone, setManualReviewDone] = useState(false);
  const [tick, setTick] = useState(Date.now());
  const previousTrustStateRef = useRef<TrustState>("normal");
  const acceptedRecommendationRef = useRef<string | null>(null);
  const latestTrustEventsRef = useRef<TrustInteractionEvent[]>([]);

  useEffect(() => {
    setRecommendation(null);
    setTrustEventHistory([]);
    setEvidenceViewed(false);
    setManualReviewRequested(false);
    setManualReviewDone(false);
    previousTrustStateRef.current = "normal";
    acceptedRecommendationRef.current = null;
    latestTrustEventsRef.current = [];
  }, [taskKey]);

  useEffect(() => {
    const timer = window.setInterval(() => setTick(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const rememberTrustEvents = useCallback((events: TrustInteractionEvent | TrustInteractionEvent[]) => {
    const nextEvents = Array.isArray(events) ? events : [events];
    latestTrustEventsRef.current = nextEvents;
    nextEvents.forEach(debugTrustInteractionEvent);
    setTrustEventHistory(history => {
      const historyLimit = Math.max(20, mergedConfig.sensor.window_size * 6);
      return [...history, ...nextEvents].slice(-historyLimit);
    });
  }, [mergedConfig.sensor.window_size]);

  const recordAIRecommendation = useCallback((target: SensorCandidateInput, fallbackConfidence?: number) => {
    if (!target?.id) return undefined;
    const confidence = normalizeConfidence(
      target.threat_score ?? fallbackConfidence,
      fallbackConfidence ?? 0.75
    );
    const nextRecommendation: SensorAIRecommendation = {
      targetId: target.id,
      confidence,
      recommendedAt: Date.now(),
      candidates: createSensorCandidates(externalTargets, target.id, confidence),
    };
    const now = Date.now();
    setRecommendation(nextRecommendation);
    setEvidenceViewed(false);
    setManualReviewRequested(false);
    setManualReviewDone(false);
    acceptedRecommendationRef.current = null;
    const nextDecision = evaluateSensorTrustDecision({
      config: mergedConfig,
      recommendation: nextRecommendation,
      iffMode,
      behaviorMetrics: buildTrustBehaviorMetricsFromEvents(trustEventHistory, mergedConfig.sensor.window_size),
      evidenceViewed: false,
      manualReviewRequested: false,
      manualReviewDone: false,
      previousTrustState: previousTrustStateRef.current,
      now,
    });
    const trustEvents = [
      createTrustInteractionEvent({
        actor: "ai",
        task: "sensor",
        eventType: "ai_recommendation_shown",
        recommendationId: nextRecommendation.targetId,
        selectedId: nextRecommendation.targetId,
        confidence,
        candidateGap: nextDecision.candidateGap,
        riskFlags: nextDecision.triggers,
        source: "sensor.recordAIRecommendation",
      }),
      createTrustInteractionEvent({
        actor: "ai",
        task: "sensor",
        eventType: "ai_auto_action",
        recommendationId: nextRecommendation.targetId,
        selectedId: nextRecommendation.targetId,
        confidence,
        candidateGap: nextDecision.candidateGap,
        riskFlags: nextDecision.triggers,
        source: "sensor.aiTargetSelect",
      }),
    ];
    rememberTrustEvents(trustEvents);
    return {
      trust_calibration: buildTrustCalibrationLogPayload(nextDecision),
      trust_events: trustEvents,
    };
  }, [externalTargets, iffMode, mergedConfig, rememberTrustEvents, trustEventHistory]);

  const recordManualSelection = useCallback((targetId?: string) => {
    if (!targetId || !recommendation) return;
    const now = Date.now();
    const eventType = targetId !== recommendation.targetId ? "reject" : "direct_accept";
    if (eventType === "direct_accept") {
      acceptedRecommendationRef.current = `${recommendation.targetId}:${recommendation.recommendedAt}`;
    }
    const latencyMs = Math.max(0, now - recommendation.recommendedAt);
    const trustEvent = createTrustInteractionEvent({
      actor: "human",
      task: "sensor",
      eventType: eventType === "direct_accept" ? "human_accept" : "human_reject",
      recommendationId: recommendation.targetId,
      selectedId: targetId,
      confidence: recommendation.confidence,
      latencyMs,
      riskFlags: [],
      source: "sensor.recordManualSelection",
      metadata: { evidenceViewed },
    });
    rememberTrustEvents(trustEvent);
    if (manualReviewRequested) {
      setManualReviewDone(true);
      setManualReviewRequested(false);
    }
  }, [evidenceViewed, manualReviewRequested, recommendation, rememberTrustEvents]);

  const recordRecommendationAcceptance = useCallback((targetId?: string) => {
    if (!targetId || !recommendation || targetId !== recommendation.targetId) return;

    const acceptKey = `${recommendation.targetId}:${recommendation.recommendedAt}`;
    if (acceptedRecommendationRef.current === acceptKey) return;
    acceptedRecommendationRef.current = acceptKey;

    const now = Date.now();
    const latencyMs = Math.max(0, now - recommendation.recommendedAt);
    const trustEvent = createTrustInteractionEvent({
      actor: "human",
      task: "sensor",
      eventType: "human_accept",
      recommendationId: recommendation.targetId,
      selectedId: targetId,
      confidence: recommendation.confidence,
      latencyMs,
      riskFlags: [],
      source: "sensor.recordRecommendationAcceptance",
      metadata: { evidenceViewed },
    });
    rememberTrustEvents(trustEvent);
    if (manualReviewRequested) {
      setManualReviewDone(true);
      setManualReviewRequested(false);
    }
  }, [evidenceViewed, manualReviewRequested, recommendation, rememberTrustEvents]);

  const markEvidenceViewed = useCallback(() => {
    const trustEvent = createTrustInteractionEvent({
      actor: "human",
      task: "sensor",
      eventType: "evidence_viewed",
      recommendationId: recommendation?.targetId,
      selectedId: recommendation?.targetId,
      confidence: recommendation?.confidence,
      riskFlags: [],
      source: "sensor.markEvidenceViewed",
    });
    rememberTrustEvents(trustEvent);
    setEvidenceViewed(true);
  }, [recommendation, rememberTrustEvents]);

  const requestManualReview = useCallback(() => {
    const trustEvent = createTrustInteractionEvent({
      actor: "human",
      task: "sensor",
      eventType: "manual_review_requested",
      recommendationId: recommendation?.targetId,
      selectedId: recommendation?.targetId,
      confidence: recommendation?.confidence,
      riskFlags: [],
      source: "sensor.requestManualReview",
    });
    rememberTrustEvents(trustEvent);
    setManualReviewRequested(true);
  }, [recommendation, rememberTrustEvents]);

  const sensorTrustDecision: SensorTrustDecision = useMemo(() => {
    return evaluateSensorTrustDecision({
      config: mergedConfig,
      recommendation,
      iffMode,
      behaviorMetrics: buildTrustBehaviorMetricsFromEvents(trustEventHistory, mergedConfig.sensor.window_size),
      evidenceViewed,
      manualReviewRequested,
      manualReviewDone,
      previousTrustState: previousTrustStateRef.current,
      now: tick,
    });
  }, [
    mergedConfig,
    recommendation,
    iffMode,
    trustEventHistory,
    evidenceViewed,
    manualReviewRequested,
    manualReviewDone,
    tick,
  ]);

  useEffect(() => {
    if (sensorTrustDecision.enabled) {
      previousTrustStateRef.current = sensorTrustDecision.trustState;
    }
  }, [sensorTrustDecision]);

  const buildLogExtra = useCallback(() => ({
    trust_calibration: buildTrustCalibrationLogPayload(sensorTrustDecision),
    trust_events: latestTrustEventsRef.current,
  }), [sensorTrustDecision]);

  return {
    sensorTrustDecision,
    recordAIRecommendation,
    recordManualSelection,
    recordRecommendationAcceptance,
    markEvidenceViewed,
    markManualReviewDone: requestManualReview,
    buildLogExtra,
  };
}
