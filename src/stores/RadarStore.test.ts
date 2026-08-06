import { beforeEach, describe, expect, it } from 'vitest';
import agentStore from './AgentStore';
import { RadarStore } from './RadarStore';

describe('RadarStore control mode propagation', () => {
  beforeEach(() => {
    agentStore.setControlMode('0', false);
  });

  it('starts mode 2 as AI-active with manual control disabled', () => {
    const store = new RadarStore();

    store.startSystem('pure-ai-user', true, false, 3, '2');

    expect(store.isStarted).toBe(true);
    expect(store.userId).toBe('pure-ai-user');
    expect(store.taskNumber).toBe(3);
    expect(agentStore.controlMode).toBe('2');
    expect(agentStore.isAIActive).toBe(true);
    expect(agentStore.isManualControlDisabled).toBe(true);
  });

  it.each([
    ['0', false, false],
    ['1', true, false],
    ['2', true, true],
  ] as const)(
    'keeps mode %s distinct when starting the radar workflow',
    (mode, includeAI, manualDisabled) => {
      const store = new RadarStore();

      store.startSystem('mode-user', includeAI, true, 2, mode);

      expect(agentStore.controlMode).toBe(mode);
      expect(agentStore.isAIActive).toBe(includeAI);
      expect(agentStore.isManualControlDisabled).toBe(manualDisabled);
      expect(store.isPractice).toBe(true);
    }
  );

  it('uses the legacy includeAI flag when no explicit mode is provided', () => {
    const store = new RadarStore();

    store.startSystem('legacy-user', true, false);

    expect(agentStore.controlMode).toBe('1');
    expect(agentStore.isManualControlDisabled).toBe(false);
  });
});
