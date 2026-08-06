import { describe, expect, it } from 'vitest';
import agentStore, { normalizeControlMode } from './AgentStore';

describe('normalizeControlMode', () => {
  it('keeps the three DefaultControlMode states distinct', () => {
    expect(normalizeControlMode('0')).toBe('0');
    expect(normalizeControlMode('1')).toBe('1');
    expect(normalizeControlMode('2')).toBe('2');
  });

  it('falls back to the legacy includeAI flag when the mode is absent', () => {
    expect(normalizeControlMode(undefined, false)).toBe('0');
    expect(normalizeControlMode(undefined, true)).toBe('1');
  });

  it('requires a human workflow confirmation in pure AI mode', () => {
    agentStore.setControlMode('2', true);

    expect(agentStore.isManualControlDisabled).toBe(true);
    expect(agentStore.requiresHumanConfirmation).toBe(true);
  });
});
