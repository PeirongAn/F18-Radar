export type SAResultReviewActor = 'AI' | 'manual';

export const hasSAEmergencyOccurredForTask = (input: {
  currentTaskKey: string;
  emergencyTaskKey: string | null;
}): boolean => (
  input.emergencyTaskKey !== null
  && input.emergencyTaskKey === input.currentTaskKey
);

export const hasSAAISelectionForTask = (input: {
  currentTaskKey: string;
  aiSelectionTaskKey: string | null;
}): boolean => (
  input.aiSelectionTaskKey !== null
  && input.aiSelectionTaskKey === input.currentTaskKey
);

export const canViewSAResult = (input: {
  aiActive: boolean;
  aiSelectionCompleted: boolean;
  eventOwner: SAResultReviewActor;
}): boolean => (
  input.eventOwner === 'AI'
  || !input.aiActive
  || input.aiSelectionCompleted
);

export const shouldOpenSAResultAfterAISelection = (input: {
  requiresHumanConfirmation: boolean;
  hasSelection: boolean;
  aiSelectionCompleted: boolean;
}): boolean => (
  input.requiresHumanConfirmation
  && input.hasSelection
  && input.aiSelectionCompleted
);

/**
 * Human task controls remain locked until the emergency event. Pure AI blocks
 * task operations after that point too, while result review stays available as
 * a human confirmation action from the UI or joystick.
 */
export const canUseSAControl = (input: {
  manualControlDisabled: boolean;
  emergencyOccurred: boolean;
  label: string;
  eventOwner: SAResultReviewActor;
}): boolean => (
  input.eventOwner === 'AI'
  || (
    input.emergencyOccurred
    && (
      !input.manualControlDisabled
      || input.label === '查看结果'
    )
  )
);

export const canSelectSAThreat = (input: {
  manualControlDisabled: boolean;
  emergencyOccurred: boolean;
  eventOwner: SAResultReviewActor;
}): boolean => (
  input.eventOwner === 'AI'
  || (input.emergencyOccurred && !input.manualControlDisabled)
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
