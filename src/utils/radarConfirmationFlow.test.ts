import { describe, expect, it } from 'vitest';
import { decideRadarConfirmation, decideRadarIffClick } from './radarConfirmationFlow';

describe('pure AI radar IFF gate', () => {
  it('does not show a confirmation before AI has locked a target', () => {
    expect(decideRadarIffClick({
      alreadyHandled: false,
      hasLockedTarget: false,
      currentIffMode: false,
      hasReachedTaskTotal: false,
    })).toEqual({
      action: 'ignore_without_locked_target',
      showMissionConfirm: false,
      missionCanComplete: false,
      nextIffMode: false,
      missionResultMessage: '',
      notifyTaskCompleted: false,
    });
  });

  it.each([
    ['army', '结果: 正确'],
    ['civilian', '结果: 错误'],
  ])('shows the result only after IFF is clicked for a locked %s target', (targetType, expectedMessage) => {
    const decision = decideRadarIffClick({
      alreadyHandled: false,
      hasLockedTarget: true,
      lockedTargetType: targetType,
      currentIffMode: false,
      hasReachedTaskTotal: false,
    });

    expect(decision.action).toBe('show_confirmation');
    expect(decision.showMissionConfirm).toBe(true);
    expect(decision.missionCanComplete).toBe(true);
    expect(decision.nextIffMode).toBe(true);
    expect(decision.missionResultMessage).toBe(expectedMessage);
  });

  it('does not reopen confirmation for an already handled round', () => {
    const decision = decideRadarIffClick({
      alreadyHandled: true,
      hasLockedTarget: true,
      lockedTargetType: 'army',
      currentIffMode: true,
      hasReachedTaskTotal: true,
    });

    expect(decision.action).toBe('ignore_already_handled');
    expect(decision.showMissionConfirm).toBe(false);
    expect(decision.missionCanComplete).toBe(false);
    expect(decision.nextIffMode).toBe(false);
    expect(decision.notifyTaskCompleted).toBe(true);
  });
});

describe('radar confirmation advancement', () => {
  it('does not submit a result when confirmation is not eligible', () => {
    expect(decideRadarConfirmation({
      missionCanComplete: false,
      alreadyHandled: false,
      hasReachedTaskTotal: false,
      canNavigateToSA: false,
    })).toEqual({
      action: 'dismiss_invalid',
      shouldSendResultConfirmed: false,
      shouldMarkHandled: false,
      notifyTaskCompleted: false,
    });
  });

  it('submits once and resets for the next radar round', () => {
    expect(decideRadarConfirmation({
      missionCanComplete: true,
      alreadyHandled: false,
      hasReachedTaskTotal: false,
      canNavigateToSA: false,
    })).toMatchObject({
      action: 'reset_for_next_mission',
      shouldSendResultConfirmed: true,
      shouldMarkHandled: true,
      notifyTaskCompleted: false,
    });
  });

  it('submits once and navigates when a combined flow provides an SA step', () => {
    expect(decideRadarConfirmation({
      missionCanComplete: true,
      alreadyHandled: false,
      hasReachedTaskTotal: false,
      canNavigateToSA: true,
    }).action).toBe('navigate_to_sa');
  });

  it('submits the final round and reports task-group completion', () => {
    expect(decideRadarConfirmation({
      missionCanComplete: true,
      alreadyHandled: false,
      hasReachedTaskTotal: true,
      canNavigateToSA: false,
    })).toMatchObject({
      action: 'complete_task_group',
      shouldSendResultConfirmed: true,
      shouldMarkHandled: true,
      notifyTaskCompleted: true,
    });
  });

  it('suppresses duplicate confirmation messages', () => {
    expect(decideRadarConfirmation({
      missionCanComplete: true,
      alreadyHandled: true,
      hasReachedTaskTotal: false,
      canNavigateToSA: false,
    })).toMatchObject({
      action: 'ignore_duplicate',
      shouldSendResultConfirmed: false,
      shouldMarkHandled: false,
    });
  });
});
