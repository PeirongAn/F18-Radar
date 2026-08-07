export type RadarTargetClassification = 'army' | string;

export interface RadarIffClickInput {
  alreadyHandled: boolean;
  hasLockedTarget: boolean;
  interactionAllowed?: boolean;
  lockedTargetType?: RadarTargetClassification;
  currentIffMode: boolean;
  hasReachedTaskTotal: boolean;
}

export type RadarIffClickDecision =
  | {
      action: 'ignore_already_handled';
      showMissionConfirm: false;
      missionCanComplete: false;
      nextIffMode: false;
      missionResultMessage: '';
      notifyTaskCompleted: boolean;
    }
  | {
      action: 'ignore_ai_selection_pending';
      showMissionConfirm: false;
      missionCanComplete: false;
      nextIffMode: false;
      missionResultMessage: '';
      notifyTaskCompleted: false;
    }
  | {
      action: 'ignore_without_locked_target';
      showMissionConfirm: false;
      missionCanComplete: false;
      nextIffMode: false;
      missionResultMessage: '';
      notifyTaskCompleted: false;
    }
  | {
      action: 'show_confirmation';
      showMissionConfirm: true;
      missionCanComplete: true;
      nextIffMode: boolean;
      missionResultMessage: '结果: 正确' | '结果: 错误';
      notifyTaskCompleted: false;
    };

export const decideRadarIffClick = (input: RadarIffClickInput): RadarIffClickDecision => {
  if (input.alreadyHandled) {
    return {
      action: 'ignore_already_handled',
      showMissionConfirm: false,
      missionCanComplete: false,
      nextIffMode: false,
      missionResultMessage: '',
      notifyTaskCompleted: input.hasReachedTaskTotal,
    };
  }

  if (input.interactionAllowed === false) {
    return {
      action: 'ignore_ai_selection_pending',
      showMissionConfirm: false,
      missionCanComplete: false,
      nextIffMode: false,
      missionResultMessage: '',
      notifyTaskCompleted: false,
    };
  }

  if (!input.hasLockedTarget) {
    return {
      action: 'ignore_without_locked_target',
      showMissionConfirm: false,
      missionCanComplete: false,
      nextIffMode: false,
      missionResultMessage: '',
      notifyTaskCompleted: false,
    };
  }

  return {
    action: 'show_confirmation',
    showMissionConfirm: true,
    missionCanComplete: true,
    nextIffMode: !input.currentIffMode,
    missionResultMessage: input.lockedTargetType === 'army' ? '结果: 正确' : '结果: 错误',
    notifyTaskCompleted: false,
  };
};

export interface RadarConfirmationInput {
  missionCanComplete: boolean;
  alreadyHandled: boolean;
  hasReachedTaskTotal: boolean;
  canNavigateToSA: boolean;
}

export type RadarConfirmationAction =
  | 'dismiss_invalid'
  | 'ignore_duplicate'
  | 'complete_task_group'
  | 'navigate_to_sa'
  | 'reset_for_next_mission';

export interface RadarConfirmationDecision {
  action: RadarConfirmationAction;
  shouldSendResultConfirmed: boolean;
  shouldMarkHandled: boolean;
  notifyTaskCompleted: boolean;
}

export const decideRadarConfirmation = (input: RadarConfirmationInput): RadarConfirmationDecision => {
  if (!input.missionCanComplete) {
    return {
      action: 'dismiss_invalid',
      shouldSendResultConfirmed: false,
      shouldMarkHandled: false,
      notifyTaskCompleted: false,
    };
  }

  if (input.alreadyHandled) {
    return {
      action: 'ignore_duplicate',
      shouldSendResultConfirmed: false,
      shouldMarkHandled: false,
      notifyTaskCompleted: input.hasReachedTaskTotal,
    };
  }

  if (input.hasReachedTaskTotal) {
    return {
      action: 'complete_task_group',
      shouldSendResultConfirmed: true,
      shouldMarkHandled: true,
      notifyTaskCompleted: true,
    };
  }

  if (input.canNavigateToSA) {
    return {
      action: 'navigate_to_sa',
      shouldSendResultConfirmed: true,
      shouldMarkHandled: true,
      notifyTaskCompleted: false,
    };
  }

  return {
    action: 'reset_for_next_mission',
    shouldSendResultConfirmed: true,
    shouldMarkHandled: true,
    notifyTaskCompleted: false,
  };
};
