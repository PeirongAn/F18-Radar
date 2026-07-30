export type TrustOutcome = 'appropriate' | 'under_trust' | 'over_trust';
export type TrustUiMode = 'standard' | 'trust_support';
export type TrustTaskType = 'RADAR_TARGETING' | 'SA_THREAT_RESPONSE';

export interface TrustConditionKey {
  task_group_id: number | string | null;
  user_id: string;
  task_type: TrustTaskType | string;
  difficulty: string;
  ai_level: string;
}

export interface TrustControlState {
  enabled: boolean;
  condition_key: TrustConditionKey;
  history_count: number;
  ui_mode: TrustUiMode;
  appropriate_rate: number;
  under_trust_rate: number;
  over_trust_rate: number;
  direction_index: number;
  ai_history_accuracy: number | null;
  ai_history_correct_count: number;
  ai_history_valid_count: number;
  ai_history_accuracy_series: number[];
  ai_history_correctness_series: boolean[];
  ai_statistical_accuracy: number | null;
  ai_statistical_accuracy_series: number[];
  ai_statistical_accuracy_lower_bound: number | null;
  ai_statistical_accuracy_upper_bound: number | null;
  ai_statistical_accuracy_source: 'ai_level_probability_range' | null;
  ai_statistical_accuracy_curve_seed: number | null;
  disclose_ai_reliability: boolean;
  manual_review_button: number;
  sensor_focus_radius_px: number;
  threat_focus_radius_px: number;
  focus_dwell_ms: number;
}

export interface TrustCandidate {
  id: string;
  label: string;
  displayNumber?: number;
  type?: string;
  distance?: number;
  score?: number;
  confidence?: number;
  reason?: string;
  evidence?: string[];
  updatedAt?: number;
  azimuthDeg?: number;
  distanceNm?: number;
  speedRaw?: number;
  headingDeg?: number;
  relativeHeadingDeg?: number;
  observedAtMs?: number;
  sourceLabel?: string;
  categoryLabel?: string;
  positionX?: number;
  positionY?: number;
  isMissile?: boolean;
}

export interface ManualReviewFeedback {
  status: 'idle' | 'active' | 'completed' | 'ignored';
  message: string;
}

export interface TrustTrialSnapshot {
  taskId: string | number | null;
  taskGroupId: string | number | null;
  taskType: TrustTaskType;
  trialSequence?: number;
  control: TrustControlState | null;
  aiRecommendation: TrustCandidate | null;
  candidates: TrustCandidate[];
  focusedCandidate: TrustCandidate | null;
  humanSelection: TrustCandidate | null;
  groundTruthId: string | null;
  manualReviewCount: number;
  invalidReviewCount: number;
  manualReviewActive: boolean;
  manualReviewDurationMs: number;
  manualReviewCandidate: TrustCandidate | null;
  manualReviewFeedback: ManualReviewFeedback;
  comparisonVisible: boolean;
  glowActive: boolean;
  aiRecommendationShownAt: number | null;
}
