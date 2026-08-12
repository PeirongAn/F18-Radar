import { describe, expect, it } from 'vitest';

import {
  clearTaskCompletionForStart,
  getTaskGroupIdFromMessage,
  isCompletionForActiveTaskGroup,
} from './taskGroupCompletion';

describe('task-group completion isolation', () => {
  it('clears the old completion marker as soon as a new task start is announced', () => {
    const previous = {
      RADAR_TARGETING: 'ALL_COMPLETED' as const,
      SA_THREAT_RESPONSE: { current: 1, total: 2 },
    };

    expect(clearTaskCompletionForStart(previous, 'RADAR_TARGETING')).toEqual({
      RADAR_TARGETING: null,
      SA_THREAT_RESPONSE: { current: 1, total: 2 },
    });
  });

  it('requires a concrete task-group id for a completion notice', () => {
    expect(isCompletionForActiveTaskGroup({ task_type: 'RADAR_TARGETING' }, '13')).toBe(false);
    expect(isCompletionForActiveTaskGroup({ task_group_id: 13 }, '13')).toBe(true);
    expect(isCompletionForActiveTaskGroup({ task_group_id: 7 }, '13')).toBe(false);
  });

  it('reads a nested repetition task-group id', () => {
    expect(getTaskGroupIdFromMessage({ repetition_info: { task_group_id: 13 } })).toBe('13');
  });
});
