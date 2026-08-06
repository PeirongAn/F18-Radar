export type SAResultReviewActor = 'AI' | 'manual';

/**
 * Pure AI blocks task operations, but result review is still a human
 * confirmation action and must remain available from the UI or joystick.
 */
export const canUseSAControl = (input: {
  manualControlDisabled: boolean;
  label: string;
  eventOwner: SAResultReviewActor;
}): boolean => (
  !input.manualControlDisabled
  || input.eventOwner === 'AI'
  || input.label === '查看结果'
);

export type SAButton2Action = 'none' | 'view_result' | 'confirm_result';

export const decideSAButton2Action = (input: {
  button2: boolean;
  previousButton2: boolean;
  joystickEnabled: boolean;
  showTaskComplete: boolean;
}): SAButton2Action => {
  const isRisingEdge = input.button2 && !input.previousButton2;
  if (!isRisingEdge || !input.joystickEnabled) {
    return 'none';
  }

  return input.showTaskComplete ? 'confirm_result' : 'view_result';
};
