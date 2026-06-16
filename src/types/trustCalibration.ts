import { UnknownTargetData } from "../components/UnknownTarget";

export type TrustState = "disabled" | "normal" | "under_trust" | "over_trust";

export type TrustControlLevel = "none" | "explain" | "review";

export type TrustEventActor = "ai" | "human";

export type TrustEventTask = "sensor" | "threat";

export type OutcomeSource = "scenario" | "iff" | "post_hoc" | "manual_label";

export type TrustInteractionEventType =
  | "ai_recommendation_shown"
  | "ai_auto_action"
  | "human_accept"
  | "human_reject"
  | "human_result_confirmed"
  | "evidence_viewed"
  | "manual_review_requested"
  | "manual_review_done";

export type TrustControlTrigger =
  | "high_confidence_unconfirmed"
  | "consecutive_reject"
  | "low_confidence"
  | "candidate_close"
  | "iff_unconfirmed"
  | "direct_accept_without_evidence"
  | "confirmation_latency"
  | "ranking_changed"
  | "score_gap_small"
  | "data_delay"
  | "manual_review_required"
  | "unwarranted_reject"
  | "unwarranted_accept"
  | "low_truth_coverage";

export interface SensorTrustCalibrationConfig {
  high_confidence: number;
  low_confidence_min: number;
  low_confidence_max: number;
  candidate_gap_threshold: number;
  unconfirmed_timeout_ms: number;
  consecutive_reject_threshold: number;
  direct_accept_threshold: number;
  window_size: number;
  hysteresis: number;
  latency_threshold_ms: number;
  require_evidence_before_confirm: boolean;
  min_truth_coverage: number;
  unwarranted_reject_threshold: number;
  unwarranted_accept_threshold: number;
}

export interface ThreatTrustCalibrationConfig {
  score_gap_threshold: number;
  data_delay_ms: number;
  unconfirmed_timeout_ms: number;
  consecutive_reject_threshold: number;
  direct_accept_threshold: number;
  window_size: number;
  hysteresis: number;
  latency_threshold_ms: number;
  require_evidence_before_submit: boolean;
  min_truth_coverage: number;
  unwarranted_reject_threshold: number;
  unwarranted_accept_threshold: number;
}

export interface TrustDisplayConfig {
  show_explanation_panel: boolean;
  show_candidate_comparison: boolean;
  show_data_quality_bar: boolean;
  show_capability_boundary: boolean;
  block_one_click_on_low_confidence: boolean;
}

export interface TrustCalibrationStateConfig {
  sensor: TrustState;
  threat: TrustState;
}

export interface TrustCalibrationConfig {
  enabled: boolean;
  state: TrustCalibrationStateConfig;
  sensor: SensorTrustCalibrationConfig;
  threat: ThreatTrustCalibrationConfig;
  display: TrustDisplayConfig;
}

export interface TrustConfigSnapshot {
  enabled: boolean;
  high_confidence?: number;
  low_confidence_max?: number;
  candidate_gap_threshold?: number;
  score_gap_threshold?: number;
  data_delay_ms?: number;
  window_size?: number;
  hysteresis?: number;
  latency_threshold_ms?: number;
  block_one_click_on_low_confidence: boolean;
}

export interface SensorCandidateEvidence {
  id: string;
  label: string;
  confidence: number;
  reason: string;
  target?: UnknownTargetData;
}

export interface SensorAIRecommendation {
  targetId: string;
  confidence: number;
  recommendedAt: number;
  candidates: SensorCandidateEvidence[];
}

export interface ThreatCandidateEvidence {
  id: string;
  label: string;
  score: number;
  reason: string;
  threat?: unknown;
}

export interface TrustBehaviorMetrics {
  sampleCount: number;
  rejectCount: number;
  consecutiveRejectCount: number;
  directAcceptCount: number;
  evidenceViewedCount: number;
  averageConfirmationLatencyMs?: number;
  /** 窗口内已知真值（AI 推荐对错已知）的人工决策数 */
  truthKnownCount: number;
  /** 已知真值范围内，AI 推荐正确 / 错误的次数 */
  aiCorrectCount: number;
  aiIncorrectCount: number;
  /** 拒绝了实际正确的推荐 = 不该拒（欠信任信号） */
  unwarrantedRejectCount: number;
  /** 拒绝了实际错误的推荐 = 应该拒（正确校准，不计欠信任） */
  justifiedRejectCount: number;
  /** 无证据接受了实际错误的推荐 = 不该接（过信任信号） */
  unwarrantedAcceptCount: number;
  /** 真值覆盖率 = truthKnownCount / sampleCount */
  truthCoverage: number;
}

export interface BaseTrustDecision {
  enabled: boolean;
  trustState: TrustState;
  controlLevel: TrustControlLevel;
  triggers: TrustControlTrigger[];
  evidenceViewed: boolean;
  manualReviewRequested: boolean;
  manualReviewDone: boolean;
  blockedOneClick: boolean;
  primaryMessage: string;
  configSnapshot: TrustConfigSnapshot;
}

export interface SensorTrustDecision extends BaseTrustDecision {
  task: "sensor";
  aiTargetId?: string;
  confidence?: number;
  candidateGap?: number;
  recommendationAgeMs: number;
  iffPending: boolean;
  candidates: SensorCandidateEvidence[];
}

export interface ThreatTrustDecision extends BaseTrustDecision {
  task: "threat";
  topThreatId?: string;
  secondThreatId?: string;
  previousTopThreatRank?: number;
  scoreGap?: number;
  dataDelayMs?: number;
  rankingUnstable: boolean;
  rankingChanged: boolean;
  changeText?: string;
  candidates: ThreatCandidateEvidence[];
}

export interface TrustCalibrationLogPayload {
  enabled: boolean;
  trust_state: TrustState;
  control_level: TrustControlLevel;
  triggers: TrustControlTrigger[];
  confidence?: number;
  score_gap?: number;
  data_delay_ms?: number;
  evidence_viewed: boolean;
  manual_review_done: boolean;
  blocked_one_click: boolean;
  config_snapshot: TrustConfigSnapshot;
}

export interface TrustInteractionEvent {
  version: 1;
  actor: TrustEventActor;
  task: TrustEventTask;
  eventType: TrustInteractionEventType;
  timestamp: number;
  recommendationId?: string;
  selectedId?: string;
  confidence?: number;
  candidateGap?: number;
  latencyMs?: number;
  riskFlags: TrustControlTrigger[];
  source: string;
  metadata?: Record<string, unknown>;
  /** 该条 AI 推荐是否与真值一致（已知时填，未知不填） */
  aiRecommendationCorrect?: boolean;
  /** 人工最终决策是否与真值一致（已知时填） */
  humanDecisionCorrect?: boolean;
  /** 真值来源 */
  outcomeSource?: OutcomeSource;
}
