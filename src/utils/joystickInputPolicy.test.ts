import { describe, expect, it } from 'vitest';
import { decideJoystickButton2Action, projectJoystickInput } from './joystickInputPolicy';

describe('joystick input policy', () => {
  const fullInput = {
    main_x: 0.4,
    main_y: -0.3,
    sub_y: 0.7,
    buttons: {
      button0: true,
      button1: true,
      button7: true,
    },
  };

  it('keeps all joystick controls in manual and collaborative modes', () => {
    expect(projectJoystickInput(fullInput, false)).toEqual({
      mainPos: { x: 0.4, y: -0.3 },
      subY: 0.7,
      button1: true,
      button2: true,
      button7: true,
    });
  });

  it('keeps only Button2 available in pure AI mode', () => {
    expect(projectJoystickInput(fullInput, true)).toEqual({
      mainPos: null,
      subY: null,
      button1: false,
      button2: true,
      button7: false,
    });
  });

  it('propagates the Button2 release so the next press has a new rising edge', () => {
    expect(projectJoystickInput({ buttons: { button1: false } }, true).button2).toBe(false);
  });

  it('uses safe defaults for a partial joystick payload', () => {
    expect(projectJoystickInput({}, false)).toEqual({
      mainPos: { x: 0, y: 0 },
      subY: 0,
      button1: false,
      button2: false,
      button7: false,
    });
  });
});

describe('joystick Button2 action', () => {
  const base = {
    button2: true,
    previousButton2: false,
    joystickEnabled: true,
    suppressJoystickActions: false,
    showMissionConfirm: false,
  };

  it('maps the first press to IFF', () => {
    expect(decideJoystickButton2Action(base)).toBe('open_iff');
  });

  it('maps a press to result confirmation while the IFF modal is open', () => {
    expect(decideJoystickButton2Action({
      ...base,
      showMissionConfirm: true,
    })).toBe('confirm_result');
  });

  it.each([
    { button2: false },
    { previousButton2: true },
    { joystickEnabled: false },
    { suppressJoystickActions: true },
  ])('ignores non-actionable input %#', override => {
    expect(decideJoystickButton2Action({ ...base, ...override })).toBe('none');
  });
});
