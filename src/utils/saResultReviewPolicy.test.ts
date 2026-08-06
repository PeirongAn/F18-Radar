import { describe, expect, it } from 'vitest';
import { canUseSAControl, decideSAButton2Action } from './saResultReviewPolicy';

describe('SA result review policy', () => {
  it('keeps result review available to a human in pure AI mode', () => {
    expect(canUseSAControl({
      manualControlDisabled: true,
      label: '查看结果',
      eventOwner: 'manual',
    })).toBe(true);
  });

  it('continues to block other human task operations in pure AI mode', () => {
    expect(canUseSAControl({
      manualControlDisabled: true,
      label: 'T1',
      eventOwner: 'manual',
    })).toBe(false);
  });

  it('allows AI operations and all controls outside pure AI mode', () => {
    expect(canUseSAControl({
      manualControlDisabled: true,
      label: 'T1',
      eventOwner: 'AI',
    })).toBe(true);
    expect(canUseSAControl({
      manualControlDisabled: false,
      label: 'T1',
      eventOwner: 'manual',
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
