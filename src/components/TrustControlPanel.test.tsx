import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import TrustControlPanel from './TrustControlPanel';
import type { TrustTrialSnapshot } from '../types/trustControl';

const candidate = {
  id: 'enemy-1',
  label: '目标1',
  displayNumber: 1,
  type: 'army',
  score: 0.99,
  azimuthDeg: 12.5,
  distanceNm: 18.2,
  speedRaw: 7.4,
  headingDeg: 241.0,
  relativeHeadingDeg: -37.0,
  observedAtMs: 1_700_000_000_000,
};

const snapshot: TrustTrialSnapshot = {
  taskId: 10,
  taskGroupId: 3,
  taskType: 'RADAR_TARGETING',
  trialSequence: 2,
  control: {
    enabled: true,
    condition_key: { task_group_id: 3, user_id: 'pilot', task_type: 'RADAR_TARGETING', difficulty: 'low', ai_level: 'L1' },
    history_count: 4,
    ui_mode: 'standard',
    appropriate_rate: 0.75,
    under_trust_rate: 0.25,
    over_trust_rate: 0,
    direction_index: 0.25,
    ai_history_accuracy: 0.75,
    ai_history_correct_count: 3,
    ai_history_valid_count: 4,
    ai_history_accuracy_series: [1, 0.5, 2 / 3, 0.75],
    ai_history_correctness_series: [true, false, true, true],
    ai_statistical_accuracy: 0.4,
    ai_statistical_accuracy_series: [0.36, 0.38, 0.41, 0.39, 0.43, 0.40, 0.42, 0.38, 0.41, 0.44, 0.37, 0.41],
    ai_statistical_accuracy_lower_bound: 0.3,
    ai_statistical_accuracy_upper_bound: 0.5,
    ai_statistical_accuracy_source: 'ai_level_probability_range',
    ai_statistical_accuracy_curve_seed: 20260730,
    disclose_ai_reliability: false,
    manual_review_button: 3,
    sensor_focus_radius_px: 30,
    threat_focus_radius_px: 40,
    focus_dwell_ms: 150,
  },
  aiRecommendation: candidate,
  candidates: [candidate],
  focusedCandidate: candidate,
  humanSelection: null,
  groundTruthId: 'enemy-1',
  manualReviewCount: 1,
  invalidReviewCount: 0,
  manualReviewActive: true,
  manualReviewDurationMs: 0,
  manualReviewCandidate: candidate,
  manualReviewFeedback: { status: 'active', message: '正在复核AI推荐目标1' },
  comparisonVisible: false,
  glowActive: false,
  aiRecommendationShownAt: 1_700_000_000_000,
};

describe('TrustControlPanel radar evidence', () => {
  it('shows the stable AI-level curve and raw values without leaking internal identity or scores', () => {
    const markup = renderToStaticMarkup(<TrustControlPanel snapshot={snapshot} />);
    expect(markup).toContain('data-gaze-aoi="right_ai_history_accuracy"');
    expect(markup.indexOf('data-gaze-aoi="right_ai_history_accuracy"'))
      .toBeLessThan(markup.indexOf('data-gaze-aoi="right_recommendation"'));
    expect(markup).toContain('AI统计识别准确率');
    expect(markup).toContain('等级统计值');
    expect(markup).toContain('40%');
    expect(markup).toContain('L1 · 30%～50%');
    expect(markup).not.toContain('75%（3/4）');
    expect(markup).not.toContain('历史试次');
    expect(markup).toContain('<path');
    expect(markup).toContain('目标1');
    expect(markup).toContain('12.5°');
    expect(markup).toContain('18.2 NM');
    expect(markup).toContain('7.4（原始值）');
    expect(markup).toContain('当前推荐');
    expect(markup).toContain('高优先级');
    expect(markup).toContain('data-recommended="true"');
    expect(markup).not.toContain('enemy-1');
    expect(markup).not.toContain('army');
    expect(markup).not.toContain('0.99');
  });

  it('shows an explicit empty state when the startup curve is unavailable', () => {
    const emptySnapshot: TrustTrialSnapshot = {
      ...snapshot,
      control: {
        ...snapshot.control,
        ai_statistical_accuracy: null,
        ai_statistical_accuracy_series: [],
        ai_statistical_accuracy_lower_bound: null,
        ai_statistical_accuracy_upper_bound: null,
        ai_statistical_accuracy_source: null,
        ai_statistical_accuracy_curve_seed: null,
      },
    };
    const markup = renderToStaticMarkup(<TrustControlPanel snapshot={emptySnapshot} />);

    expect(markup).toContain('暂无统计值');
    expect(markup).not.toContain('75%（3/4）');
  });

  it('renders SA candidate observations with SA fields instead of empty radar fields', () => {
    const saCandidate = {
      ...candidate,
      id: 'PrimaryAir-1001',
      label: '目标2',
      displayNumber: 2,
      categoryLabel: '一级空中威胁',
      sourceLabel: 'J-11',
      distance: 146.8,
      positionX: 324,
      positionY: 188,
    };
    const saSnapshot: TrustTrialSnapshot = {
      ...snapshot,
      taskType: 'SA_THREAT_RESPONSE',
      aiRecommendation: saCandidate,
      candidates: [saCandidate],
      focusedCandidate: saCandidate,
      manualReviewCandidate: saCandidate,
      groundTruthId: saCandidate.id,
    };
    const markup = renderToStaticMarkup(<TrustControlPanel snapshot={saSnapshot} />);
    expect(markup).toContain('一级空中威胁');
    expect(markup).toContain('J-11');
    expect(markup).toContain('146.8');
    expect(markup).toContain('324, 188');
    expect(markup).not.toContain('PrimaryAir-1001');
  });
});
