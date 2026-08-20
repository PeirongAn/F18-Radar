import { describe, expect, it } from 'vitest';
import {
  canSelectSAThreat,
  canUseSAControl,
  canViewSAResult,
  decideSAButton2Action,
  hasSAAISelectionForTask,
  hasSAEmergencyOccurredForTask,
  shouldOpenSAResultAfterAISelection,
} from './saResultReviewPolicy';

describe('SA emergency task gate', () => {
  it('unlocks only the task that received the emergency event', () => {
    expect(hasSAEmergencyOccurredForTask({
      currentTaskKey: 'task-1',
      emergencyTaskKey: 'task-1',
    })).toBe(true);
    expect(hasSAEmergencyOccurredForTask({
      currentTaskKey: 'task-2',
      emergencyTaskKey: 'task-1',
    })).toBe(false);
  });

  it('locks the task when the emergency state is reset', () => {
    expect(hasSAEmergencyOccurredForTask({
      currentTaskKey: 'task-1',
      emergencyTaskKey: null,
    })).toBe(false);
  });
});

describe('SA AI selection gate', () => {
  it('unlocks the result only for the task where AI completed its selection', () => {
    expect(hasSAAISelectionForTask({
      currentTaskKey: 'task-1',
      aiSelectionTaskKey: 'task-1',
    })).toBe(true);
    expect(hasSAAISelectionForTask({
      currentTaskKey: 'task-2',
      aiSelectionTaskKey: 'task-1',
    })).toBe(false);
  });

  it('blocks a fast human result request while participating AI is pending', () => {
    expect(canViewSAResult({
      aiActive: true,
      aiSelectionCompleted: false,
      eventOwner: 'manual',
    })).toBe(false);
  });

  it('allows result review after AI selection or when AI is not participating', () => {
    expect(canViewSAResult({
      aiActive: true,
      aiSelectionCompleted: true,
      eventOwner: 'manual',
    })).toBe(true);
    expect(canViewSAResult({
      aiActive: false,
      aiSelectionCompleted: false,
      eventOwner: 'manual',
    })).toBe(true);
  });

  it('allows the AI completion flow to open the result dialog', () => {
    expect(canViewSAResult({
      aiActive: true,
      aiSelectionCompleted: false,
      eventOwner: 'AI',
    })).toBe(true);
  });

  it('does not auto-open results for a fast human selection before AI finishes', () => {
    expect(shouldOpenSAResultAfterAISelection({
      requiresHumanConfirmation: true,
      hasSelection: true,
      aiSelectionCompleted: false,
    })).toBe(false);
    expect(shouldOpenSAResultAfterAISelection({
      requiresHumanConfirmation: true,
      hasSelection: true,
      aiSelectionCompleted: true,
    })).toBe(true);
  });
});

describe('SA result review policy', () => {
  it('keeps result review available to a human in pure AI mode', () => {
    expect(canUseSAControl({
      manualControlDisabled: true,
      emergencyOccurred: true,
      label: '查看结果',
      eventOwner: 'manual',
    })).toBe(true);
  });

  it('continues to block other human task operations in pure AI mode', () => {
    expect(canUseSAControl({
      manualControlDisabled: true,
      emergencyOccurred: true,
      label: 'T1',
      eventOwner: 'manual',
    })).toBe(false);
  });

  it('allows AI operations and all controls outside pure AI mode', () => {
    expect(canUseSAControl({
      manualControlDisabled: true,
      emergencyOccurred: true,
      label: 'T1',
      eventOwner: 'AI',
    })).toBe(true);
    expect(canUseSAControl({
      manualControlDisabled: false,
      emergencyOccurred: true,
      label: 'T1',
      eventOwner: 'manual',
    })).toBe(true);
  });

  it('blocks human controls until the emergency event occurs', () => {
    expect(canUseSAControl({
      manualControlDisabled: false,
      emergencyOccurred: false,
      label: '查看结果',
      eventOwner: 'manual',
    })).toBe(false);
  });
});

describe('SA threat selection policy', () => {
  it('blocks mouse and joystick selection before the emergency event', () => {
    expect(canSelectSAThreat({
      manualControlDisabled: false,
      emergencyOccurred: false,
      eventOwner: 'manual',
    })).toBe(false);
  });

  it('allows human selection after the emergency event', () => {
    expect(canSelectSAThreat({
      manualControlDisabled: false,
      emergencyOccurred: true,
      eventOwner: 'manual',
    })).toBe(true);
  });

  it('keeps AI selection independent from the human interaction gate', () => {
    expect(canSelectSAThreat({
      manualControlDisabled: true,
      emergencyOccurred: false,
      eventOwner: 'AI',
    })).toBe(true);
  });
});

describe('SA joystick Button2 action', () => {
  const base = {
    button2: true,
    previousButton2: false,
    joystickEnabled: true,
    showTaskComplete: false,
  };

  it('opens result review on the first press', () => {
    expect(decideSAButton2Action(base)).toBe('view_result');
  });

  it('confirms the result while the result dialog is open', () => {
    expect(decideSAButton2Action({
      ...base,
      showTaskComplete: true,
    })).toBe('confirm_result');
  });

  it.each([
    { button2: false },
    { previousButton2: true },
    { joystickEnabled: false },
  ])('ignores non-actionable input %#', override => {
    expect(decideSAButton2Action({ ...base, ...override })).toBe('none');
  });
});
