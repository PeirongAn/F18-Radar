import type { AIDecisionContext } from '../stores/AgentStore';

export interface AISelectionOutcome<T> {
  selected: T | undefined;
  selectedPool: string[];
  fallbackReason: string | null;
  selectionProtocol: string;
  expectedTargetId: string | null;
}

const selectServerTarget = <T extends { id: string }>(
  items: T[],
  decision: AIDecisionContext,
): AISelectionOutcome<T> => {
  const expectedTargetId = decision.expected_target_id ?? null;
  const selectedPool = Array.isArray(decision.selected_pool)
    ? decision.selected_pool.map(String)
    : [];
  const expectedIsAuthorized = !!expectedTargetId && selectedPool.includes(expectedTargetId);
  return {
    selected: expectedIsAuthorized
      ? items.find(item => String(item.id) === expectedTargetId)
      : undefined,
    selectedPool,
    fallbackReason: decision.fallback_reason ?? null,
    selectionProtocol: decision.selection_protocol,
    expectedTargetId,
  };
};

export const selectRadarTarget = <T extends { id: string }>(
  targets: T[],
  decision: AIDecisionContext,
): AISelectionOutcome<T> => selectServerTarget(targets, decision);

export const selectSAThreat = <T extends { id: string }>(
  threatsInPriorityOrder: T[],
  decision: AIDecisionContext,
): AISelectionOutcome<T> => selectServerTarget(threatsInPriorityOrder, decision);
