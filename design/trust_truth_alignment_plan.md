# 信任校准：接入「AI 推荐正确性」改动方案

更新时间：2026-06-11

## 0. 为什么要做这个

现状的状态机是**纯行为计数**：连续拒绝 → `under_trust`，无证据直接接受 → `over_trust`（见 `evaluateTrustState`）。
问题在于：信任校准的目标是让**信任**对齐 AI 的**可信度（trustworthiness）**，而现在系统不知道每条 AI 推荐到底对不对，所以分不清：

- 人工连续拒绝，是因为 AI 真错了（**正确校准**），还是 AI 对了人却不信（**真正的欠信任**）。
- 无证据接受，是因为 AI 一直很准（**合理依赖**），还是 AI 会错人却闭眼点（**真正的过信任**）。

核心改动：给每条决策补一个真值维度，把 `under_trust / over_trust` 重新定义为**与真值不一致的偏差**，而不是单纯的行为频次。

---

## 1. 真值（ground truth）从哪来

按可信度排优先级，三个来源：

1. **场景脚本真值（首选，权威）**——这是仿真试验平台，每个任务场景在编排时就知道正确答案（哪个目标真为敌、哪个威胁真为最高优先级）。从任务配置直接给出 `groundTruthId`。
2. **IFF / 延迟揭示**——传感器任务里 IFF 确认会揭示真实身份；可在 IFF 结果回来时补一个结果事件。
3. **事后人工标注**——研究员在回放/导出阶段补标（接 Phase 8 报告）。

设计成「真值可延迟到达、可追溯回填到窗口内的历史事件」，因为做决策的当下往往还不知道对错。

---

## 2. 类型层改动 `src/types/trustCalibration.ts`

### 2.1 新增结果枚举与事件类型

```ts
export type RecommendationOutcome = "correct" | "incorrect" | "unknown";

export type OutcomeSource = "scenario" | "iff" | "post_hoc" | "manual_label";

export type TrustInteractionEventType =
  | "ai_recommendation_shown"
  | "ai_auto_action"
  | "human_accept"
  | "human_reject"
  | "human_result_confirmed"
  | "evidence_viewed"
  | "manual_review_requested"
  | "manual_review_done"
  | "recommendation_outcome_revealed"; // 新增：真值到达
```

### 2.2 给 `TrustInteractionEvent` 加真值字段（全部可选，向后兼容）

```ts
export interface TrustInteractionEvent {
  // ...existing...
  /** 该条 AI 推荐是否与真值一致（已知时填，未知不填） */
  aiRecommendationCorrect?: boolean;
  /** 人工最终决策是否与真值一致（已知时填） */
  humanDecisionCorrect?: boolean;
  /** 真值来源，便于分析与加权 */
  outcomeSource?: OutcomeSource;
  /** 真值揭示时所指向的 recommendationId（结果事件用） */
  resolvesRecommendationId?: string;
}
```

> 不在事件里存「正确目标 id」本身，只存「这条决策对不对」的布尔判定，避免把场景答案散落到日志里、也简化下游聚合。正确 id 的比对在生成事件的那一刻完成。

### 2.3 扩展 `TrustBehaviorMetrics`

```ts
export interface TrustBehaviorMetrics {
  sampleCount: number;
  rejectCount: number;
  directAcceptCount: number;
  evidenceViewedCount: number;
  averageConfirmationLatencyMs?: number;

  // —— 真值相关（新增）——
  /** 窗口内已知真值的决策数 */
  truthKnownCount: number;
  /** AI 推荐正确数 / 错误数（已知真值范围内） */
  aiCorrectCount: number;
  aiIncorrectCount: number;
  /** 拒绝了「其实正确」的推荐 = 不该拒（欠信任信号） */
  unwarrantedRejectCount: number;
  /** 拒绝了「确实错误」的推荐 = 应该拒（正确校准，不计欠信任） */
  justifiedRejectCount: number;
  /** 无证据接受了「确实错误」的推荐 = 不该接（过信任信号） */
  unwarrantedAcceptCount: number;
  /** 真值覆盖率 = truthKnownCount / sampleCount */
  truthCoverage: number;
}
```

新增 trigger，便于 Phase 7 解释展示：

```ts
export type TrustControlTrigger =
  | // ...existing...
  | "unwarranted_reject"        // 拒了对的
  | "unwarranted_accept"        // 接了错的
  | "low_truth_coverage";       // 真值不足，状态为暂定
```

---

## 3. 指标层改动 `src/utils/trustCalibration.ts`

### 3.1 真值映射 + 改写 `buildTrustBehaviorMetricsFromEvents`

先用全量事件建一张 `recommendationId → correct?` 的表（来自内联字段或 `recommendation_outcome_revealed` 事件），再回填到窗口内的人工决策。

```ts
function buildOutcomeMap(events: TrustInteractionEvent[]): Map<string, boolean> {
  const map = new Map<string, boolean>();
  for (const e of events) {
    // 1) 显式结果事件优先
    if (e.eventType === "recommendation_outcome_revealed"
        && e.resolvesRecommendationId
        && typeof e.aiRecommendationCorrect === "boolean") {
      map.set(e.resolvesRecommendationId, e.aiRecommendationCorrect);
    }
    // 2) 决策事件上的内联真值兜底
    if (e.recommendationId && typeof e.aiRecommendationCorrect === "boolean"
        && !map.has(e.recommendationId)) {
      map.set(e.recommendationId, e.aiRecommendationCorrect);
    }
  }
  return map;
}
```

在 `buildTrustBehaviorMetricsFromEvents` 里，对窗口内每个 `human_accept / human_reject` 决策查表：

```ts
const outcomeMap = buildOutcomeMap(events);

let truthKnownCount = 0, aiCorrectCount = 0, aiIncorrectCount = 0;
let unwarrantedReject = 0, justifiedReject = 0, unwarrantedAccept = 0;

for (const ev of decisionEvents) {
  const aiCorrect = ev.recommendationId ? outcomeMap.get(ev.recommendationId) : undefined;
  if (aiCorrect === undefined) continue;          // 真值未知，跳过真值统计
  truthKnownCount++;
  aiCorrect ? aiCorrectCount++ : aiIncorrectCount++;

  if (ev.eventType === "human_reject") {
    aiCorrect ? unwarrantedReject++ : justifiedReject++;
  } else { // human_accept
    const direct = !hasEvidenceViewedBeforeDecision(ev, events);
    if (!aiCorrect && direct) unwarrantedAccept++;
  }
}

return {
  ...existingFields,
  truthKnownCount,
  aiCorrectCount,
  aiIncorrectCount,
  unwarrantedRejectCount: unwarrantedReject,
  justifiedRejectCount: justifiedReject,
  unwarrantedAcceptCount: unwarrantedAccept,
  truthCoverage: decisionEvents.length ? truthKnownCount / decisionEvents.length : 0,
};
```

### 3.2 改写 `evaluateTrustState` —— 真值优先，行为兜底

核心思路：真值覆盖够时用真值口径；覆盖不足时退回旧的行为启发式，但把状态标成**暂定**（只 `explain`，不 `review`，并打 `low_truth_coverage`）。

```ts
export function evaluateTrustState(input: {
  metrics: TrustBehaviorMetrics;
  consecutiveRejectThreshold: number;
  directAcceptThreshold: number;
  latencyThresholdMs: number;
  hysteresis: number;
  // 新增配置
  minTruthCoverage: number;          // 例：0.5
  unwarrantedRejectThreshold: number; // 例：2
  unwarrantedAcceptThreshold: number; // 例：1（接了错的更危险，阈值更低）
  previousTrustState?: TrustState;
}): TrustStateEvaluation {
  const { metrics } = input;
  const truthReliable = metrics.truthCoverage >= input.minTruthCoverage
                        && metrics.truthKnownCount > 0;

  if (truthReliable) {
    // —— 真值口径：偏差 = 与真值不一致 ——
    const underTrust = metrics.unwarrantedRejectCount >= input.unwarrantedRejectThreshold;
    const overTrust  = metrics.unwarrantedAcceptCount >= input.unwarrantedAcceptThreshold;

    const triggers: TrustControlTrigger[] = [];
    if (underTrust) triggers.push("unwarranted_reject");
    if (overTrust)  triggers.push("unwarranted_accept");

    return {
      trustState: overTrust ? "over_trust" : underTrust ? "under_trust" : "normal",
      underTrust, overTrust, triggers,
      provisional: false,            // TrustStateEvaluation 加这个字段
    };
  }

  // —— 行为兜底口径：沿用现有计数逻辑，但状态为暂定 ——
  const behavioral = evaluateTrustStateBehavioral(input); // 把现有实现抽成这个函数
  return {
    ...behavioral,
    triggers: [...behavioral.triggers, "low_truth_coverage"],
    provisional: true,
  };
}
```

下游消费（`evaluateSensorTrustDecision` / `evaluateThreatTrustDecision`）做一处保护：**当 `provisional === true` 时，不升级到 `review` / 不 `blockOneClick`**，最多 `explain`。理由：在还不知道 AI 对错时，不应该用强干预（拦一键、强制复核）去打断被试——这既影响体验也污染实验数据。

```ts
const allowHardControl = !behaviorState.provisional;
const reviewNeeded = allowHardControl && overTrust && taskRisk.reviewRisk
                     && sensorConfig.require_evidence_before_confirm;
```

---

## 4. 事件生成层改动（hooks）

### 4.1 把真值传进来

给两个 hook 各加一个可选入参，用于「在记录人工决策的当下」就知道 AI 推荐对不对（场景脚本来源）：

```ts
// useSensorTrustCalibration / useThreatTrustCalibration
groundTruth?: {
  /** 该任务的正确目标/最高威胁 id；未知则不传 */
  correctId?: string | null;
};
```

`useSensorTrustCalibration` 的 `recordManualSelection` / `recordRecommendationAcceptance` 里补两个字段：

```ts
const aiCorrect = groundTruth?.correctId != null
  ? recommendation.targetId === groundTruth.correctId
  : undefined;
const humanCorrect = groundTruth?.correctId != null
  ? targetId === groundTruth.correctId
  : undefined;

createTrustInteractionEvent({
  // ...existing...
  aiRecommendationCorrect: aiCorrect,
  humanDecisionCorrect: humanCorrect,
  outcomeSource: aiCorrect !== undefined ? "scenario" : undefined,
});
```

`useThreatTrustCalibration` 的 `recordThreatSelection` 同理（`candidates[0].id` 对比 `correctId`）。

### 4.2 延迟真值（IFF / 事后）

新增一个回调，在 IFF 结果或回放标注到达时补结果事件，回填窗口：

```ts
const resolveRecommendationOutcome = useCallback(
  (recommendationId: string, correct: boolean, source: OutcomeSource = "iff") => {
    rememberTrustEvents(createTrustInteractionEvent({
      actor: "ai",
      task: "sensor",
      eventType: "recommendation_outcome_revealed",
      recommendationId,
      resolvesRecommendationId: recommendationId,
      aiRecommendationCorrect: correct,
      outcomeSource: source,
      riskFlags: [],
      source: "sensor.resolveOutcome",
    }));
  }, [rememberTrustEvents]);
```

因为 `buildOutcomeMap` 会回填窗口内同 `recommendationId` 的历史决策，所以延迟到达的真值会**追溯**修正先前决策的对错判定，无需重算事件本身。

---

## 5. 配置项改动

`SensorTrustCalibrationConfig` / `ThreatTrustCalibrationConfig` 各加：

```ts
min_truth_coverage: number;          // 默认 0.5
unwarranted_reject_threshold: number; // 默认 2
unwarranted_accept_threshold: number; // 默认 1
```

`DEFAULT_TRUST_CALIBRATION_CONFIG` 补默认值；`mergeTrustCalibrationConfig` 自动覆盖到位（已是浅合并，无需改结构）。`agent_level.json` 与「信任设置」UI（`TrustCalibrationSettings.tsx`）同步加这三个可调项。

---

## 6. 连带改动

- **`/api/trust-history`（`database_manager.py` / `http_server.py`）**：聚合时输出真值口径指标——AI 准确率、不该拒次数、不该接次数、真值覆盖率。当前「人工接受/拒绝」面板旁加一栏「其中不该拒 / 不该接」。
- **Phase 6 校准建议**：现在是用纯行为数据建议阈值，存在自我循环。改为**真值覆盖率达标时**才给建议，并把 `unwarranted_*_threshold` 也纳入建议；覆盖不足时明确提示「真值样本不足，暂不校准」。
- **Phase 7 解释文案**：可区分两类——
  - `unwarranted_reject`：「近期多次拒绝了事后证实正确的 AI 推荐，建议展开依据再判断。」
  - `unwarranted_accept`：「近期无证据接受了事后证实错误的推荐，已进入复核。」
  - `low_truth_coverage`：「真值尚未揭示，当前为暂定状态，不强制复核。」

---

## 7. 兼容性与迁移

- 所有新字段可选，旧事件 `aiRecommendationCorrect === undefined` → 计入「真值未知」，自动走行为兜底口径，旧行为不破。
- `TrustStateEvaluation` 新增 `provisional` 字段，消费端按上文做一处判空即可。
- 历史库里的旧 `trust_events` 没有真值字段 → 聚合时 `truthCoverage` 偏低、走暂定，不会误报。

---

## 8. 验证用例（接 Phase 8 脚本）

| 场景构造 | 期望状态 | 说明 |
|---|---|---|
| AI 全对，人工连续拒绝（已知真值） | `under_trust` + `unwarranted_reject` | 真正的欠信任 |
| AI 连续出错，人工连续拒绝（已知真值） | `normal` | 正确校准，不应报欠信任（**这是旧逻辑会误报的关键用例**）|
| AI 出错，人工无证据接受 | `over_trust` + `unwarranted_accept` | 真正的过信任 |
| AI 全对，人工无证据接受 | `normal` | 合理依赖，不应报过信任 |
| 真值覆盖率 < `min_truth_coverage` | 暂定状态，仅 `explain`，带 `low_truth_coverage`，不 `blockOneClick` | 不在未知时强干预 |
| 延迟揭示真值后 | 窗口内历史决策对错被回填，状态重算 | 验证 `buildOutcomeMap` 回溯 |

---

## 9. 落地顺序建议

1. **类型 + 指标**（§2、§3）：纯函数层，可先写单测，零 UI 风险。
2. **hooks 接真值**（§4）：先接场景脚本来源（最权威），IFF/事后延迟揭示作为第二步。
3. **配置 + UI**（§5）：暴露三个新阈值。
4. **历史聚合 + Phase 6**（§6）：让校准建议改用真值口径。
5. **Phase 7 文案**：区分三类解释。

第 1 步本身就能消除「AI 错、人对却被判欠信任」这个最关键的误报，建议优先合入。
