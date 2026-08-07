import { describe, expect, it } from 'vitest';
import { selectRadarTarget, selectSAThreat } from './aiAccuracyDecision';

const decision = (
  intended_correct: boolean,
  pool_random: number,
  expected_target_id: string,
  selected_pool: string[],
  fallback_reason: string | null = null,
) => ({
  task_id: 1,
  task_seq: 1,
  decision_seed: 2,
  decision_random: intended_correct ? 0.1 : 0.9,
  pool_random,
  intended_correct,
  selection_protocol: 'server-authoritative-target-v1' as const,
  selected_pool,
  fallback_reason,
  pool_index: selected_pool.indexOf(expected_target_id),
  expected_target_id,
});

describe('server-owned AI target selection', () => {
  it('executes the exact Radar target supplied by the server', () => {
    const targets = [{ id: 'enemy-1' }, { id: 'enemy-2' }, { id: 'friend-1' }];
    expect(selectRadarTarget(targets, decision(true, 0.9, 'enemy-2', ['enemy-1', 'enemy-2'])).selected?.id).toBe('enemy-2');
    expect(selectRadarTarget(targets, decision(false, 0.4, 'friend-1', ['friend-1'])).selected?.id).toBe('friend-1');
  });

  it('preserves the server Radar fallback audit', () => {
    const result = selectRadarTarget(
      [{ id: 'friend-1' }],
      decision(true, 0.5, 'friend-1', ['friend-1'], 'enemy_pool_empty'),
    );
    expect(result.selected?.id).toBe('friend-1');
    expect(result.fallbackReason).toBe('enemy_pool_empty');
  });

  it('executes the exact SA target supplied by the server', () => {
    const threats = [{ id: 'highest' }, { id: 'second' }, { id: 'third' }];
    expect(selectSAThreat(threats, decision(true, 0.8, 'highest', ['highest'])).selected?.id).toBe('highest');
    expect(selectSAThreat(threats, decision(false, 0.8, 'third', ['second', 'third'])).selected?.id).toBe('third');
  });

  it('preserves the single-threat SA fallback audit', () => {
    const result = selectSAThreat(
      [{ id: 'only' }],
      decision(false, 0.2, 'only', ['only'], 'single_threat_no_incorrect_pool'),
    );
    expect(result.selected?.id).toBe('only');
    expect(result.fallbackReason).toBe('single_threat_no_incorrect_pool');
  });

  it('does not select a target when the server target is missing from the task', () => {
    const result = selectRadarTarget(
      [{ id: 'enemy-1' }],
      decision(true, 0.2, 'enemy-2', ['enemy-1', 'enemy-2']),
    );
    expect(result.selected).toBeUndefined();
  });
});
