export interface SaThreatLabelCandidate {
  id: string;
  label?: string | null;
  type?: string | null;
}

export interface SaThreatLabelOrderState {
  nextOrder: number;
  firstSeenOrder: Map<string, number>;
}

export const createSaThreatLabelOrderState = (): SaThreatLabelOrderState => ({
  nextOrder: 0,
  firstSeenOrder: new Map(),
});

export const getSaThreatBaseLabel = (threat: SaThreatLabelCandidate): string => {
  if (threat.type === 'MissileUp') return '上升导弹';
  if (threat.type === 'MissileDown') return '下降导弹';
  return threat.label?.trim() || '未知威胁';
};

/**
 * Build labels used by the SA radar and its two lists.
 *
 * The suffix is only a same-name discriminator. Its order follows the first
 * appearance of each target in the current task, so selection-driven array
 * reordering cannot swap labels such as `F-16 [1]` and `F-16 [2]`.
 */
export const buildSaThreatDisplayLabels = (
  candidates: SaThreatLabelCandidate[],
  orderState: SaThreatLabelOrderState,
): Map<string, string> => {
  const uniqueCandidates = new Map<string, SaThreatLabelCandidate>();

  candidates.forEach(candidate => {
    const id = String(candidate.id);
    if (!uniqueCandidates.has(id)) {
      uniqueCandidates.set(id, { ...candidate, id });
    }
    if (!orderState.firstSeenOrder.has(id)) {
      orderState.firstSeenOrder.set(id, orderState.nextOrder);
      orderState.nextOrder += 1;
    }
  });

  const groups = new Map<string, SaThreatLabelCandidate[]>();
  uniqueCandidates.forEach(candidate => {
    const baseLabel = getSaThreatBaseLabel(candidate);
    const group = groups.get(baseLabel) ?? [];
    group.push(candidate);
    groups.set(baseLabel, group);
  });

  const displayLabels = new Map<string, string>();
  groups.forEach((group, baseLabel) => {
    const orderedGroup = [...group].sort((a, b) => (
      (orderState.firstSeenOrder.get(a.id) ?? Number.MAX_SAFE_INTEGER)
      - (orderState.firstSeenOrder.get(b.id) ?? Number.MAX_SAFE_INTEGER)
    ));

    orderedGroup.forEach((candidate, index) => {
      displayLabels.set(
        candidate.id,
        orderedGroup.length > 1 ? `${baseLabel} [${index + 1}]` : baseLabel,
      );
    });
  });

  return displayLabels;
};
