import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  AIAgentScheduler,
  AI_THREAT_MAX_ATTEMPTS,
  AI_THREAT_RETRY_DELAY_MS,
} from './aiAgentScheduler';

describe('AIAgentScheduler', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('keeps a scheduled emergency alive until its delay expires', () => {
    const threat = { id: 'threat-1' };
    const onHandleEmergency = vi.fn();
    const scheduler = new AIAgentScheduler({
      getDelayMs: () => 1000,
      getBestThreat: () => threat,
      onHandleEmergency,
    });

    scheduler.setActive(true);
    expect(scheduler.scheduleEmergency('event-1')).toBe(true);

    // A transient emergency prop disappearing causes no scheduler action.
    vi.advanceTimersByTime(999);
    expect(onHandleEmergency).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onHandleEmergency).toHaveBeenCalledOnce();
    expect(onHandleEmergency).toHaveBeenCalledWith(threat);
  });

  it('uses the latest callbacks without restarting the pending timer', () => {
    const firstHandler = vi.fn();
    const latestHandler = vi.fn();
    const latestThreat = { id: 'latest-threat' };
    const scheduler = new AIAgentScheduler({
      getDelayMs: () => 500,
      getBestThreat: () => ({ id: 'stale-threat' }),
      onHandleEmergency: firstHandler,
    });

    scheduler.setActive(true);
    scheduler.scheduleEmergency('event-1');
    vi.advanceTimersByTime(200);
    scheduler.updateCallbacks({
      getDelayMs: () => 500,
      getBestThreat: () => latestThreat,
      onHandleEmergency: latestHandler,
    });
    vi.advanceTimersByTime(300);

    expect(firstHandler).not.toHaveBeenCalled();
    expect(latestHandler).toHaveBeenCalledOnce();
    expect(latestHandler).toHaveBeenCalledWith(latestThreat);
  });

  it('handles each emergency id only once and accepts a new id', () => {
    const onHandleEmergency = vi.fn();
    const scheduler = new AIAgentScheduler({
      getDelayMs: () => 100,
      getBestThreat: () => ({ id: 'threat-1' }),
      onHandleEmergency,
    });

    scheduler.setActive(true);
    expect(scheduler.scheduleEmergency('event-1')).toBe(true);
    expect(scheduler.scheduleEmergency('event-1')).toBe(false);
    vi.advanceTimersByTime(100);
    expect(scheduler.scheduleEmergency('event-1')).toBe(false);

    expect(scheduler.scheduleEmergency('event-2')).toBe(true);
    vi.advanceTimersByTime(100);
    expect(onHandleEmergency).toHaveBeenCalledTimes(2);
  });

  it('cancels pending work when AI is deactivated', () => {
    const onHandleEmergency = vi.fn();
    const scheduler = new AIAgentScheduler({
      getDelayMs: () => 1000,
      getBestThreat: () => ({ id: 'threat-1' }),
      onHandleEmergency,
    });

    scheduler.setActive(true);
    scheduler.scheduleEmergency('event-1');
    scheduler.setActive(false);
    vi.runAllTimers();

    expect(onHandleEmergency).not.toHaveBeenCalled();
  });

  it('keeps initial assessment and emergency timers independent', () => {
    const onHandleEmergency = vi.fn();
    const scheduler = new AIAgentScheduler({
      getDelayMs: () => 100,
      getBestThreat: () => ({ id: 'threat-1' }),
      onHandleEmergency,
    });

    scheduler.setActive(true);
    scheduler.scheduleInitialAssessment();
    scheduler.scheduleEmergency('event-1');
    vi.advanceTimersByTime(100);

    expect(onHandleEmergency).toHaveBeenCalledTimes(2);
  });

  it('retries a temporarily empty threat list and handles it when ready', () => {
    const threat = { id: 'threat-ready' };
    const getBestThreat = vi.fn()
      .mockReturnValueOnce(null)
      .mockReturnValueOnce(null)
      .mockReturnValue(threat);
    const onHandleEmergency = vi.fn();
    const scheduler = new AIAgentScheduler({
      getDelayMs: () => 100,
      getBestThreat,
      onHandleEmergency,
    });

    scheduler.setActive(true);
    scheduler.scheduleEmergency('event-1');
    vi.advanceTimersByTime(100 + AI_THREAT_RETRY_DELAY_MS * 2);

    expect(getBestThreat).toHaveBeenCalledTimes(3);
    expect(onHandleEmergency).toHaveBeenCalledOnce();
    expect(onHandleEmergency).toHaveBeenCalledWith(threat);
  });

  it('stops retrying after the bounded attempt count', () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const getBestThreat = vi.fn(() => null);
    const onHandleEmergency = vi.fn();
    const scheduler = new AIAgentScheduler({
      getDelayMs: () => 100,
      getBestThreat,
      onHandleEmergency,
    });

    scheduler.setActive(true);
    scheduler.scheduleEmergency('event-1');
    vi.runAllTimers();

    expect(getBestThreat).toHaveBeenCalledTimes(AI_THREAT_MAX_ATTEMPTS);
    expect(onHandleEmergency).not.toHaveBeenCalled();
    expect(errorSpy).toHaveBeenCalledOnce();
  });
});
