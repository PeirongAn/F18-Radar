import { describe, it, expect } from "vitest";
import {
  DEFAULT_TRUST_CALIBRATION_CONFIG,
  buildTrustBehaviorMetricsFromEvents,
  createTrustInteractionEvent,
  evaluateTrustState,
  evaluateThreatTrustDecision,
} from "./trustCalibration";
import {
  ThreatCandidateEvidence,
  TrustInteractionEvent,
  TrustInteractionEventType,
} from "../types/trustCalibration";

const WINDOW = DEFAULT_TRUST_CALIBRATION_CONFIG.threat.window_size;

/** 构造一个人工决策事件 */
function humanDecision(
  eventType: Extract<TrustInteractionEventType, "human_accept" | "human_reject">,
  opts: {
    aiCorrect?: boolean; // AI 推荐是否与真值一致；undefined = 真值未知
    evidenceViewed?: boolean;
    recId?: string;
  } = {}
): TrustInteractionEvent {
  return createTrustInteractionEvent({
    actor: "human",
    task: "threat",
    eventType,
    recommendationId: opts.recId ?? "top",
    selectedId: eventType === "human_accept" ? "top" : "other",
    metadata: { evidenceViewed: opts.evidenceViewed ?? false },
    aiRecommendationCorrect: opts.aiCorrect,
    outcomeSource: opts.aiCorrect === undefined ? undefined : "scenario",
    source: "test",
  });
}

function evalThreat(metricsEvents: TrustInteractionEvent[], scoreGapSmall: boolean) {
  // scoreGapSmall=true 时构造接近的候选分数，触发 taskRisk.reviewRisk
  const candidates: ThreatCandidateEvidence[] = scoreGapSmall
    ? [
        { id: "a", label: "A", score: 0.8, reason: "" },
        { id: "b", label: "B", score: 0.78, reason: "" },
      ]
    : [
        { id: "a", label: "A", score: 0.9, reason: "" },
        { id: "b", label: "B", score: 0.3, reason: "" },
      ];
  return evaluateThreatTrustDecision({
    config: DEFAULT_TRUST_CALIBRATION_CONFIG,
    candidates,
    generationTimestamp: undefined,
    behaviorMetrics: buildTrustBehaviorMetricsFromEvents(metricsEvents, WINDOW),
    evidenceViewed: false,
    manualReviewDone: false,
    previousTrustState: "normal",
    now: Date.now(),
  });
}

describe("buildTrustBehaviorMetricsFromEvents — 真值计数", () => {
  it("拒绝正确推荐计入 unwarrantedReject，拒绝错误推荐计入 justifiedReject", () => {
    const events = [
      humanDecision("human_reject", { aiCorrect: true }),
      humanDecision("human_reject", { aiCorrect: false }),
    ];
    const m = buildTrustBehaviorMetricsFromEvents(events, WINDOW);
    expect(m.truthKnownCount).toBe(2);
    expect(m.unwarrantedRejectCount).toBe(1);
    expect(m.justifiedRejectCount).toBe(1);
    expect(m.truthCoverage).toBe(1);
  });

  it("无证据接受错误推荐计入 unwarrantedAccept；接受正确推荐不计入", () => {
    const events = [
      humanDecision("human_accept", { aiCorrect: false, evidenceViewed: false }),
      humanDecision("human_accept", { aiCorrect: true, evidenceViewed: false }),
    ];
    const m = buildTrustBehaviorMetricsFromEvents(events, WINDOW);
    expect(m.unwarrantedAcceptCount).toBe(1);
  });

  it("真值未知的事件不计入真值统计，拉低覆盖率", () => {
    const events = [
      humanDecision("human_reject", { aiCorrect: true }),
      humanDecision("human_reject", {}), // 未知
      humanDecision("human_reject", {}), // 未知
      humanDecision("human_reject", {}), // 未知
    ];
    const m = buildTrustBehaviorMetricsFromEvents(events, WINDOW);
    expect(m.truthKnownCount).toBe(1);
    expect(m.truthCoverage).toBeCloseTo(0.25);
  });
});

describe("evaluateTrustState — 真值优先", () => {
  it("连续拒绝实际正确的推荐 → under_trust（真值口径，非暂定）", () => {
    const events = [
      humanDecision("human_reject", { aiCorrect: true }),
      humanDecision("human_reject", { aiCorrect: true }),
    ];
    const r = evaluateTrustState({
      metrics: buildTrustBehaviorMetricsFromEvents(events, WINDOW),
      consecutiveRejectThreshold: 2,
      directAcceptThreshold: 2,
      latencyThresholdMs: 4500,
      hysteresis: 1,
      minTruthCoverage: 0.5,
      unwarrantedRejectThreshold: 2,
      unwarrantedAcceptThreshold: 1,
    });
    expect(r.trustState).toBe("under_trust");
    expect(r.provisional).toBe(false);
    expect(r.triggers).toContain("unwarranted_reject");
  });

  it("AI 连续出错、人工连续拒绝 → normal（关键回归用例）", () => {
    const events = [
      humanDecision("human_reject", { aiCorrect: false }),
      humanDecision("human_reject", { aiCorrect: false }),
      humanDecision("human_reject", { aiCorrect: false }),
    ];
    const r = evaluateTrustState({
      metrics: buildTrustBehaviorMetricsFromEvents(events, WINDOW),
      consecutiveRejectThreshold: 2,
      directAcceptThreshold: 2,
      latencyThresholdMs: 4500,
      hysteresis: 1,
      minTruthCoverage: 0.5,
      unwarrantedRejectThreshold: 2,
      unwarrantedAcceptThreshold: 1,
    });
    expect(r.trustState).toBe("normal");
    expect(r.provisional).toBe(false);
  });

  it("无证据接受实际错误的推荐 → over_trust", () => {
    const events = [humanDecision("human_accept", { aiCorrect: false, evidenceViewed: false })];
    const r = evaluateTrustState({
      metrics: buildTrustBehaviorMetricsFromEvents(events, WINDOW),
      consecutiveRejectThreshold: 2,
      directAcceptThreshold: 2,
      latencyThresholdMs: 4500,
      hysteresis: 1,
      minTruthCoverage: 0.5,
      unwarrantedRejectThreshold: 2,
      unwarrantedAcceptThreshold: 1,
    });
    expect(r.trustState).toBe("over_trust");
    expect(r.triggers).toContain("unwarranted_accept");
  });

  it("真值覆盖不足 → 退回行为启发式但标记 provisional", () => {
    const events = [
      humanDecision("human_reject", {}),
      humanDecision("human_reject", {}),
      humanDecision("human_reject", {}),
      humanDecision("human_reject", { aiCorrect: true }),
    ];
    const r = evaluateTrustState({
      metrics: buildTrustBehaviorMetricsFromEvents(events, WINDOW),
      consecutiveRejectThreshold: 2,
      directAcceptThreshold: 2,
      latencyThresholdMs: 4500,
      hysteresis: 1,
      minTruthCoverage: 0.5,
      unwarrantedRejectThreshold: 2,
      unwarrantedAcceptThreshold: 1,
    });
    expect(r.provisional).toBe(true);
    expect(r.trustState).toBe("under_trust"); // 行为口径：连续拒绝
    expect(r.triggers).toContain("low_truth_coverage");
  });
});

describe("evaluateThreatTrustDecision — 强干预闸门", () => {
  it("真值确认的过信任 + 任务风险 → review + 拦一键", () => {
    const events = [
      humanDecision("human_accept", { aiCorrect: false, evidenceViewed: false }),
      humanDecision("human_accept", { aiCorrect: false, evidenceViewed: false }),
    ];
    const d = evalThreat(events, /* scoreGapSmall */ true);
    expect(d.trustState).toBe("over_trust");
    expect(d.controlLevel).toBe("review");
    expect(d.blockedOneClick).toBe(true);
  });

  it("暂定（真值不足）的过信任 + 任务风险 → 只 explain，不拦一键", () => {
    const events = [
      humanDecision("human_accept", { evidenceViewed: false }),
      humanDecision("human_accept", { evidenceViewed: false }),
      humanDecision("human_accept", { evidenceViewed: false }),
    ];
    const d = evalThreat(events, /* scoreGapSmall */ true);
    expect(d.controlLevel).toBe("explain");
    expect(d.blockedOneClick).toBe(false);
  });
});
