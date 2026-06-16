import {
  SensorAIRecommendation,
  SensorCandidateEvidence,
  SensorTrustDecision,
  ThreatCandidateEvidence,
  TrustInteractionEvent,
  ThreatTrustDecision,
  TrustBehaviorMetrics,
  TrustCalibrationConfig,
  TrustCalibrationLogPayload,
  TrustCalibrationStateConfig,
  TrustConfigSnapshot,
  TrustControlTrigger,
  TrustState,
} from "../types/trustCalibration";

export const DEFAULT_TRUST_CALIBRATION_CONFIG: TrustCalibrationConfig = {
  enabled: true,
  state: {
    sensor: "normal",
    threat: "normal",
  },
  sensor: {
    high_confidence: 0.85,
    low_confidence_min: 0.6,
    low_confidence_max: 0.7,
    candidate_gap_threshold: 0.1,
    unconfirmed_timeout_ms: 5000,
    consecutive_reject_threshold: 2,
    direct_accept_threshold: 2,
    window_size: 5,
    hysteresis: 1,
    latency_threshold_ms: 4500,
    require_evidence_before_confirm: true,
    min_truth_coverage: 0.5,
    unwarranted_reject_threshold: 2,
    unwarranted_accept_threshold: 1,
  },
  threat: {
    score_gap_threshold: 0.1,
    data_delay_ms: 1800,
    unconfirmed_timeout_ms: 5000,
    consecutive_reject_threshold: 2,
    direct_accept_threshold: 2,
    window_size: 5,
    hysteresis: 1,
    latency_threshold_ms: 4500,
    require_evidence_before_submit: true,
    min_truth_coverage: 0.5,
    unwarranted_reject_threshold: 2,
    unwarranted_accept_threshold: 1,
  },
  display: {
    show_explanation_panel: true,
    show_candidate_comparison: true,
    show_data_quality_bar: true,
    show_capability_boundary: true,
    block_one_click_on_low_confidence: true,
  },
};

export function mergeTrustCalibrationConfig(
  config?: Partial<TrustCalibrationConfig> | null
): TrustCalibrationConfig {
  const incomingState = (config as { state?: TrustCalibrationStateConfig | TrustState } | null | undefined)?.state;
  const state = typeof incomingState === "string"
    ? { sensor: incomingState, threat: incomingState }
    : {
      ...DEFAULT_TRUST_CALIBRATION_CONFIG.state,
      ...(incomingState ?? {}),
    };
  return {
    ...DEFAULT_TRUST_CALIBRATION_CONFIG,
    ...(config ?? {}),
    state,
    sensor: {
      ...DEFAULT_TRUST_CALIBRATION_CONFIG.sensor,
      ...(config?.sensor ?? {}),
    },
    threat: {
      ...DEFAULT_TRUST_CALIBRATION_CONFIG.threat,
      ...(config?.threat ?? {}),
    },
    display: {
      ...DEFAULT_TRUST_CALIBRATION_CONFIG.display,
      ...(config?.display ?? {}),
    },
  };
}

export function createTrustInteractionEvent(
  input: Omit<TrustInteractionEvent, "version" | "timestamp" | "riskFlags"> & {
    timestamp?: number;
    riskFlags?: TrustControlTrigger[];
  }
): TrustInteractionEvent {
  return {
    version: 1,
    timestamp: input.timestamp ?? Date.now(),
    riskFlags: input.riskFlags ?? [],
    actor: input.actor,
    task: input.task,
    eventType: input.eventType,
    recommendationId: input.recommendationId,
    selectedId: input.selectedId,
    confidence: input.confidence,
    candidateGap: input.candidateGap,
    latencyMs: input.latencyMs,
    source: input.source,
    metadata: input.metadata,
    aiRecommendationCorrect: input.aiRecommendationCorrect,
    humanDecisionCorrect: input.humanDecisionCorrect,
    outcomeSource: input.outcomeSource,
  };
}

export function debugTrustInteractionEvent(event: TrustInteractionEvent): void {
  if (typeof console !== "undefined") {
    console.debug("[TrustEvent]", event);
  }
}

function readBooleanMetadata(event: TrustInteractionEvent, key: string): boolean | undefined {
  const value = event.metadata?.[key];
  return typeof value === "boolean" ? value : undefined;
}

function hasEvidenceViewedBeforeDecision(
  event: TrustInteractionEvent,
  events: TrustInteractionEvent[]
): boolean {
  const metadataValue = readBooleanMetadata(event, "evidenceViewed");
  if (metadataValue !== undefined) return metadataValue;
  if (!event.recommendationId) return false;

  return events.some(candidate =>
    candidate.actor === "human" &&
    candidate.eventType === "evidence_viewed" &&
    candidate.recommendationId === event.recommendationId &&
    candidate.timestamp <= event.timestamp
  );
}

export function buildTrustBehaviorMetricsFromEvents(
  events: TrustInteractionEvent[],
  windowSize: number
): TrustBehaviorMetrics {
  const decisionEvents = events
    .filter(event =>
      event.actor === "human" &&
      (event.eventType === "human_accept" || event.eventType === "human_reject")
    )
    .slice(-Math.max(1, windowSize));
  const latencyEvents = decisionEvents
    .filter(event => typeof event.latencyMs === "number" && Number.isFinite(event.latencyMs) && event.latencyMs >= 0);
  const consecutiveRejectCount = decisionEvents
    .slice()
    .reverse()
    .findIndex(event => event.eventType !== "human_reject");
  const trailingRejectCount = consecutiveRejectCount === -1
    ? decisionEvents.length
    : consecutiveRejectCount;

  let truthKnownCount = 0;
  let aiCorrectCount = 0;
  let aiIncorrectCount = 0;
  let unwarrantedRejectCount = 0;
  let justifiedRejectCount = 0;
  let unwarrantedAcceptCount = 0;
  for (const event of decisionEvents) {
    const aiCorrect = event.aiRecommendationCorrect;
    if (typeof aiCorrect !== "boolean") continue; // 真值未知，跳过真值统计
    truthKnownCount += 1;
    if (aiCorrect) aiCorrectCount += 1;
    else aiIncorrectCount += 1;

    if (event.eventType === "human_reject") {
      if (aiCorrect) unwarrantedRejectCount += 1; // 拒了对的
      else justifiedRejectCount += 1; // 应该拒
    } else if (
      event.eventType === "human_accept" &&
      !aiCorrect &&
      !hasEvidenceViewedBeforeDecision(event, events)
    ) {
      unwarrantedAcceptCount += 1; // 无证据接受了错的
    }
  }

  return {
    sampleCount: decisionEvents.length,
    rejectCount: decisionEvents.filter(event => event.eventType === "human_reject").length,
    consecutiveRejectCount: trailingRejectCount,
    directAcceptCount: decisionEvents.filter(event =>
      event.eventType === "human_accept" &&
      !hasEvidenceViewedBeforeDecision(event, events)
    ).length,
    evidenceViewedCount: decisionEvents.filter(event => hasEvidenceViewedBeforeDecision(event, events)).length,
    averageConfirmationLatencyMs: latencyEvents.length > 0
      ? latencyEvents.reduce((total, event) => total + (event.latencyMs ?? 0), 0) / latencyEvents.length
      : undefined,
    truthKnownCount,
    aiCorrectCount,
    aiIncorrectCount,
    unwarrantedRejectCount,
    justifiedRejectCount,
    unwarrantedAcceptCount,
    truthCoverage: decisionEvents.length > 0 ? truthKnownCount / decisionEvents.length : 0,
  };
}

export function buildTrustConfigSnapshot(config: TrustCalibrationConfig): TrustConfigSnapshot {
  return {
    enabled: config.enabled,
    high_confidence: config.sensor.high_confidence,
    low_confidence_max: config.sensor.low_confidence_max,
    candidate_gap_threshold: config.sensor.candidate_gap_threshold,
    score_gap_threshold: config.threat.score_gap_threshold,
    data_delay_ms: config.threat.data_delay_ms,
    window_size: Math.max(config.sensor.window_size, config.threat.window_size),
    hysteresis: Math.max(config.sensor.hysteresis, config.threat.hysteresis),
    latency_threshold_ms: Math.max(config.sensor.latency_threshold_ms, config.threat.latency_threshold_ms),
    block_one_click_on_low_confidence: config.display.block_one_click_on_low_confidence,
  };
}

export function normalizeConfidence(value: number | undefined, fallback = 0.75): number {
  if (typeof value !== "number" || Number.isNaN(value)) return fallback;
  if (value > 1) return Math.max(0, Math.min(1, value / 100));
  return Math.max(0, Math.min(1, value));
}

export function normalizeTimestampMs(value: number | undefined | null, fallback = Date.now()): number {
  if (typeof value !== "number" || Number.isNaN(value) || value <= 0) return fallback;
  if (value > 1e14) return Math.round(value / 1000);
  if (value < 1e11) return Math.round(value * 1000);
  return Math.round(value);
}

export function getCandidateGap(candidates: Array<{ confidence?: number; score?: number }>): number | undefined {
  if (candidates.length < 2) return undefined;
  const values = candidates
    .map(candidate => candidate.confidence ?? candidate.score)
    .filter((value): value is number => typeof value === "number" && !Number.isNaN(value))
    .sort((a, b) => b - a);
  if (values.length < 2) return undefined;
  return Math.abs(values[0] - values[1]);
}

export interface TrustStateEvaluation {
  trustState: Exclude<TrustState, "disabled">;
  underTrust: boolean;
  overTrust: boolean;
  triggers: TrustControlTrigger[];
  /** true 表示真值覆盖不足、状态由行为启发式推断，仅供软提示，不应触发强干预 */
  provisional: boolean;
}

export interface EvaluateTrustStateInput {
  metrics: TrustBehaviorMetrics;
  consecutiveRejectThreshold: number;
  directAcceptThreshold: number;
  latencyThresholdMs: number;
  hysteresis: number;
  previousTrustState?: TrustState;
  minTruthCoverage?: number;
  unwarrantedRejectThreshold?: number;
  unwarrantedAcceptThreshold?: number;
}

/**
 * 信任状态判定：真值优先，行为兜底。
 * - 真值覆盖率达标时：under/over 严格按「与真值不一致」定义（拒了对的 / 接了错的）。
 * - 覆盖不足时：退回行为启发式，但标记 provisional，仅作软提示。
 */
export function evaluateTrustState(input: EvaluateTrustStateInput): TrustStateEvaluation {
  const { metrics } = input;
  const minTruthCoverage = input.minTruthCoverage ?? 0.5;
  const truthReliable = metrics.truthKnownCount > 0 && metrics.truthCoverage >= minTruthCoverage;

  if (truthReliable) {
    const unwarrantedRejectThreshold = Math.max(1, input.unwarrantedRejectThreshold ?? 2);
    const unwarrantedAcceptThreshold = Math.max(1, input.unwarrantedAcceptThreshold ?? 1);
    const underTrust = metrics.unwarrantedRejectCount >= unwarrantedRejectThreshold;
    const overTrust = metrics.unwarrantedAcceptCount >= unwarrantedAcceptThreshold;
    const triggers: TrustControlTrigger[] = [];
    if (underTrust) triggers.push("unwarranted_reject");
    if (overTrust) triggers.push("unwarranted_accept");
    return {
      trustState: overTrust ? "over_trust" : underTrust ? "under_trust" : "normal",
      underTrust,
      overTrust,
      triggers,
      provisional: false,
    };
  }

  const behavioral = evaluateTrustStateBehavioral(input);
  const flagged = behavioral.underTrust || behavioral.overTrust;
  return {
    ...behavioral,
    triggers: flagged ? [...behavioral.triggers, "low_truth_coverage"] : behavioral.triggers,
    provisional: true,
  };
}

function evaluateTrustStateBehavioral(
  input: EvaluateTrustStateInput
): Omit<TrustStateEvaluation, "provisional"> {
  const { metrics } = input;
  const previousTrustState = input.previousTrustState === "disabled" ? "normal" : input.previousTrustState;
  const hysteresis = Math.max(0, input.hysteresis);
  const rejectThreshold = Math.max(1, input.consecutiveRejectThreshold);
  const directAcceptThreshold = Math.max(1, input.directAcceptThreshold);
  const latencyThreshold = Math.max(1, input.latencyThresholdMs);
  const evidenceViewRate =
    metrics.sampleCount > 0 ? metrics.evidenceViewedCount / metrics.sampleCount : 1;

  const rejectEntry = metrics.consecutiveRejectCount >= rejectThreshold;
  const rejectExit = metrics.consecutiveRejectCount >= Math.max(1, rejectThreshold - hysteresis);
  const latencyEntry =
    metrics.averageConfirmationLatencyMs !== undefined &&
    metrics.averageConfirmationLatencyMs >= latencyThreshold;
  const latencyExit =
    metrics.averageConfirmationLatencyMs !== undefined &&
    metrics.averageConfirmationLatencyMs >= Math.max(1, latencyThreshold - hysteresis * 500);
  const directAcceptEntry =
    metrics.directAcceptCount >= directAcceptThreshold &&
    evidenceViewRate < 0.5;
  const directAcceptExit =
    metrics.directAcceptCount >= Math.max(1, directAcceptThreshold - hysteresis) &&
    evidenceViewRate < 0.75;

  const underTrust =
    previousTrustState === "under_trust"
      ? rejectExit || latencyExit
      : rejectEntry || latencyEntry;
  const overTrust =
    previousTrustState === "over_trust"
      ? directAcceptExit
      : directAcceptEntry;

  const triggers: TrustControlTrigger[] = [];
  if (underTrust && metrics.consecutiveRejectCount > 0) triggers.push("consecutive_reject");
  if (underTrust && (latencyEntry || latencyExit)) triggers.push("confirmation_latency");
  if (overTrust) triggers.push("direct_accept_without_evidence");

  return {
    trustState: overTrust ? "over_trust" : underTrust ? "under_trust" : "normal",
    underTrust,
    overTrust,
    triggers,
  };
}

export function evaluateSensorTaskRisk(input: {
  confidence: number;
  candidateGap?: number;
  recommendationAgeMs: number;
  iffMode: boolean;
  isEnemyRecommendation: boolean;
  config: TrustCalibrationConfig["sensor"];
}): {
  reviewRisk: boolean;
  explainRisk: boolean;
  triggers: TrustControlTrigger[];
} {
  const { config } = input;
  const triggers: TrustControlTrigger[] = [];
  const highConfidenceUnconfirmed =
    input.confidence >= config.high_confidence &&
    input.recommendationAgeMs >= config.unconfirmed_timeout_ms;
  const lowConfidence = input.confidence <= config.low_confidence_max;
  const candidateClose =
    input.candidateGap !== undefined &&
    input.candidateGap < config.candidate_gap_threshold;
  const iffUnconfirmed = !input.iffMode && input.isEnemyRecommendation;

  if (highConfidenceUnconfirmed) triggers.push("high_confidence_unconfirmed");
  if (lowConfidence) triggers.push("low_confidence");
  if (candidateClose) triggers.push("candidate_close");
  if (iffUnconfirmed) triggers.push("iff_unconfirmed");

  return {
    reviewRisk: lowConfidence || candidateClose || iffUnconfirmed,
    explainRisk: highConfidenceUnconfirmed,
    triggers,
  };
}

export function evaluateThreatTaskRisk(input: {
  scoreGap?: number;
  dataDelayMs?: number;
  rankingChanged: boolean;
  config: TrustCalibrationConfig["threat"];
}): {
  reviewRisk: boolean;
  explainRisk: boolean;
  triggers: TrustControlTrigger[];
} {
  const { config } = input;
  const triggers: TrustControlTrigger[] = [];
  const scoreGapSmall =
    input.scoreGap !== undefined &&
    input.scoreGap < config.score_gap_threshold;
  const dataDelay =
    input.dataDelayMs !== undefined &&
    input.dataDelayMs > config.data_delay_ms;
  const unconfirmed =
    input.dataDelayMs !== undefined &&
    input.dataDelayMs >= config.unconfirmed_timeout_ms;

  if (input.rankingChanged) triggers.push("ranking_changed");
  if (scoreGapSmall) triggers.push("score_gap_small");
  if (dataDelay) triggers.push("data_delay");

  return {
    reviewRisk: scoreGapSmall || dataDelay,
    explainRisk: input.rankingChanged || unconfirmed,
    triggers,
  };
}

function disabledSensorDecision(config: TrustCalibrationConfig): SensorTrustDecision {
  return {
    task: "sensor",
    enabled: false,
    trustState: "disabled",
    controlLevel: "none",
    triggers: [],
    evidenceViewed: false,
    manualReviewRequested: false,
    manualReviewDone: false,
    blockedOneClick: false,
    primaryMessage: "",
    recommendationAgeMs: 0,
    iffPending: false,
    candidates: [],
    configSnapshot: buildTrustConfigSnapshot(config),
  };
}

function disabledThreatDecision(config: TrustCalibrationConfig): ThreatTrustDecision {
  return {
    task: "threat",
    enabled: false,
    trustState: "disabled",
    controlLevel: "none",
    triggers: [],
    evidenceViewed: false,
    manualReviewRequested: false,
    manualReviewDone: false,
    blockedOneClick: false,
    primaryMessage: "",
    recommendationAgeMs: 0,
    rankingUnstable: false,
    rankingChanged: false,
    candidates: [],
    configSnapshot: buildTrustConfigSnapshot(config),
  } as ThreatTrustDecision;
}

export function evaluateSensorTrustDecision(input: {
  config: TrustCalibrationConfig;
  recommendation?: SensorAIRecommendation | null;
  iffMode: boolean;
  behaviorMetrics: TrustBehaviorMetrics;
  evidenceViewed: boolean;
  manualReviewRequested?: boolean;
  manualReviewDone: boolean;
  previousTrustState?: TrustState;
  now: number;
}): SensorTrustDecision {
  const { config, recommendation } = input;
  if (!config.enabled || !recommendation) return disabledSensorDecision(config);

  const sensorConfig = config.sensor;
  const confidence = normalizeConfidence(recommendation.confidence);
  const ageMs = Math.max(0, input.now - recommendation.recommendedAt);
  const candidateGap = getCandidateGap(recommendation.candidates);
  const behaviorState = evaluateTrustState({
    metrics: input.behaviorMetrics,
    consecutiveRejectThreshold: sensorConfig.consecutive_reject_threshold,
    directAcceptThreshold: sensorConfig.direct_accept_threshold,
    latencyThresholdMs: sensorConfig.latency_threshold_ms,
    hysteresis: sensorConfig.hysteresis,
    previousTrustState: input.previousTrustState,
    minTruthCoverage: sensorConfig.min_truth_coverage,
    unwarrantedRejectThreshold: sensorConfig.unwarranted_reject_threshold,
    unwarrantedAcceptThreshold: sensorConfig.unwarranted_accept_threshold,
  });
  const taskRisk = evaluateSensorTaskRisk({
    confidence,
    candidateGap,
    recommendationAgeMs: ageMs,
    iffMode: input.iffMode,
    isEnemyRecommendation: recommendation.candidates
      .some(candidate => candidate.id === recommendation.targetId && candidate.target?.type === "army"),
    config: sensorConfig,
  });
  const triggers = Array.from(new Set([...taskRisk.triggers, ...behaviorState.triggers]));
  const underTrust = behaviorState.underTrust || (behaviorState.trustState === "normal" && taskRisk.explainRisk);
  const overTrust = behaviorState.overTrust;
  // 真值不足导致的暂定状态不触发强干预（复核/拦一键），只做软提示
  const allowHardControl = !behaviorState.provisional;
  const reviewNeeded = allowHardControl && overTrust && taskRisk.reviewRisk && sensorConfig.require_evidence_before_confirm;
  const reviewComplete = input.evidenceViewed || input.manualReviewDone;
  const blockedOneClick =
    reviewNeeded &&
    config.display.block_one_click_on_low_confidence &&
    !reviewComplete;

  return {
    task: "sensor",
    enabled: true,
    trustState: behaviorState.trustState === "normal" && taskRisk.explainRisk
      ? "under_trust"
      : behaviorState.trustState,
    controlLevel: reviewNeeded ? "review" : (underTrust || overTrust) ? "explain" : "none",
    triggers,
    evidenceViewed: input.evidenceViewed,
    manualReviewRequested: Boolean(input.manualReviewRequested),
    manualReviewDone: input.manualReviewDone,
    blockedOneClick,
    primaryMessage: reviewNeeded
      ? reviewComplete
        ? "复核已完成，可继续确认"
        : "近期多次无证据接受了实际错误的推荐，需要人工复核"
      : overTrust
        ? "近期存在对错误推荐的过度接受倾向，请查看依据再确认"
        : underTrust
          ? behaviorState.triggers.includes("unwarranted_reject")
            ? "近期多次拒绝了实际正确的推荐，建议展开依据再判断"
            : "AI建议依据已展开"
          : taskRisk.reviewRisk
            ? "当前建议存在任务风险，请查看候选依据"
          : "",
    aiTargetId: recommendation.targetId,
    confidence,
    candidateGap,
    recommendationAgeMs: ageMs,
    iffPending: !input.iffMode,
    candidates: recommendation.candidates,
    configSnapshot: buildTrustConfigSnapshot(config),
  };
}

export function evaluateThreatTrustDecision(input: {
  config: TrustCalibrationConfig;
  candidates: ThreatCandidateEvidence[];
  generationTimestamp?: number | null;
  previousTopThreatId?: string | null;
  previousTopThreatRank?: number;
  behaviorMetrics: TrustBehaviorMetrics;
  evidenceViewed: boolean;
  manualReviewRequested?: boolean;
  manualReviewDone: boolean;
  previousTrustState?: TrustState;
  now: number;
}): ThreatTrustDecision {
  const { config, candidates } = input;
  if (!config.enabled || candidates.length === 0) return disabledThreatDecision(config);

  const threatConfig = config.threat;
  const [top, second] = candidates;
  const scoreGap =
    top && second && typeof top.score === "number" && typeof second.score === "number"
      ? Math.abs(top.score - second.score)
      : undefined;
  const normalizedGenerationTimestamp = normalizeTimestampMs(input.generationTimestamp, input.now);
  const dataDelayMs = input.generationTimestamp
    ? Math.max(0, input.now - normalizedGenerationTimestamp)
    : undefined;
  const rankingChanged =
    !!input.previousTopThreatId &&
    !!top?.id &&
    input.previousTopThreatId !== top.id;

  const behaviorState = evaluateTrustState({
    metrics: input.behaviorMetrics,
    consecutiveRejectThreshold: threatConfig.consecutive_reject_threshold,
    directAcceptThreshold: threatConfig.direct_accept_threshold,
    latencyThresholdMs: threatConfig.latency_threshold_ms,
    hysteresis: threatConfig.hysteresis,
    previousTrustState: input.previousTrustState,
    minTruthCoverage: threatConfig.min_truth_coverage,
    unwarrantedRejectThreshold: threatConfig.unwarranted_reject_threshold,
    unwarrantedAcceptThreshold: threatConfig.unwarranted_accept_threshold,
  });
  const taskRisk = evaluateThreatTaskRisk({
    scoreGap,
    dataDelayMs,
    rankingChanged,
    config: threatConfig,
  });
  const triggers = Array.from(new Set([...taskRisk.triggers, ...behaviorState.triggers]));
  const underTrust = behaviorState.underTrust || (behaviorState.trustState === "normal" && taskRisk.explainRisk);
  const overTrust = behaviorState.overTrust;
  // 真值不足导致的暂定状态不触发强干预（复核/拦一键），只做软提示
  const allowHardControl = !behaviorState.provisional;
  const reviewNeeded = allowHardControl && overTrust && taskRisk.reviewRisk && threatConfig.require_evidence_before_submit;
  const reviewComplete = input.evidenceViewed || input.manualReviewDone;
  const blockedOneClick = reviewNeeded && !reviewComplete;

  return {
    task: "threat",
    enabled: true,
    trustState: behaviorState.trustState === "normal" && taskRisk.explainRisk
      ? "under_trust"
      : behaviorState.trustState,
    controlLevel: reviewNeeded ? "review" : (underTrust || overTrust) ? "explain" : "none",
    triggers,
    evidenceViewed: input.evidenceViewed,
    manualReviewRequested: Boolean(input.manualReviewRequested),
    manualReviewDone: input.manualReviewDone,
    blockedOneClick,
    primaryMessage: reviewNeeded
      ? reviewComplete
        ? "复核已完成，可继续查看结果"
        : "近期多次无证据接受了实际错误的排序，需要人工确认"
      : overTrust
        ? "近期存在对错误排序的过度接受倾向，请查看证据再确认"
        : underTrust
          ? behaviorState.triggers.includes("unwarranted_reject")
            ? "近期多次拒绝了实际正确的排序，建议展开依据再判断"
            : "排序变化依据已展开"
          : taskRisk.reviewRisk
            ? "当前排序存在任务风险，请查看证据"
          : "",
    topThreatId: top?.id,
    secondThreatId: second?.id,
    previousTopThreatRank: input.previousTopThreatRank,
    scoreGap,
    dataDelayMs,
    rankingUnstable: taskRisk.triggers.includes("score_gap_small"),
    rankingChanged,
    changeText: rankingChanged && top?.label
      ? input.previousTopThreatRank
        ? `${top.label} 从第${input.previousTopThreatRank}位升至第1位`
        : `${top.label} 成为当前最高威胁`
      : undefined,
    candidates,
    configSnapshot: buildTrustConfigSnapshot(config),
  };
}

export function buildTrustCalibrationLogPayload(
  decision: SensorTrustDecision | ThreatTrustDecision
): TrustCalibrationLogPayload {
  return {
    enabled: decision.enabled,
    trust_state: decision.trustState,
    control_level: decision.controlLevel,
    triggers: decision.triggers,
    confidence: decision.task === "sensor" ? decision.confidence : undefined,
    score_gap: decision.task === "threat" ? decision.scoreGap : undefined,
    data_delay_ms: decision.task === "threat" ? decision.dataDelayMs : undefined,
    evidence_viewed: decision.evidenceViewed,
    manual_review_done: decision.manualReviewDone,
    blocked_one_click: decision.blockedOneClick,
    config_snapshot: decision.configSnapshot,
  };
}

type SensorCandidateInput = NonNullable<SensorCandidateEvidence["target"]>;

export function createSensorCandidates(
  targets: SensorCandidateInput[],
  selectedTargetId: string,
  confidence: number
): SensorCandidateEvidence[] {
  const sorted = [...targets].sort((a, b) => {
    const aScore = normalizeConfidence(a.threat_score ?? (a.id === selectedTargetId ? confidence : 0.5));
    const bScore = normalizeConfidence(b.threat_score ?? (b.id === selectedTargetId ? confidence : 0.5));
    return bScore - aScore;
  });

  const selected = sorted.find(target => target.id === selectedTargetId);
  const candidates = [
    ...(selected ? [selected] : []),
    ...sorted.filter(target => target.id !== selectedTargetId),
  ].slice(0, 3);

  return candidates.map((target, index) => {
    const targetConfidence = normalizeConfidence(
      target.threat_score ?? (target.id === selectedTargetId ? confidence : confidence - (index + 1) * 0.12),
      Math.max(0.35, confidence - index * 0.12)
    );
    return {
      id: target.id,
      label: target.id,
      confidence: targetConfidence,
      reason: target.type === "army"
        ? "敌方特征 / 航向接近"
        : "相似候选 / 需IFF确认",
      target,
    };
  });
}
