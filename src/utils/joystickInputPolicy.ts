export interface RawJoystickInput {
  main_x?: number;
  main_y?: number;
  sub_y?: number;
  buttons?: {
    button0?: boolean;
    button1?: boolean;
    button7?: boolean;
  };
}

export interface ProjectedJoystickInput {
  mainPos: { x: number; y: number } | null;
  subY: number | null;
  button1: boolean;
  button2: boolean;
  button7: boolean;
}

/**
 * Pure AI keeps the joystick connected only as a confirmation device.
 * Button2 represents IFF/confirm; axes and task-operation buttons remain blocked.
 */
export const projectJoystickInput = (
  data: RawJoystickInput,
  manualControlDisabled: boolean,
): ProjectedJoystickInput => {
  const buttons = data.buttons ?? {};

  return {
    mainPos: manualControlDisabled
      ? null
      : { x: data.main_x || 0, y: data.main_y || 0 },
    subY: manualControlDisabled ? null : (data.sub_y || 0),
    button1: manualControlDisabled ? false : !!buttons.button0,
    button2: !!buttons.button1,
    button7: manualControlDisabled ? false : !!buttons.button7,
  };
};

export type JoystickButton2Action = 'none' | 'open_iff' | 'confirm_result';

export const decideJoystickButton2Action = (input: {
  button2: boolean;
  previousButton2: boolean;
  joystickEnabled: boolean;
  suppressJoystickActions: boolean;
  showMissionConfirm: boolean;
}): JoystickButton2Action => {
  const isRisingEdge = input.button2 && !input.previousButton2;
  if (!isRisingEdge || !input.joystickEnabled || input.suppressJoystickActions) {
    return 'none';
  }
  return input.showMissionConfirm ? 'confirm_result' : 'open_iff';
};
