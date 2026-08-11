import React from 'react';
import ReactDOM from 'react-dom/client';
import TrustControlPanel from '../../src/components/TrustControlPanel';
import type { TrustCandidate, TrustTrialSnapshot } from '../../src/types/trustControl';
import '../../src/index.css';

const now = Date.now();
const candidates: TrustCandidate[] = [
  { id: 'air-1', label: '目标1', displayNumber: 1, categoryLabel: '一级空中威胁', sourceLabel: 'J-11', distance: 46.8, positionX: 324, positionY: 188, observedAtMs: now },
  { id: 'air-2', label: '目标2', displayNumber: 2, categoryLabel: '二级空中威胁', sourceLabel: '不明航迹', distance: 218.6, positionX: 441, positionY: 254, observedAtMs: now - 123 },
  { id: 'air-3', label: '目标3', displayNumber: 3, categoryLabel: '三级空中威胁', sourceLabel: '运输机', distance: 117.4, positionX: 207, positionY: 311, observedAtMs: now - 256 },
  { id: 'air-4', label: '目标4', displayNumber: 4, categoryLabel: '二级空中威胁', sourceLabel: '高速航迹', distance: 43.1, positionX: 502, positionY: 142, observedAtMs: now - 318 },
  { id: 'air-5', label: '目标5', displayNumber: 5, categoryLabel: '三级空中威胁', sourceLabel: '民用航迹', distance: 75.8, positionX: 165, positionY: 228, observedAtMs: now - 429 },
];

const snapshot: TrustTrialSnapshot = {
  taskId: 108,
  taskGroupId: 3,
  taskType: 'SA_THREAT_RESPONSE',
  trialSequence: 3,
  control: {
    enabled: true,
    condition_key: { task_group_id: 3, user_id: 'ANPEIRONG0705', task_type: 'SA_THREAT_RESPONSE', difficulty: 'high', ai_level: 'L2' },
    history_count: 8,
    ui_mode: 'standard',
    appropriate_rate: 0.75,
    under_trust_rate: 0.125,
    over_trust_rate: 0.125,
    direction_index: 0,
    ai_history_accuracy: 0.875,
    ai_history_correct_count: 7,
    ai_history_valid_count: 8,
    ai_history_accuracy_series: [1, 1, 0.67, 0.75, 0.8, 0.83, 0.86, 0.875],
    ai_history_correctness_series: [true, true, false, true, true, true, true, true],
    disclose_ai_reliability: true,
    manual_review_button: 3,
    sensor_focus_radius_px: 30,
    threat_focus_radius_px: 40,
    focus_dwell_ms: 150,
  },
  aiRecommendation: candidates[0],
  candidates,
  focusedCandidate: candidates[1],
  humanSelection: null,
  groundTruthId: candidates[0].id,
  manualReviewCount: 1,
  invalidReviewCount: 0,
  manualReviewActive: false,
  manualReviewDurationMs: 2400,
  manualReviewCandidate: null,
  manualReviewFeedback: { status: 'idle', message: '按下第3键可复核AI推荐目标' },
  comparisonVisible: false,
  glowActive: true,
  aiRecommendationShownAt: now,
};

const Preview = () => (
  <main style={{ height: '100dvh', display: 'grid', gridTemplateColumns: '1fr minmax(520px, 36%)', background: '#020905' }}>
    <section style={{
      position: 'relative',
      overflow: 'hidden',
      borderRight: '1px solid #12321d',
      background: 'radial-gradient(circle at 50% 48%, rgba(0, 60, 25, 0.23), transparent 35%), #030a05',
    }}>
      <div style={{
        position: 'absolute',
        inset: '14% 15%',
        border: '1px solid rgba(120, 190, 135, 0.35)',
        backgroundImage: 'linear-gradient(rgba(34, 105, 57, 0.13) 1px, transparent 1px), linear-gradient(90deg, rgba(34, 105, 57, 0.13) 1px, transparent 1px)',
        backgroundSize: '56px 56px',
      }} />
      <div style={{
        position: 'absolute',
        left: '50%',
        top: '51%',
        width: 14,
        height: 14,
        border: '2px solid #24df82',
        transform: 'translate(-50%, -50%) rotate(45deg)',
        boxShadow: '0 0 16px rgba(36, 223, 130, 0.55)',
      }} />
    </section>
    <aside style={{ display: 'flex', minHeight: 0, flexDirection: 'column', overflow: 'hidden', background: '#030c05' }}>
      <TrustControlPanel snapshot={snapshot} />
      <div style={{ flex: 1, borderTop: '1px solid #0a2010', padding: 18, color: '#486651', fontSize: 12 }}>通信日志</div>
    </aside>
  </main>
);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><Preview /></React.StrictMode>
);
