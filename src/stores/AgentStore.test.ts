import { beforeEach, describe, expect, it } from 'vitest';
import agentStore, { normalizeControlMode } from './AgentStore';

beforeEach(() => {
  agentStore.setControlMode('0', false);
  agentStore.setServerAIRecommendation(null);
  agentStore.resetRadarAISelection(null);
});

describe('normalizeControlMode', () => {
  it('keeps the three DefaultControlMode states distinct', () => {
    expect(normalizeControlMode('0')).toBe('0');
    expect(normalizeControlMode('1')).toBe('1');
    expect(normalizeControlMode('2')).toBe('2');
  });

  it('falls back to the legacy includeAI flag when the mode is absent', () => {
    expect(normalizeControlMode(undefined, false)).toBe('0');
    expect(normalizeControlMode(undefined, true)).toBe('1');
    expect(normalizeControlMode('', false)).toBe('0');
    expect(normalizeControlMode('   ', true)).toBe('1');
  });

  it.each([
    [false, '0'],
    ['manual', '0'],
    ['false', '0'],
    ['pure_ai', '2'],
    ['pure-ai', '2'],
    ['ai_only', '2'],
    ['ai-only', '2'],
    ['unexpected-ai-value', '1'],
  ] as const)('normalizes %s to mode %s', (input, expected) => {
    expect(normalizeControlMode(input)).toBe(expected);
  });

  it('requires a human workflow confirmation in pure AI mode', () => {
    agentStore.setControlMode('2', true);

    expect(agentStore.isManualControlDisabled).toBe(true);
    expect(agentStore.requiresHumanConfirmation).toBe(true);
    expect(agentStore.isAIActive).toBe(true);
    expect(agentStore.currentOperationOwner).toBe('AI');
  });

  it('opens pure-AI IFF only for the recorded selection of the current task', () => {
    agentStore.setControlMode('2', true);
    agentStore.resetRadarAISelection(1002);

    expect(agentStore.isRadarAISelectionReadyFor(1002)).toBe(false);
    agentStore.markRadarAISelectionRecording(1002, 'enemy-1');
    expect(agentStore.isRadarAISelectionReadyFor(1002)).toBe(false);
    agentStore.markRadarAISelectionReady(1001, 'enemy-1');
    expect(agentStore.isRadarAISelectionReadyFor(1002)).toBe(false);
    agentStore.markRadarAISelectionReady(1002, 'enemy-1');
    expect(agentStore.isRadarAISelectionReadyFor(1002)).toBe(true);
    expect(agentStore.isRadarAISelectionReadyFor(1001)).toBe(false);
  });

  it('prevents manual takeover while preserving pure AI mode', () => {
    agentStore.setControlMode('2', true);

    agentStore.toggleAIActive();
    expect(agentStore.controlMode).toBe('2');
    expect(agentStore.isAIActive).toBe(true);

    agentStore.setAIActive(false);
    expect(agentStore.controlMode).toBe('2');
    expect(agentStore.isAIActive).toBe(true);

    agentStore.setAIActive(true);
    expect(agentStore.controlMode).toBe('2');
    expect(agentStore.currentOperationOwner).toBe('AI');
  });

  it('keeps legacy AI mode available for human participation', () => {
    agentStore.setControlMode('1', true);

    expect(agentStore.isAIActive).toBe(true);
    expect(agentStore.isManualControlDisabled).toBe(false);
    expect(agentStore.requiresHumanConfirmation).toBe(false);

    agentStore.setAIActive(false);
    expect(agentStore.controlMode).toBe('0');
    expect(agentStore.currentOperationOwner).toBe('manual');
  });

  it.each([
    [{ control_mode: '2' }, '2'],
    [{ platform_task: { normalized: { control_mode: '2' } } }, '2'],
    [{ platform_task: { normalized: { default_control_mode: '2' } } }, '2'],
    [{ manual_control_disabled: true }, '2'],
  ])('initializes pure AI from server payload variant %#', (variant, expectedMode) => {
    agentStore.initializeFromServer({
      is_ai_active: false,
      ai_level: 'L1',
      ai_configs: [],
      audio_enabled: true,
      ...variant,
    });

    expect(agentStore.controlMode).toBe(expectedMode);
    expect(agentStore.isAIActive).toBe(true);
    expect(agentStore.isManualControlDisabled).toBe(true);
    expect(agentStore.currentOperationOwner).toBe('AI');
  });

  it('prefers the explicit server control mode over compatibility flags', () => {
    agentStore.initializeFromServer({
      is_ai_active: true,
      ai_level: 'L1',
      ai_configs: [],
      audio_enabled: true,
      control_mode: '0',
      manual_control_disabled: true,
    });

    expect(agentStore.controlMode).toBe('0');
    expect(agentStore.isAIActive).toBe(false);
    expect(agentStore.isManualControlDisabled).toBe(false);
    expect(agentStore.currentOperationOwner).toBe('manual');
  });
});
