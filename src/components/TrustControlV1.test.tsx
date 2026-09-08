import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import TrustControlPanel from './TrustControlPanel';
import { strategyLabel } from '../types/trustConfig';
import type { TrustDisplayPolicy } from '../types/trustConfig';
import type { TrustTrialSnapshot } from '../types/trustControl';

const base: TrustDisplayPolicy = { show_evidence: false, show_reliability: false, highlight: 'none' };
function render(policy: TrustDisplayPolicy, taskType = 'RADAR_TARGETING') {
  const candidate = { id: 'enemy1', label: '目标甲', azimuthDeg: 17, distanceNm: 23,
    categoryLabel: '来袭导弹', sourceLabel: '当前传感器', distance: 42 };
  const snapshot = { taskType, aiRecommendation: candidate, candidates: [candidate],
    glowActive: true, manualReviewFeedback: { status: 'idle', message: '未启动' },
    manualReviewCount: 0, manualReviewDurationMs: 0,
    control: { enabled: true, ui_mode: 'trust_support', condition_key: { ai_level: 'L1' },
      ai_statistical_accuracy: null, ai_statistical_accuracy_lower_bound: null,
      ai_statistical_accuracy_upper_bound: null, ai_statistical_accuracy_series: [],
      display_config: { tendency: 'normal', source: 'config', valid: true, policy } },
  } as unknown as TrustTrialSnapshot;
  return renderToStaticMarkup(<TrustControlPanel snapshot={snapshot} />);
}

describe('configuration-driven display', () => {
  it.each([
    [base, '基础显示'], [{ ...base, show_evidence: true }, '内容调控'],
    [{ ...base, highlight: 'observation' }, '形式调控'],
    [{ ...base, show_reliability: true, highlight: 'reliability' }, '联合调控'],
  ] as [TrustDisplayPolicy, string][])('labels independent content and form', (policy, expected) => {
    expect(strategyLabel(policy)).toBe(expected);
  });
  it('form only never adds evidence or reliability prose', () => {
    const html = render({ ...base, highlight: 'reliability' });
    expect(html).toContain('trust-section--reliability-highlight');
    expect(html).not.toContain('补充观测依据');
    expect(html).not.toContain('AI建议可能出错');
    expect(html).not.toContain('trust-hero--glow');
    expect(html).not.toContain('trust-panel--support');
  });
  it('content only never highlights', () => {
    const html = render({ ...base, show_evidence: true, show_reliability: true });
    expect(html).toContain('补充观测依据');
    expect(html).toContain('AI建议可能出错');
    expect(html).not.toContain('trust-section--observation-highlight');
    expect(html).not.toContain('trust-section--reliability-highlight');
  });
  it('renders task-specific real observations with the same policy', () => {
    const policy = { ...base, show_evidence: true };
    expect(render(policy)).toContain('23.0 NM');
    expect(render(policy)).toContain('17.0°');
    const sa = render(policy, 'SA_THREAT_RESPONSE');
    expect(sa).toContain('来袭导弹');
    expect(sa).toContain('当前传感器');
    expect(sa).not.toContain('23.0 NM');
  });
});
