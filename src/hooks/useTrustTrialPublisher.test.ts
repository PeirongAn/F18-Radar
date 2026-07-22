import { describe, expect, it } from 'vitest';
import { getTrustTrialSnapshotSignature } from './useTrustTrialPublisher';
import type { TrustTrialSnapshot } from '../types/trustControl';

const makeSnapshot = (): TrustTrialSnapshot => ({
  taskId: 101,
  taskGroupId: 7,
  taskType: 'RADAR_TARGETING',
  trialSequence: 1,
  control: null,
  aiRecommendation: null,
  candidates: [{ id: 'T1', label: 'T1', score: 0.8 }],
  focusedCandidate: null,
  humanSelection: null,
  groundTruthId: 'T1',
  manualReviewCount: 0,
  invalidReviewCount: 0,
  manualReviewActive: false,
  manualReviewDurationMs: 0,
  manualReviewCandidate: null,
  manualReviewFeedback: { status: 'idle', message: '未启动人工复核' },
  comparisonVisible: false,
  glowActive: false,
  aiRecommendationShownAt: null,
});

describe('getTrustTrialSnapshotSignature', () => {
  it('is stable when React recreates equivalent nested objects', () => {
    expect(getTrustTrialSnapshotSignature(makeSnapshot()))
      .toBe(getTrustTrialSnapshotSignature(makeSnapshot()));
  });

  it('changes when observable trial content changes', () => {
    const next = makeSnapshot();
    next.manualReviewCount = 1;
    expect(getTrustTrialSnapshotSignature(next))
      .not.toBe(getTrustTrialSnapshotSignature(makeSnapshot()));
  });
});
