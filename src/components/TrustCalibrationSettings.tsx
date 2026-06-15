import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { observer } from 'mobx-react-lite';
import agentStore from '../stores/AgentStore';
import { ConfiguredTrustState, TrustCalibrationConfig } from '../types/trustCalibration';
import {
  DEFAULT_TRUST_CALIBRATION_CONFIG,
  mergeTrustCalibrationConfig,
} from '../utils/trustCalibration';

type SectionKey = 'overview' | 'sensor' | 'threat' | 'experiment' | 'display';
type DecisionState = 'normal' | 'under' | 'over';
type FactorDirection = 'over' | 'under';

interface ScoreFactor {
  key: string;
  label: string;
  direction: FactorDirection;
  score: number;
  maxScore: number;
  reason: string;
}

interface ScoreBreakdown {
  state: DecisionState;
  score: number;
  overScore: number;
  underScore: number;
  factors: ScoreFactor[];
  summary: string;
}

interface TrustCalibrationSettingsProps {
  onClose: () => void;
  connected?: boolean;
  currentUserId?: string;
  sendMessage?: (message: object) => void;
}

type SaveStatus = 'idle' | 'local' | 'sent';
type BehaviorThresholdPatch = Partial<Pick<
  TrustCalibrationConfig['sensor'],
  'direct_accept_threshold' | 'consecutive_reject_threshold' | 'latency_threshold_ms'
>>;

interface TrustHistoryStats {
  event_count: number;
  human_event_count: number;
  ai_event_count: number;
  human_decision_count: number;
  human_accept_count: number;
  human_reject_count: number;
  max_consecutive_reject_count: number;
  direct_accept_without_evidence_count: number;
  evidence_viewed_count: number;
  manual_review_count: number;
  result_confirmed_count: number;
  average_confirmation_latency_ms?: number | null;
  last_event_at?: number | null;
  // —— 真值口径 ——
  truth_known_count?: number;
  ai_correct_count?: number;
  ai_incorrect_count?: number;
  unwarranted_reject_count?: number;
  justified_reject_count?: number;
  unwarranted_accept_count?: number;
  ai_accuracy?: number | null;
  truth_coverage?: number | null;
}

interface TrustHistoryEvent {
  actor?: 'ai' | 'human';
  task?: 'sensor' | 'threat';
  eventType?: string;
  timestamp?: number;
  recommendationId?: string;
  selectedId?: string;
  source?: string;
  _operation?: {
    task_id?: number;
    operation_type?: string;
    user_id?: string;
  };
}

interface TrustHistoryResponse {
  ok: boolean;
  minimum_sample_size: number;
  sample_sufficient: boolean;
  operation_count: number;
  event_count: number;
  filters?: {
    user_id?: string | null;
    limit?: number;
  };
  summary: TrustHistoryStats;
  task_breakdown: Record<string, TrustHistoryStats>;
  recent_events: TrustHistoryEvent[];
  msg?: string;
}

const cloneConfig = (config: TrustCalibrationConfig): TrustCalibrationConfig =>
  JSON.parse(JSON.stringify(config)) as TrustCalibrationConfig;

const panelStyle: React.CSSProperties = {
  border: '1px solid #0d4020',
  background: 'rgba(1, 14, 6, 0.82)',
  borderRadius: '4px',
  boxShadow: 'inset 0 0 18px rgba(0,255,100,0.025)',
};

const fieldLabelStyle: React.CSSProperties = {
  color: '#86c58f',
  fontSize: '12px',
  letterSpacing: '0.08em',
};

const inputStyle: React.CSSProperties = {
  width: '82px',
  height: '30px',
  background: 'rgba(0, 18, 8, 0.92)',
  border: '1px solid #166232',
  color: '#9effb5',
  borderRadius: '3px',
  padding: '0 8px',
  fontFamily: "'Share Tech Mono', monospace",
  fontSize: '12px',
  outline: 'none',
};

const actionButtonStyle: React.CSSProperties = {
  height: '34px',
  padding: '0 16px',
  background: 'rgba(0, 40, 16, 0.8)',
  border: '1px solid #168842',
  color: '#74ff9a',
  borderRadius: '3px',
  cursor: 'pointer',
  fontFamily: "'SimHei', 'Microsoft YaHei', sans-serif",
  letterSpacing: '0.08em',
};

const secondaryButtonStyle: React.CSSProperties = {
  ...actionButtonStyle,
  background: 'rgba(0, 32, 16, 0.58)',
  borderColor: '#0ea856',
  color: '#7dffad',
};

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));
const roundScore = (value: number) => Math.round(value * 10) / 10;
const getScoreState = (score: number): DecisionState => {
  if (score <= -30) return 'over';
  if (score >= 30) return 'under';
  return 'normal';
};

const scoreReason = (score: number) => {
  if (score <= -30) return `S=${roundScore(score)}，落入过信任风险区，需要复核或查看证据。`;
  if (score >= 30) return `S=${roundScore(score)}，落入欠信任风险区，需要解释 AI 推荐依据。`;
  return `S=${roundScore(score)}，处于正常校准区，仅保留常规提示。`;
};

const formatCount = (value: number | undefined | null) => String(value ?? 0);
const formatLatency = (value: number | undefined | null) =>
  typeof value === 'number' && Number.isFinite(value) ? `${Math.round(value)}ms` : '暂无';
const formatEventTime = (timestamp: number | undefined | null) =>
  typeof timestamp === 'number' && Number.isFinite(timestamp)
    ? new Date(timestamp).toLocaleString()
    : '暂无';
const hitText = (hit: boolean) => hit ? '命中' : '未命中';
const roundLatencyThreshold = (value: number) =>
  clamp(Math.round(value / 500) * 500, 500, 15000);
const eventTypeLabel = (eventType?: string) => {
  switch (eventType) {
    case 'ai_recommendation_shown': return 'AI推荐展示';
    case 'ai_auto_action': return 'AI自动动作';
    case 'human_accept': return '人工接受';
    case 'human_reject': return '人工拒绝';
    case 'human_result_confirmed': return '查看结果确认';
    case 'evidence_viewed': return '查看证据';
    case 'manual_review_requested': return '请求人工复核';
    case 'manual_review_done': return '人工复核完成';
    default: return eventType || '未知事件';
  }
};

const configuredStateMeta = (state: ConfiguredTrustState) => {
  switch (state) {
    case 'under_trust':
      return { label: '欠信任', state: 'under' as DecisionState };
    case 'over_trust':
      return { label: '过信任', state: 'over' as DecisionState };
    default:
      return { label: '信任适当', state: 'normal' as DecisionState };
  }
};

const HistoryRuleValidationPanel: React.FC<{
  title: string;
  stats: TrustHistoryStats | undefined;
  directAcceptThreshold: number;
  rejectThreshold: number;
  latencyThresholdMs: number;
}> = ({ title, stats, directAcceptThreshold, rejectThreshold, latencyThresholdMs }) => {
  const safeStats = stats ?? {
    event_count: 0,
    human_event_count: 0,
    ai_event_count: 0,
    human_decision_count: 0,
    human_accept_count: 0,
    human_reject_count: 0,
    max_consecutive_reject_count: 0,
    direct_accept_without_evidence_count: 0,
    evidence_viewed_count: 0,
    manual_review_count: 0,
    result_confirmed_count: 0,
    average_confirmation_latency_ms: null,
    last_event_at: null,
  };
  const directAcceptHit = safeStats.direct_accept_without_evidence_count >= directAcceptThreshold;
  const rejectHit = safeStats.max_consecutive_reject_count >= rejectThreshold;
  const latencyHit =
    typeof safeStats.average_confirmation_latency_ms === 'number' &&
    safeStats.average_confirmation_latency_ms >= latencyThresholdMs;
  const rows = [
    {
      label: '过信任验证',
      value: `${safeStats.direct_accept_without_evidence_count} / ${directAcceptThreshold}`,
      hit: directAcceptHit,
      hint: '无证据直接接受达到阈值',
      state: 'over' as DecisionState,
    },
    {
      label: '欠信任验证',
      value: `${safeStats.max_consecutive_reject_count} / ${rejectThreshold}`,
      hit: rejectHit,
      hint: '最大连续拒绝达到阈值',
      state: 'under' as DecisionState,
    },
    {
      label: '时延验证',
      value: `${formatLatency(safeStats.average_confirmation_latency_ms)} / ${latencyThresholdMs}ms`,
      hit: latencyHit,
      hint: '平均确认时延超过阈值',
      state: 'under' as DecisionState,
    },
  ];

  return (
    <div style={{ ...panelStyle, padding: '16px' }}>
      <div style={{ color: '#dfffea', fontSize: '15px', fontWeight: 700, marginBottom: '6px' }}>{title}</div>
      <div style={{ color: '#86c58f', fontSize: '11px', lineHeight: 1.5, marginBottom: '12px' }}>
        用历史行为指标套入当前阈值，检查规则是否会被触发。
      </div>
      <div style={{ display: 'grid', gap: '8px' }}>
        {rows.map(row => {
          const tone = getDecisionTone(row.state);
          return (
            <div key={row.label} style={{
              display: 'grid',
              gridTemplateColumns: '96px 1fr 56px',
              gap: '10px',
              alignItems: 'center',
              border: `1px solid ${row.hit ? tone.border : 'rgba(80,170,100,0.18)'}`,
              background: row.hit ? tone.bg : 'rgba(0,12,5,0.55)',
              padding: '9px 10px',
              borderRadius: '3px',
            }}>
              <span style={{ color: row.hit ? tone.color : '#bdf5c8', fontSize: '12px', fontWeight: 700 }}>{row.label}</span>
              <span style={{ color: '#d8ffe3', fontSize: '11px', lineHeight: 1.4 }}>
                {row.value} · {row.hint}
              </span>
              <span style={{ color: row.hit ? tone.color : '#6fa878', fontSize: '12px', textAlign: 'right' }}>
                {hitText(row.hit)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const HistoryCalibrationSuggestionPanel: React.FC<{
  title: string;
  stats: TrustHistoryStats | undefined;
  config: Pick<TrustCalibrationConfig['sensor'], 'direct_accept_threshold' | 'consecutive_reject_threshold' | 'latency_threshold_ms'>;
  sampleSufficient: boolean;
  onApply: (patch: BehaviorThresholdPatch) => void;
}> = ({ title, stats, config, sampleSufficient, onApply }) => {
  const safeStats: TrustHistoryStats = stats ?? {
    event_count: 0,
    human_event_count: 0,
    ai_event_count: 0,
    human_decision_count: 0,
    human_accept_count: 0,
    human_reject_count: 0,
    max_consecutive_reject_count: 0,
    direct_accept_without_evidence_count: 0,
    evidence_viewed_count: 0,
    manual_review_count: 0,
    result_confirmed_count: 0,
    average_confirmation_latency_ms: null,
    last_event_at: null,
    truth_known_count: 0,
    unwarranted_reject_count: 0,
    unwarranted_accept_count: 0,
    truth_coverage: null,
    ai_accuracy: null,
  };
  // 真值口径就绪条件：覆盖率达标且有已知真值样本
  const MIN_TRUTH_COVERAGE = 0.5;
  const truthCoverage = safeStats.truth_coverage ?? 0;
  const truthKnown = safeStats.truth_known_count ?? 0;
  const truthReady = truthKnown > 0 && truthCoverage >= MIN_TRUTH_COVERAGE;
  const ready = sampleSufficient && truthReady;
  const unwarrantedAccept = safeStats.unwarranted_accept_count ?? 0;
  const unwarrantedReject = safeStats.unwarranted_reject_count ?? 0;
  const suggestions = [
    {
      key: 'direct_accept_threshold',
      label: '直接接受阈值',
      current: config.direct_accept_threshold,
      suggested: unwarrantedAccept > 0
        ? clamp(unwarrantedAccept, 1, 6)
        : config.direct_accept_threshold,
      evidence: `无证据接受了实际错误的推荐 ${unwarrantedAccept} 次`,
    },
    {
      key: 'consecutive_reject_threshold',
      label: '连续拒绝阈值',
      current: config.consecutive_reject_threshold,
      suggested: unwarrantedReject > 0
        ? clamp(unwarrantedReject, 1, 6)
        : config.consecutive_reject_threshold,
      evidence: `拒绝了实际正确的推荐 ${unwarrantedReject} 次（最大连续拒绝 ${safeStats.max_consecutive_reject_count} 次）`,
    },
    {
      key: 'latency_threshold_ms',
      label: '确认时延阈值',
      current: config.latency_threshold_ms,
      suggested: typeof safeStats.average_confirmation_latency_ms === 'number'
        ? roundLatencyThreshold(safeStats.average_confirmation_latency_ms)
        : config.latency_threshold_ms,
      evidence: `历史平均确认时延 ${formatLatency(safeStats.average_confirmation_latency_ms)}`,
    },
  ] as const;
  const changedSuggestions = suggestions.filter(item => item.suggested !== item.current);

  return (
    <div style={{
      ...panelStyle,
      padding: '16px',
      borderColor: ready ? '#176a8a' : '#8a7518',
      background: ready ? 'rgba(0,24,20,0.68)' : 'rgba(46,35,0,0.38)',
    }}>
      <div style={{ color: '#dfffea', fontSize: '15px', fontWeight: 700, marginBottom: '6px' }}>{title}</div>
      <div style={{ color: ready ? '#86c58f' : '#ffdf73', fontSize: '11px', lineHeight: 1.5, marginBottom: '12px' }}>
        {ready
          ? `真值覆盖率 ${Math.round(truthCoverage * 100)}%，建议基于「该拒/该接」真值口径，仅写入草稿；需再点击“应用并保存”才生效。`
          : !sampleSufficient
            ? '样本量不足，暂不建议调整阈值。'
            : `真值样本不足（覆盖率 ${Math.round(truthCoverage * 100)}%，已知 ${truthKnown} 条），暂不校准；请确保任务回传正确答案。`}
      </div>
      <div style={{ display: 'grid', gap: '8px' }}>
        {suggestions.map(item => {
          const changed = item.suggested !== item.current;
          return (
            <div key={item.key} style={{
              display: 'grid',
              gridTemplateColumns: '100px 1fr 84px',
              gap: '10px',
              alignItems: 'center',
              border: `1px solid ${changed && ready ? '#1ca8ff' : 'rgba(80,170,100,0.18)'}`,
              background: changed && ready ? 'rgba(0,42,55,0.35)' : 'rgba(0,12,5,0.55)',
              padding: '9px 10px',
              borderRadius: '3px',
            }}>
              <span style={{ color: changed && ready ? '#7bdcff' : '#bdf5c8', fontSize: '12px', fontWeight: 700 }}>{item.label}</span>
              <span style={{ color: '#d8ffe3', fontSize: '11px', lineHeight: 1.4 }}>
                当前 {item.current} · 建议 {item.suggested} · {item.evidence}
              </span>
              <button
                type="button"
                disabled={!ready || !changed}
                onClick={() => onApply({ [item.key]: item.suggested } as BehaviorThresholdPatch)}
                style={{
                  height: '28px',
                  border: `1px solid ${ready && changed ? '#1ca8ff' : '#245331'}`,
                  background: ready && changed ? 'rgba(0,42,55,0.72)' : 'rgba(0,18,8,0.45)',
                  color: ready && changed ? '#9cf6ff' : '#5c8264',
                  borderRadius: '3px',
                  cursor: ready && changed ? 'pointer' : 'not-allowed',
                  fontSize: '11px',
                  fontFamily: "'SimHei', 'Microsoft YaHei', sans-serif",
                }}
              >
                写入草稿
              </button>
            </div>
          );
        })}
      </div>
      {ready && changedSuggestions.length === 0 && (
        <div style={{ color: '#6fa878', fontSize: '11px', marginTop: '10px' }}>
          当前阈值与真值口径建议一致，暂无调整建议。
        </div>
      )}
    </div>
  );
};

const RangeField: React.FC<{
  label: string;
  hint: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit?: string;
  highlight?: DecisionState;
  statusText?: string;
  onChange: (value: number) => void;
}> = ({ label, hint, value, min, max, step, unit, highlight, statusText, onChange }) => {
  const tone = highlight ? getDecisionTone(highlight) : null;
  return (
  <div style={{
    ...panelStyle,
    padding: '14px 16px',
    borderColor: tone?.border ?? panelStyle.border?.toString().replace('1px solid ', ''),
    background: tone ? `linear-gradient(135deg, ${tone.bg}, rgba(1,14,6,0.88) 58%)` : panelStyle.background,
    boxShadow: tone ? `0 0 18px ${highlight === 'over' ? 'rgba(255,159,53,0.18)' : highlight === 'under' ? 'rgba(45,216,255,0.18)' : 'rgba(0,255,136,0.12)'}` : panelStyle.boxShadow,
  }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '14px', alignItems: 'center' }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#d4ffe0', fontSize: '14px', letterSpacing: '0.08em', marginBottom: '4px' }}>
          {label}
          {tone && (
            <span style={{
              color: tone.color,
              border: `1px solid ${tone.border}`,
              background: tone.bg,
              padding: '2px 6px',
              borderRadius: '999px',
              fontSize: '10px',
              letterSpacing: '0.08em',
            }}>
              当前已触发
            </span>
          )}
        </div>
        <div style={fieldLabelStyle}>{hint}</div>
      </div>
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={event => onChange(Number(event.target.value))}
        style={inputStyle}
      />
    </div>
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '12px' }}>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={event => onChange(Number(event.target.value))}
        style={{ flex: 1, accentColor: '#00cc66' }}
      />
      <span style={{ color: '#00ff88', fontSize: '12px', width: '62px', textAlign: 'right' }}>
        {value}{unit ?? ''}
      </span>
    </div>
    {statusText && (
      <div style={{
        marginTop: '10px',
        color: tone?.color ?? '#83d994',
        fontSize: '11px',
        lineHeight: 1.45,
        borderTop: '1px solid rgba(80,170,100,0.18)',
        paddingTop: '8px',
      }}>
        {statusText}
      </div>
    )}
  </div>
  );
};

const ToggleField: React.FC<{
  label: string;
  hint: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}> = ({ label, hint, checked, onChange }) => (
  <button
    type="button"
    onClick={() => onChange(!checked)}
    style={{
      ...panelStyle,
      width: '100%',
      padding: '14px 16px',
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      gap: '18px',
      cursor: 'pointer',
      textAlign: 'left',
    }}
  >
    <span>
      <span style={{ display: 'block', color: '#d4ffe0', fontSize: '14px', letterSpacing: '0.08em', marginBottom: '4px' }}>{label}</span>
      <span style={fieldLabelStyle}>{hint}</span>
    </span>
    <span style={{
      width: '48px',
      height: '24px',
      border: `1px solid ${checked ? '#00d56d' : '#35513a'}`,
      borderRadius: '999px',
      background: checked ? 'rgba(0, 160, 80, 0.26)' : 'rgba(16, 28, 18, 0.9)',
      padding: '3px',
      flexShrink: 0,
    }}>
      <span style={{
        display: 'block',
        width: '16px',
        height: '16px',
        borderRadius: '50%',
        background: checked ? '#00ff88' : '#526854',
        transform: checked ? 'translateX(22px)' : 'translateX(0)',
        transition: 'transform 0.16s',
      }} />
    </span>
  </button>
);

const NavButton: React.FC<{
  active: boolean;
  label: string;
  description: string;
  onClick: () => void;
}> = ({ active, label, description, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    style={{
      width: '100%',
      padding: '14px',
      background: active ? 'rgba(0, 165, 78, 0.15)' : 'rgba(0, 18, 8, 0.42)',
      border: `1px solid ${active ? '#00a85a' : '#0d4020'}`,
      borderLeft: `3px solid ${active ? '#00ff88' : '#1d5a2c'}`,
      color: active ? '#d8ffe3' : '#6fb47a',
      borderRadius: '3px',
      cursor: 'pointer',
      textAlign: 'left',
      fontFamily: "'SimHei', 'Microsoft YaHei', sans-serif",
    }}
  >
    <div style={{ fontSize: '14px', letterSpacing: '0.12em', marginBottom: '5px' }}>{label}</div>
    <div style={{ fontSize: '11px', color: active ? '#85d99a' : '#47744f', lineHeight: 1.45 }}>{description}</div>
  </button>
);

const getDecisionTone = (state: DecisionState) => {
  if (state === 'under') return { label: '欠信任', color: '#5ec8ff', bg: 'rgba(0, 42, 55, 0.72)', border: '#1ca8ff' };
  if (state === 'over') return { label: '过信任', color: '#ffb45c', bg: 'rgba(58, 28, 0, 0.72)', border: '#ff9f35' };
  return { label: '正常', color: '#00ff88', bg: 'rgba(0, 42, 18, 0.72)', border: '#1aa85a' };
};

const TrustStateSelect: React.FC<{
  label: string;
  value: ConfiguredTrustState;
  onChange: (value: ConfiguredTrustState) => void;
}> = ({ label, value, onChange }) => {
  const meta = configuredStateMeta(value);
  const tone = getDecisionTone(meta.state);
  return (
    <div style={{
      ...panelStyle,
      padding: '14px 16px',
      borderColor: tone.border,
      background: `linear-gradient(135deg, ${tone.bg}, rgba(1,14,6,0.9) 62%)`,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '14px', alignItems: 'center' }}>
        <div>
          <div style={{ color: '#d4ffe0', fontSize: '14px', letterSpacing: '0.08em', marginBottom: '4px' }}>{label}</div>
          <div style={fieldLabelStyle}>后台配置值，任务调控按该值执行</div>
        </div>
        <select
          value={value}
          onChange={event => onChange(event.target.value as ConfiguredTrustState)}
          style={{
            ...inputStyle,
            width: '128px',
            color: tone.color,
            borderColor: tone.border,
          }}
        >
          <option value="normal">信任适当</option>
          <option value="under_trust">欠信任</option>
          <option value="over_trust">过信任</option>
        </select>
      </div>
    </div>
  );
};

const DecisionBadge: React.FC<{
  state: DecisionState;
  reason: string;
}> = ({ state, reason }) => {
  const tone = getDecisionTone(state);
  return (
    <div style={{
      border: `1px solid ${tone.border}`,
      borderLeft: `4px solid ${tone.border}`,
      background: tone.bg,
      padding: '12px 14px',
      borderRadius: '4px',
    }}>
      <div style={{ color: tone.color, fontSize: '18px', fontWeight: 700, letterSpacing: '0.12em', marginBottom: '6px' }}>
        {tone.label}
      </div>
      <div style={{ color: '#d2ffe0', fontSize: '12px', lineHeight: 1.55 }}>{reason}</div>
    </div>
  );
};

const ScoreAxis: React.FC<{ score: number; compact?: boolean }> = ({ score, compact }) => {
  const marker = clamp((score + 100) / 200 * 100, 0, 100);
  const state = getScoreState(score);
  const tone = getDecisionTone(state);

  return (
    <div style={{ display: 'grid', gap: compact ? '6px' : '9px' }}>
      <div style={{
        position: 'relative',
        height: compact ? '32px' : '44px',
        border: '1px solid #24452b',
        borderRadius: '4px',
        overflow: 'hidden',
        display: 'grid',
        gridTemplateColumns: '35fr 30fr 35fr',
        boxShadow: 'inset 0 0 18px rgba(0,0,0,0.6)',
      }}>
        <div style={{ background: 'linear-gradient(90deg, rgba(255,159,53,0.62), rgba(255,159,53,0.18))' }} />
        <div style={{ background: 'linear-gradient(90deg, rgba(0,180,90,0.22), rgba(0,220,120,0.34), rgba(0,180,90,0.22))' }} />
        <div style={{ background: 'linear-gradient(90deg, rgba(45,216,255,0.18), rgba(45,216,255,0.6))' }} />
        <div style={{ position: 'absolute', left: '35%', top: 0, bottom: 0, width: '1px', background: 'rgba(255,255,255,0.45)' }} />
        <div style={{ position: 'absolute', left: '65%', top: 0, bottom: 0, width: '1px', background: 'rgba(255,255,255,0.45)' }} />
        <div style={{
          position: 'absolute',
          left: `${marker}%`,
          top: '-2px',
          bottom: '-2px',
          width: '3px',
          background: '#ffffff',
          boxShadow: `0 0 14px ${tone.color}`,
        }} />
        <div style={{
          position: 'absolute',
          left: `${marker}%`,
          top: compact ? '5px' : '9px',
          transform: 'translateX(-50%)',
          color: '#ffffff',
          fontSize: compact ? '11px' : '13px',
          fontFamily: "'Share Tech Mono', monospace",
          textShadow: '0 0 8px rgba(255,255,255,0.85)',
          whiteSpace: 'nowrap',
        }}>
          S {roundScore(score)}
        </div>
      </div>
      {!compact && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px', fontSize: '12px', lineHeight: 1.45 }}>
          <span style={{ color: '#ffbd73' }}>S ≤ -30：过信任</span>
          <span style={{ color: '#9effb5', textAlign: 'center' }}>-30 &lt; S &lt; 30：正常</span>
          <span style={{ color: '#7bdcff', textAlign: 'right' }}>S ≥ 30：欠信任</span>
        </div>
      )}
    </div>
  );
};

const FactorRow: React.FC<{ factor: ScoreFactor }> = ({ factor }) => {
  const tone = getDecisionTone(factor.direction === 'over' ? 'over' : 'under');
  const width = clamp(factor.score / factor.maxScore * 100, 0, 100);

  return (
    <div style={{ display: 'grid', gap: '5px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', alignItems: 'baseline' }}>
        <div style={{ color: factor.score > 0 ? tone.color : '#6fa878', fontSize: '12px', lineHeight: 1.35 }}>
          {factor.label}
        </div>
        <div style={{ color: factor.score > 0 ? tone.color : '#496f50', fontSize: '12px', fontFamily: "'Share Tech Mono', monospace", whiteSpace: 'nowrap' }}>
          {factor.direction === 'over' ? 'O' : 'U'} +{roundScore(factor.score)}
        </div>
      </div>
      <div style={{ height: '7px', border: '1px solid #213d28', background: 'rgba(0, 9, 3, 0.86)', borderRadius: '99px', overflow: 'hidden' }}>
        <div style={{
          width: `${width}%`,
          height: '100%',
          background: factor.score > 0 ? tone.color : '#24472b',
          boxShadow: factor.score > 0 ? `0 0 8px ${tone.color}` : undefined,
        }} />
      </div>
      <div style={{ color: '#6fa878', fontSize: '10px', lineHeight: 1.35 }}>{factor.reason}</div>
    </div>
  );
};

const ScoreBreakdownPanel: React.FC<{
  title: string;
  subtitle: string;
  breakdown: ScoreBreakdown;
  compact?: boolean;
}> = ({ title, subtitle, breakdown, compact }) => {
  const tone = getDecisionTone(breakdown.state);
  const visibleFactors = compact
    ? breakdown.factors.filter(factor => factor.score > 0).slice(0, 4)
    : breakdown.factors;

  return (
    <div style={{
      ...panelStyle,
      padding: compact ? '12px' : '16px',
      borderColor: tone.border,
      background: `linear-gradient(135deg, ${tone.bg}, rgba(1,14,6,0.9) 55%)`,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '14px', marginBottom: '12px' }}>
        <div>
          <div style={{ color: '#dfffea', fontSize: compact ? '14px' : '17px', letterSpacing: '0.08em', fontWeight: 700, marginBottom: '4px' }}>
            {title}
          </div>
          <div style={{ color: '#86c58f', fontSize: '11px', lineHeight: 1.55 }}>{subtitle}</div>
        </div>
        <div style={{ color: tone.color, border: `1px solid ${tone.border}`, background: tone.bg, borderRadius: '4px', padding: '6px 10px', fontSize: '13px', fontWeight: 700, whiteSpace: 'nowrap' }}>
          {tone.label}
        </div>
      </div>

      <ScoreAxis score={breakdown.score} compact={compact} />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginTop: '12px' }}>
        <div style={{ border: '1px solid rgba(255,159,53,0.4)', background: 'rgba(58,28,0,0.28)', padding: '8px 10px', borderRadius: '3px' }}>
          <div style={{ color: '#ffbd73', fontSize: '11px', letterSpacing: '0.08em' }}>过信任风险 O</div>
          <div style={{ color: '#ffe2bd', fontSize: compact ? '20px' : '26px', fontFamily: "'Share Tech Mono', monospace" }}>{roundScore(breakdown.overScore)}</div>
        </div>
        <div style={{ border: '1px solid rgba(45,216,255,0.4)', background: 'rgba(0,42,55,0.28)', padding: '8px 10px', borderRadius: '3px' }}>
          <div style={{ color: '#72e7ff', fontSize: '11px', letterSpacing: '0.08em' }}>欠信任风险 U</div>
          <div style={{ color: '#d5f8ff', fontSize: compact ? '20px' : '26px', fontFamily: "'Share Tech Mono', monospace" }}>{roundScore(breakdown.underScore)}</div>
        </div>
      </div>

      <div style={{ color: '#d2ffe0', fontSize: '12px', lineHeight: 1.55, marginTop: '10px' }}>{breakdown.summary}</div>

      {visibleFactors.length > 0 && (
        <div style={{ display: 'grid', gap: '10px', marginTop: '12px' }}>
          {visibleFactors.map(factor => <FactorRow key={factor.key} factor={factor} />)}
        </div>
      )}
    </div>
  );
};

const SimpleScorePanel: React.FC<{
  title: string;
  breakdown: ScoreBreakdown;
  primaryAction: string;
}> = ({ title, breakdown, primaryAction }) => {
  const tone = getDecisionTone(breakdown.state);
  const strongestOver = breakdown.factors
    .filter(factor => factor.direction === 'over')
    .sort((a, b) => b.score - a.score)[0];
  const strongestUnder = breakdown.factors
    .filter(factor => factor.direction === 'under')
    .sort((a, b) => b.score - a.score)[0];
  const mainFactor = breakdown.state === 'over' ? strongestOver : breakdown.state === 'under' ? strongestUnder : undefined;

  return (
    <div style={{
      ...panelStyle,
      padding: '18px',
      borderColor: tone.border,
      background: `linear-gradient(135deg, ${tone.bg}, rgba(1,14,6,0.92) 58%)`,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', alignItems: 'flex-start', marginBottom: '14px' }}>
        <div>
          <div style={{ color: '#86c58f', fontSize: '11px', letterSpacing: '0.18em', marginBottom: '5px' }}>{title}</div>
          <div style={{ color: tone.color, fontSize: '28px', fontWeight: 800, letterSpacing: '0.12em' }}>{tone.label}</div>
        </div>
        <div style={{ textAlign: 'right', fontFamily: "'Share Tech Mono', monospace" }}>
          <div style={{ color: '#6fa878', fontSize: '11px' }}>当前指数</div>
          <div style={{ color: '#ffffff', fontSize: '30px', textShadow: `0 0 12px ${tone.color}` }}>{roundScore(breakdown.score)}</div>
        </div>
      </div>

      <ScoreAxis score={breakdown.score} />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px', marginTop: '16px' }}>
        {[
          { label: '过信任', value: '≤ -30', state: 'over' as DecisionState },
          { label: '正常', value: '-30 ~ 30', state: 'normal' as DecisionState },
          { label: '欠信任', value: '≥ 30', state: 'under' as DecisionState },
        ].map(item => {
          const itemTone = getDecisionTone(item.state);
          const active = breakdown.state === item.state;
          return (
            <div key={item.label} style={{
              border: `1px solid ${active ? itemTone.border : '#1f4a2a'}`,
              background: active ? itemTone.bg : 'rgba(0,16,7,0.7)',
              padding: '10px',
              borderRadius: '4px',
              textAlign: 'center',
            }}>
              <div style={{ color: active ? itemTone.color : '#6fa878', fontSize: '13px', fontWeight: 700 }}>{item.label}</div>
              <div style={{ color: active ? '#ffffff' : '#497150', fontSize: '11px', marginTop: '4px', fontFamily: "'Share Tech Mono', monospace" }}>S {item.value}</div>
            </div>
          );
        })}
      </div>

      <div style={{ borderTop: '1px solid rgba(100,180,120,0.18)', marginTop: '16px', paddingTop: '12px' }}>
        <div style={{ color: '#dfffea', fontSize: '13px', lineHeight: 1.6 }}>
          {mainFactor && breakdown.state !== 'normal'
            ? `主要原因：${mainFactor.label}。${mainFactor.reason}`
            : '主要原因：当前过信任风险 O 和欠信任风险 U 相互抵消，落在正常区间。'}
        </div>
        <div style={{ color: tone.color, fontSize: '13px', lineHeight: 1.6, marginTop: '6px', fontWeight: 700 }}>
          建议动作：{primaryAction}
        </div>
      </div>
    </div>
  );
};

const MiniScoreCard: React.FC<{
  title: string;
  breakdown: ScoreBreakdown;
}> = ({ title, breakdown }) => {
  const tone = getDecisionTone(breakdown.state);
  const activeFactor = breakdown.factors
    .filter(factor => factor.score > 0)
    .sort((a, b) => b.score - a.score)[0];

  return (
    <div style={{
      border: `1px solid ${tone.border}`,
      borderLeft: `4px solid ${tone.border}`,
      background: tone.bg,
      padding: '12px',
      borderRadius: '4px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', alignItems: 'center' }}>
        <div>
          <div style={{ color: '#cdebd4', fontSize: '11px', marginBottom: '3px' }}>{title}</div>
          <div style={{ color: tone.color, fontSize: '20px', fontWeight: 800, letterSpacing: '0.1em' }}>{tone.label}</div>
        </div>
        <div style={{ color: '#ffffff', fontSize: '24px', fontFamily: "'Share Tech Mono', monospace" }}>S {roundScore(breakdown.score)}</div>
      </div>
      <div style={{ marginTop: '10px' }}>
        <ScoreAxis score={breakdown.score} compact />
      </div>
      <div style={{ color: '#d2ffe0', fontSize: '11px', lineHeight: 1.5, marginTop: '8px' }}>
        {activeFactor ? `主要原因：${activeFactor.label}` : '当前没有明显风险因子'}
      </div>
    </div>
  );
};

const DataCollectionNotice: React.FC<{
  history: TrustHistoryResponse | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}> = ({ history, loading, error, onRefresh }) => {
  const summary = history?.summary;
  const sampleCount = summary?.human_decision_count ?? 0;
  const minimumSampleSize = history?.minimum_sample_size ?? 30;
  const sampleSufficient = Boolean(history?.sample_sufficient);
  return (
  <div style={{
    ...panelStyle,
    padding: '16px',
    borderColor: sampleSufficient ? '#168842' : '#8a7518',
    background: sampleSufficient ? 'rgba(0, 46, 18, 0.52)' : 'rgba(46, 35, 0, 0.52)',
  }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'center', marginBottom: '8px' }}>
      <div style={{ color: sampleSufficient ? '#9effb5' : '#ffdf73', fontSize: '16px', fontWeight: 700, letterSpacing: '0.08em' }}>
      {loading ? '正在读取历史行为数据' : sampleSufficient ? '历史行为数据：可用于规则验证' : '历史行为数据：样本量不足'}
      </div>
      <button type="button" style={{ ...secondaryButtonStyle, height: '28px', padding: '0 10px', fontSize: '11px' }} onClick={onRefresh}>
        刷新
      </button>
    </div>
    <div style={{ color: '#e9ffef', fontSize: '12px', lineHeight: 1.65 }}>
      {error
        ? `读取失败：${error}`
        : `已采集人工决策样本 ${sampleCount} / ${minimumSampleSize}。当前筛选：${history?.filters?.user_id || '全部用户'}。AI 自动动作会进入历史日志，但不会计入人工接受/拒绝样本；历史数据只用于校准规则阈值。`}
    </div>
    {summary && (
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '10px' }}>
        {[
          `人工接受 ${formatCount(summary.human_accept_count)}`,
          `人工拒绝 ${formatCount(summary.human_reject_count)}`,
          `最大连续拒绝 ${formatCount(summary.max_consecutive_reject_count)}`,
          `无证据直接接受 ${formatCount(summary.direct_accept_without_evidence_count)}`,
          `查看证据 ${formatCount(summary.evidence_viewed_count)}`,
          `AI事件 ${formatCount(summary.ai_event_count)}`,
          `真值覆盖 ${typeof summary.truth_coverage === 'number' ? Math.round(summary.truth_coverage * 100) + '%' : '—'}`,
          `AI准确率 ${typeof summary.ai_accuracy === 'number' ? Math.round(summary.ai_accuracy * 100) + '%' : '—'}`,
          `不该拒 ${formatCount(summary.unwarranted_reject_count ?? 0)}`,
          `不该接 ${formatCount(summary.unwarranted_accept_count ?? 0)}`,
        ].map(label => (
          <span key={label} style={{
            border: '1px solid rgba(130,210,150,0.3)',
            background: 'rgba(0,18,8,0.55)',
            color: '#bdf5c8',
            padding: '5px 8px',
            borderRadius: '3px',
            fontSize: '11px',
          }}>
            {label}
          </span>
        ))}
      </div>
    )}
  </div>
  );
};

const BackendStateCard: React.FC<{
  sensorState: ConfiguredTrustState;
  threatState: ConfiguredTrustState;
}> = ({ sensorState, threatState }) => {
  const sensorMeta = configuredStateMeta(sensorState);
  const threatMeta = configuredStateMeta(threatState);
  const sensorTone = getDecisionTone(sensorMeta.state);
  const threatTone = getDecisionTone(threatMeta.state);
  return (
  <div style={{
    border: '1px solid rgba(0, 255, 136, 0.35)',
    background: 'rgba(0, 35, 16, 0.30)',
    borderRadius: '4px',
    padding: '14px 16px',
  }}>
    <div style={{ color: '#8dbb91', fontSize: '11px', letterSpacing: '0.12em', marginBottom: '8px' }}>后台状态配置</div>
    <div style={{ display: 'grid', gap: '8px' }}>
      {[
        ['传感器', sensorMeta.label, sensorTone],
        ['威胁排序', threatMeta.label, threatTone],
      ].map(([label, value, tone]) => {
        const itemTone = tone as ReturnType<typeof getDecisionTone>;
        return (
          <div key={label as string} style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', alignItems: 'center' }}>
            <span style={{ color: '#d8ffe3', fontSize: '12px' }}>{label as string}</span>
            <span style={{
              color: itemTone.color,
              border: `1px solid ${itemTone.border}`,
              background: itemTone.bg,
              padding: '4px 8px',
              borderRadius: '3px',
              fontSize: '12px',
              fontWeight: 700,
            }}>{value as string}</span>
          </div>
        );
      })}
    </div>
    <div style={{ color: '#d8ffe3', fontSize: '12px', lineHeight: 1.55 }}>
      前端按该配置执行解释、复核和拦截；历史数据只作为规则校准参考。
    </div>
  </div>
  );
};

const OverviewRuleCard: React.FC<{
  title: string;
  description: string;
  overText: string;
  underText: string;
  onConfigure: () => void;
}> = ({ title, description, overText, underText, onConfigure }) => (
  <div style={{ ...panelStyle, padding: '16px' }}>
    <div style={{ color: '#dfffea', fontSize: '17px', fontWeight: 700, letterSpacing: '0.08em', marginBottom: '6px' }}>{title}</div>
    <div style={{ color: '#86c58f', fontSize: '12px', lineHeight: 1.55, marginBottom: '14px' }}>{description}</div>
    <div style={{ display: 'grid', gap: '10px' }}>
      <div style={{ border: '1px solid rgba(255,159,53,0.55)', background: 'rgba(58,28,0,0.32)', padding: '11px 12px', borderRadius: '4px' }}>
        <div style={{ color: '#ffbd73', fontSize: '13px', fontWeight: 700, marginBottom: '4px' }}>可能进入过信任复核</div>
        <div style={{ color: '#e9ffef', fontSize: '12px', lineHeight: 1.5 }}>{overText}</div>
      </div>
      <div style={{ border: '1px solid rgba(45,216,255,0.55)', background: 'rgba(0,42,55,0.32)', padding: '11px 12px', borderRadius: '4px' }}>
        <div style={{ color: '#72e7ff', fontSize: '13px', fontWeight: 700, marginBottom: '4px' }}>可能进入欠信任解释</div>
        <div style={{ color: '#e9ffef', fontSize: '12px', lineHeight: 1.5 }}>{underText}</div>
      </div>
    </div>
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '14px' }}>
      <span style={{
        color: '#ffdf73',
        border: '1px solid rgba(255,223,115,0.55)',
        background: 'rgba(45,36,0,0.32)',
        padding: '7px 10px',
        borderRadius: '3px',
        fontSize: '12px',
        whiteSpace: 'nowrap',
      }}>
        行为数据：待采集
      </span>
      <button type="button" style={secondaryButtonStyle} onClick={onConfigure}>
        配置规则值
      </button>
    </div>
  </div>
);

const RuleConfigNotice: React.FC<{
  title: string;
  body: string;
}> = ({ title, body }) => (
  <div style={{
    ...panelStyle,
    padding: '16px',
    borderColor: '#8a7518',
    background: 'rgba(46, 35, 0, 0.45)',
  }}>
    <div style={{ color: '#ffdf73', fontSize: '16px', fontWeight: 700, marginBottom: '8px' }}>{title}</div>
    <div style={{ color: '#e9ffef', fontSize: '12px', lineHeight: 1.65 }}>{body}</div>
  </div>
);

const ExperimentStatusPanel: React.FC<{
  history: TrustHistoryResponse | null;
  config: TrustCalibrationConfig;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  onApplySensorThresholds: (patch: BehaviorThresholdPatch) => void;
  onApplyThreatThresholds: (patch: BehaviorThresholdPatch) => void;
}> = ({ history, config, loading, error, onRefresh, onApplySensorThresholds, onApplyThreatThresholds }) => {
  const summary = history?.summary;
  const sensorStats = history?.task_breakdown?.sensor;
  const threatStats = history?.task_breakdown?.threat;
  const minimumSampleSize = history?.minimum_sample_size ?? 30;
  const sampleCount = summary?.human_decision_count ?? 0;
  return (
  <div style={{ display: 'grid', gap: '14px' }}>
    <DataCollectionNotice history={history} loading={loading} error={error} onRefresh={onRefresh} />
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '14px' }}>
      {[
        ['实验样本', `${sampleCount} / ${minimumSampleSize}`, history?.sample_sufficient ? '已达到规则验证样本量' : '达到样本量后可辅助校准规则'],
        ['行为因子', summary ? `${summary.human_accept_count}/${summary.max_consecutive_reject_count}` : '待采集', '人工接受 / 最大连续拒绝'],
        ['证据查看', summary ? `${summary.evidence_viewed_count}` : '待采集', '用于区分直接接受与有证据接受'],
      ].map(([label, value, hint]) => (
        <div key={label} style={{ ...panelStyle, padding: '16px', borderColor: '#52652a', background: 'rgba(28, 32, 5, 0.46)' }}>
          <div style={{ color: '#86c58f', fontSize: '12px', letterSpacing: '0.12em', marginBottom: '10px' }}>{label}</div>
          <div style={{ color: '#ffdf73', fontSize: '24px', fontWeight: 800, marginBottom: '8px' }}>{value}</div>
          <div style={{ color: '#d8ffe3', fontSize: '12px', lineHeight: 1.5 }}>{hint}</div>
        </div>
      ))}
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '14px' }}>
      {[
        ['传感器任务', sensorStats],
        ['威胁排序任务', threatStats],
      ].map(([label, stats]) => {
        const taskStats = stats as TrustHistoryStats | undefined;
        return (
          <div key={label as string} style={{ ...panelStyle, padding: '16px' }}>
            <div style={{ color: '#dfffea', fontSize: '15px', fontWeight: 700, marginBottom: '12px' }}>{label as string}</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', color: '#bdf5c8', fontSize: '12px', lineHeight: 1.5 }}>
              <span>人工决策</span><span>{formatCount(taskStats?.human_decision_count)}</span>
              <span>无证据接受</span><span>{formatCount(taskStats?.direct_accept_without_evidence_count)}</span>
              <span>人工拒绝</span><span>{formatCount(taskStats?.human_reject_count)}</span>
              <span>最大连续拒绝</span><span>{formatCount(taskStats?.max_consecutive_reject_count)}</span>
              <span>平均确认时延</span><span>{formatLatency(taskStats?.average_confirmation_latency_ms)}</span>
              <span>最近事件</span><span>{formatEventTime(taskStats?.last_event_at)}</span>
            </div>
          </div>
        );
      })}
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '14px' }}>
      <HistoryRuleValidationPanel
        title="传感器历史规则验证"
        stats={sensorStats}
        directAcceptThreshold={config.sensor.direct_accept_threshold}
        rejectThreshold={config.sensor.consecutive_reject_threshold}
        latencyThresholdMs={config.sensor.latency_threshold_ms}
      />
      <HistoryRuleValidationPanel
        title="威胁排序历史规则验证"
        stats={threatStats}
        directAcceptThreshold={config.threat.direct_accept_threshold}
        rejectThreshold={config.threat.consecutive_reject_threshold}
        latencyThresholdMs={config.threat.latency_threshold_ms}
      />
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '14px' }}>
      <HistoryCalibrationSuggestionPanel
        title="传感器阈值校准建议"
        stats={sensorStats}
        config={config.sensor}
        sampleSufficient={Boolean(history?.sample_sufficient)}
        onApply={onApplySensorThresholds}
      />
      <HistoryCalibrationSuggestionPanel
        title="威胁排序阈值校准建议"
        stats={threatStats}
        config={config.threat}
        sampleSufficient={Boolean(history?.sample_sufficient)}
        onApply={onApplyThreatThresholds}
      />
    </div>
    <div style={{ ...panelStyle, padding: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', marginBottom: '10px' }}>
        <div style={{ color: '#dfffea', fontSize: '15px', fontWeight: 700 }}>最近信任事件</div>
        <div style={{ color: '#6fa878', fontSize: '11px' }}>显示最近 20 条</div>
      </div>
      <div style={{ display: 'grid', gap: '6px' }}>
        {(history?.recent_events?.length ?? 0) === 0 ? (
          <div style={{ color: '#86c58f', fontSize: '12px' }}>暂无历史信任事件。</div>
        ) : history?.recent_events.map((event, index) => (
          <div key={`${event.timestamp}-${event.eventType}-${index}`} style={{
            display: 'grid',
            gridTemplateColumns: '80px 96px 1fr 120px',
            gap: '10px',
            padding: '8px 10px',
            border: '1px solid rgba(80,170,100,0.16)',
            background: 'rgba(0,12,5,0.55)',
            color: '#cdebd4',
            fontSize: '11px',
            alignItems: 'center',
          }}>
            <span style={{ color: event.actor === 'ai' ? '#7bdcff' : '#ffdf73' }}>{event.actor === 'ai' ? 'AI' : '人工'}</span>
            <span>{event.task === 'sensor' ? '传感器' : event.task === 'threat' ? '威胁排序' : '未知任务'}</span>
            <span>{eventTypeLabel(event.eventType)} · {event.recommendationId ?? '-'}</span>
            <span style={{ color: '#6fa878' }}>{formatEventTime(event.timestamp)}</span>
          </div>
        ))}
      </div>
    </div>
  </div>
  );
};

const ScenarioButton: React.FC<{
  state: DecisionState;
  label: string;
  onClick: () => void;
}> = ({ state, label, onClick }) => {
  const tone = getDecisionTone(state);
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        height: '30px',
        padding: '0 10px',
        border: `1px solid ${tone.border}`,
        background: tone.bg,
        color: tone.color,
        borderRadius: '3px',
        cursor: 'pointer',
        fontFamily: "'SimHei', 'Microsoft YaHei', sans-serif",
        fontSize: '12px',
        letterSpacing: '0.06em',
      }}
    >
      {label}
    </button>
  );
};

const ConditionChip: React.FC<{
  label: string;
  active: boolean;
  state: DecisionState;
}> = ({ label, active, state }) => {
  const tone = getDecisionTone(state);
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '6px',
      padding: '6px 9px',
      borderRadius: '3px',
      border: `1px solid ${active ? tone.border : '#245331'}`,
      background: active ? tone.bg : 'rgba(0, 18, 8, 0.72)',
      color: active ? tone.color : '#6fa878',
      fontSize: '12px',
      lineHeight: 1.35,
    }}>
      <span style={{
        width: '6px',
        height: '6px',
        borderRadius: '50%',
        background: active ? tone.color : '#315c38',
        boxShadow: active ? `0 0 8px ${tone.color}` : undefined,
      }} />
      {label}
    </span>
  );
};

const LogicCard: React.FC<{
  state: DecisionState;
  title: string;
  summary: string;
  chips: Array<{ label: string; active: boolean }>;
}> = ({ state, title, summary, chips }) => {
  const tone = getDecisionTone(state);
  const activeCount = chips.filter(chip => chip.active).length;
  return (
    <div style={{
      border: `1px solid ${activeCount > 0 ? tone.border : '#0d4020'}`,
      borderLeft: `4px solid ${tone.border}`,
      background: activeCount > 0 ? tone.bg : 'rgba(1, 14, 6, 0.82)',
      borderRadius: '4px',
      padding: '14px 16px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'center', marginBottom: '8px' }}>
        <div style={{ color: tone.color, fontSize: '16px', fontWeight: 700, letterSpacing: '0.08em' }}>{title}</div>
        <div style={{
          color: activeCount > 0 ? tone.color : '#6fa878',
          border: `1px solid ${activeCount > 0 ? tone.border : '#245331'}`,
          padding: '3px 8px',
          borderRadius: '999px',
          fontSize: '11px',
        }}>
          {activeCount > 0 ? '当前命中' : '当前未命中'}
        </div>
      </div>
      <div style={{ color: '#d2ffe0', fontSize: '12px', lineHeight: 1.55, marginBottom: '10px' }}>{summary}</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
        {chips.map(chip => (
          <ConditionChip key={chip.label} label={chip.label} active={chip.active} state={state} />
        ))}
      </div>
    </div>
  );
};

const ThresholdBand: React.FC<{
  title: string;
  leftLabel: string;
  middleLabel: string;
  rightLabel: string;
  leftColor: string;
  middleColor: string;
  rightColor: string;
  markerPercent?: number;
  markerLabel?: string;
}> = ({ title, leftLabel, middleLabel, rightLabel, leftColor, middleColor, rightColor, markerPercent, markerLabel }) => (
  <div style={{ ...panelStyle, padding: '14px 16px' }}>
    <div style={{ color: '#d4ffe0', fontSize: '14px', letterSpacing: '0.08em', marginBottom: '10px' }}>{title}</div>
    <div style={{ position: 'relative', height: '34px', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', border: '1px solid #183f22', borderRadius: '3px', overflow: 'hidden' }}>
      {[leftColor, middleColor, rightColor].map((color, index) => (
        <div key={index} style={{ background: color, borderRight: index < 2 ? '1px solid rgba(0,0,0,0.45)' : undefined }} />
      ))}
      {typeof markerPercent === 'number' && (
        <div style={{
          position: 'absolute',
          left: `${Math.max(0, Math.min(100, markerPercent))}%`,
          top: 0,
          bottom: 0,
          width: '2px',
          background: '#ffffff',
          boxShadow: '0 0 10px rgba(255,255,255,0.8)',
        }} />
      )}
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '6px', marginTop: '8px', fontSize: '11px', lineHeight: 1.4 }}>
      <span style={{ color: '#ffbf74' }}>{leftLabel}</span>
      <span style={{ color: '#9effb5', textAlign: 'center' }}>{middleLabel}</span>
      <span style={{ color: '#7bdcff', textAlign: 'right' }}>{rightLabel}</span>
    </div>
    {markerLabel && <div style={{ color: '#cdebd4', fontSize: '11px', marginTop: '8px' }}>当前模拟：{markerLabel}</div>}
  </div>
);

const ConfidenceAxis: React.FC<{
  lowMin: number;
  lowMax: number;
  high: number;
  sample: number;
  onLowMinChange: (value: number) => void;
  onLowMaxChange: (value: number) => void;
  onHighChange: (value: number) => void;
}> = ({ lowMin, lowMax, high, sample, onLowMinChange, onLowMaxChange, onHighChange }) => {
  const overWidth = Math.max(0, lowMax) * 100;
  const normalWidth = Math.max(0, high - lowMax) * 100;
  const highWidth = Math.max(0, 1 - high) * 100;
  const marker = Math.max(0, Math.min(100, sample * 100));
  const state: DecisionState = sample <= lowMax ? 'over' : sample >= high ? 'under' : 'normal';
  const tone = getDecisionTone(state);

  return (
    <div style={{ ...panelStyle, padding: '18px', borderColor: '#168842' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '20px', alignItems: 'flex-start', marginBottom: '16px' }}>
        <div>
          <div style={{ color: '#dfffea', fontSize: '19px', fontWeight: 700, letterSpacing: '0.1em', marginBottom: '6px' }}>
            AI 置信度调控轴
          </div>
          <div style={{ color: '#86c58f', fontSize: '12px', lineHeight: 1.6 }}>
            只调这一条轴：低置信进入复核，高置信但超时未采纳进入解释。
          </div>
        </div>
        <div style={{
          border: `1px solid ${tone.border}`,
          color: tone.color,
          background: tone.bg,
          borderRadius: '4px',
          padding: '8px 12px',
          minWidth: '112px',
          textAlign: 'center',
        }}>
          <div style={{ fontSize: '11px', color: '#cdebd4', marginBottom: '2px' }}>当前样例</div>
          <div style={{ fontSize: '18px', fontWeight: 700 }}>{tone.label}</div>
        </div>
      </div>

      <div style={{
        position: 'relative',
        height: '46px',
        display: 'flex',
        border: '1px solid #24452b',
        borderRadius: '4px',
        overflow: 'hidden',
        boxShadow: 'inset 0 0 18px rgba(0,0,0,0.55)',
      }}>
        <div style={{ width: `${overWidth}%`, background: 'linear-gradient(90deg, rgba(255,159,53,0.55), rgba(255,159,53,0.32))' }} />
        <div style={{ width: `${normalWidth}%`, background: 'linear-gradient(90deg, rgba(0,190,90,0.24), rgba(0,220,120,0.32))' }} />
        <div style={{ width: `${highWidth}%`, background: 'linear-gradient(90deg, rgba(45,216,255,0.25), rgba(45,216,255,0.5))' }} />
        <div style={{ position: 'absolute', left: `${marker}%`, top: 0, bottom: 0, width: '3px', background: '#ffffff', boxShadow: '0 0 12px #ffffff' }} />
        {[
          { value: lowMin, label: `${Math.round(lowMin * 100)}%` },
          { value: lowMax, label: `${Math.round(lowMax * 100)}%` },
          { value: high, label: `${Math.round(high * 100)}%` },
        ].map(item => (
          <div key={item.label} style={{ position: 'absolute', left: `${item.value * 100}%`, top: 0, bottom: 0, width: '1px', background: 'rgba(255,255,255,0.45)' }}>
            <span style={{ position: 'absolute', top: '4px', transform: 'translateX(-50%)', color: '#eaffef', fontSize: '11px' }}>{item.label}</span>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px', marginTop: '10px', fontSize: '12px', lineHeight: 1.5 }}>
        <div style={{ color: '#ffbd73' }}>≤ {Math.round(lowMax * 100)}%：过信任复核</div>
        <div style={{ color: '#9effb5', textAlign: 'center' }}>{Math.round(lowMax * 100)}%-{Math.round(high * 100)}%：正常参考</div>
        <div style={{ color: '#7bdcff', textAlign: 'right' }}>≥ {Math.round(high * 100)}%：高可信，超时未采纳则解释</div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '12px', marginTop: '18px' }}>
        <RangeField label="低可信起点" hint="文档建议低置信范围从 60% 开始" value={lowMin} min={0.3} max={0.8} step={0.01} onChange={onLowMinChange} />
        <RangeField label="复核上限" hint="低于/等于该值时要求人工复核" value={lowMax} min={0.4} max={0.9} step={0.01} highlight={sample <= lowMax ? 'over' : undefined} onChange={onLowMaxChange} />
        <RangeField label="高可信起点" hint="达到该值且超时未确认时展开解释" value={high} min={0.6} max={1} step={0.01} highlight={sample >= high ? 'under' : undefined} onChange={onHighChange} />
      </div>
    </div>
  );
};

const RuleModelCard: React.FC = () => (
  <div style={{ ...panelStyle, padding: '16px', borderColor: '#176a8a', background: 'rgba(0, 24, 20, 0.76)' }}>
    <div style={{ color: '#5ec8ff', fontSize: '13px', letterSpacing: '0.14em', marginBottom: '10px' }}>判定模型：两套规则，不是一条轴</div>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
      <div style={{ border: '1px solid #176a8a', borderLeft: '3px solid #2dd8ff', padding: '12px', background: 'rgba(0, 42, 55, 0.45)' }}>
        <div style={{ color: '#72e7ff', fontSize: '15px', fontWeight: 700, marginBottom: '8px' }}>欠信任</div>
        <div style={{ color: '#d6ffe4', fontSize: '12px', lineHeight: 1.7 }}>
          AI 建议较可靠，但操作者迟迟不采纳或连续拒绝。<br />
          关注的是：<span style={{ color: '#ffffff' }}>“该信 AI 的时候没有信”</span>
        </div>
      </div>
      <div style={{ border: '1px solid #9a641a', borderLeft: '3px solid #ff9f35', padding: '12px', background: 'rgba(58, 28, 0, 0.5)' }}>
        <div style={{ color: '#ffbd73', fontSize: '15px', fontWeight: 700, marginBottom: '8px' }}>过信任</div>
        <div style={{ color: '#ffe4bd', fontSize: '12px', lineHeight: 1.7 }}>
          AI 建议证据不足、候选接近或数据不稳定，但操作者可能直接接受。<br />
          关注的是：<span style={{ color: '#ffffff' }}>“不该直接信的时候信得太快”</span>
        </div>
      </div>
    </div>
  </div>
);

const RuleMatrix: React.FC<{ config: TrustCalibrationConfig }> = ({ config }) => {
  const rows = [
    {
      task: '传感器',
      state: '欠信任',
      tone: getDecisionTone('under'),
      rule: '高置信推荐超时未确认',
      condition: `置信度 ≥ ${config.sensor.high_confidence} 且未确认时间 ≥ ${config.sensor.unconfirmed_timeout_ms}ms`,
      field: 'sensor.high_confidence / sensor.unconfirmed_timeout_ms',
    },
    {
      task: '传感器',
      state: '欠信任',
      tone: getDecisionTone('under'),
      rule: '连续拒绝 AI 推荐',
      condition: `连续拒绝次数 ≥ ${config.sensor.consecutive_reject_threshold}`,
      field: 'sensor.consecutive_reject_threshold',
    },
    {
      task: '传感器',
      state: '过信任',
      tone: getDecisionTone('over'),
      rule: 'AI 推荐置信度偏低',
      condition: `置信度 ≤ ${config.sensor.low_confidence_max}`,
      field: 'sensor.low_confidence_max',
    },
    {
      task: '传感器',
      state: '过信任',
      tone: getDecisionTone('over'),
      rule: '候选目标过近',
      condition: `第一/第二候选差距 < ${config.sensor.candidate_gap_threshold}`,
      field: 'sensor.candidate_gap_threshold',
    },
    {
      task: '传感器',
      state: '过信任',
      tone: getDecisionTone('over'),
      rule: 'IFF 未确认',
      condition: 'IFF 未开启或未确认时，不允许直接形成最终敌我判断',
      field: '运行态：iffMode',
    },
    {
      task: '传感器',
      state: '过信任',
      tone: getDecisionTone('over'),
      rule: '连续直接接受但未看证据',
      condition: `直接接受次数 ≥ ${config.sensor.direct_accept_threshold} 且未查看证据`,
      field: 'sensor.direct_accept_threshold',
    },
    {
      task: '威胁排序',
      state: '欠信任',
      tone: getDecisionTone('under'),
      rule: '最高威胁发生变化',
      condition: '前一轮最高威胁和当前最高威胁不同',
      field: '运行态：previousTopThreatId',
    },
    {
      task: '威胁排序',
      state: '欠信任',
      tone: getDecisionTone('under'),
      rule: '排序长时间未确认',
      condition: `未确认时间 ≥ ${config.threat.unconfirmed_timeout_ms}ms`,
      field: 'threat.unconfirmed_timeout_ms',
    },
    {
      task: '威胁排序',
      state: '欠信任',
      tone: getDecisionTone('under'),
      rule: '连续拒绝 AI 排序',
      condition: `连续拒绝次数 ≥ ${config.threat.consecutive_reject_threshold}`,
      field: 'threat.consecutive_reject_threshold',
    },
    {
      task: '威胁排序',
      state: '过信任',
      tone: getDecisionTone('over'),
      rule: '第一/第二威胁分差过小',
      condition: `分差 < ${config.threat.score_gap_threshold}`,
      field: 'threat.score_gap_threshold',
    },
    {
      task: '威胁排序',
      state: '过信任',
      tone: getDecisionTone('over'),
      rule: '数据延迟过高',
      condition: `数据延迟 > ${config.threat.data_delay_ms}ms`,
      field: 'threat.data_delay_ms',
    },
    {
      task: '威胁排序',
      state: '过信任',
      tone: getDecisionTone('over'),
      rule: '直接查看结果但未看证据',
      condition: `直接接受次数 ≥ ${config.threat.direct_accept_threshold} 且未查看证据`,
      field: 'threat.direct_accept_threshold',
    },
  ];

  return (
    <div style={{ ...panelStyle, padding: '16px' }}>
      <div style={{ color: '#d4ffe0', fontSize: '15px', letterSpacing: '0.1em', marginBottom: '12px' }}>完整规则清单</div>
      <div style={{ display: 'grid', gridTemplateColumns: '92px 72px 150px 1fr 220px', gap: '1px', background: '#0d4020', border: '1px solid #0d4020', overflow: 'hidden', borderRadius: '3px' }}>
        {['任务', '状态', '规则', '触发条件', '配置字段'].map(label => (
          <div key={label} style={{ background: '#06200d', color: '#8eeaa2', fontSize: '11px', letterSpacing: '0.08em', padding: '8px' }}>{label}</div>
        ))}
        {rows.map((row, index) => (
          <React.Fragment key={`${row.task}-${row.rule}`}>
            <div style={{ background: 'rgba(0, 14, 5, 0.94)', color: '#9effb5', fontSize: '12px', padding: '9px 8px' }}>{row.task}</div>
            <div style={{ background: row.tone.bg, color: row.tone.color, fontSize: '12px', padding: '9px 8px', fontWeight: 700 }}>{row.state}</div>
            <div style={{ background: 'rgba(0, 14, 5, 0.94)', color: '#e5ffea', fontSize: '12px', padding: '9px 8px' }}>{row.rule}</div>
            <div style={{ background: 'rgba(0, 14, 5, 0.94)', color: '#bdddc4', fontSize: '12px', padding: '9px 8px', lineHeight: 1.45 }}>{row.condition}</div>
            <div style={{ background: 'rgba(0, 14, 5, 0.94)', color: '#74d68b', fontSize: '11px', padding: '9px 8px', fontFamily: "'Share Tech Mono', monospace" }}>{row.field}</div>
          </React.Fragment>
        ))}
      </div>
      <div style={{ color: '#6fa878', fontSize: '11px', marginTop: '10px', lineHeight: 1.5 }}>
        注：右侧模拟器只演示最常见、最容易理解的阈值规则；运行态规则如 IFF、连续拒绝、最高威胁变化会在真实任务交互中触发。
      </div>
    </div>
  );
};

const TrustCalibrationSettings: React.FC<TrustCalibrationSettingsProps> = observer(({ onClose, connected = false, currentUserId = '', sendMessage }) => {
  const serverConfig = useMemo(
    () => mergeTrustCalibrationConfig(agentStore.trustCalibrationConfig),
    [agentStore.trustCalibrationConfig],
  );
  const [draft, setDraft] = useState<TrustCalibrationConfig>(() => cloneConfig(serverConfig));
  const [section, setSection] = useState<SectionKey>('overview');
  const [copied, setCopied] = useState(false);
  const [simSensorConfidence, setSimSensorConfidence] = useState(0.65);
  const [simSensorAgeMs, setSimSensorAgeMs] = useState(6000);
  const [simSensorGap, setSimSensorGap] = useState(0.08);
  const [simThreatGap, setSimThreatGap] = useState(0.06);
  const [simThreatDelayMs, setSimThreatDelayMs] = useState(2200);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const [lastAppliedAt, setLastAppliedAt] = useState<number | null>(null);
  const [history, setHistory] = useState<TrustHistoryResponse | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const loadTrustHistory = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const params = new URLSearchParams({
        limit: '500',
        minimum_sample_size: '30',
      });
      if (currentUserId.trim()) {
        params.set('user_id', currentUserId.trim());
      }
      const response = await fetch(`/api/trust-history?${params.toString()}`, { cache: 'no-store' });
      const data = await response.json() as TrustHistoryResponse;
      if (!response.ok || data.ok === false) {
        throw new Error(data.msg || `HTTP ${response.status}`);
      }
      setHistory(data);
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : '无法读取历史行为数据');
    } finally {
      setHistoryLoading(false);
    }
  }, [currentUserId]);

  useEffect(() => {
    loadTrustHistory();
  }, [loadTrustHistory]);

  const setEnabled = (enabled: boolean) => setDraft(prev => ({ ...prev, enabled }));
  const updateConfiguredState = (task: keyof TrustCalibrationConfig['state'], value: ConfiguredTrustState) => {
    setDraft(prev => ({ ...prev, state: { ...prev.state, [task]: value } }));
  };
  const updateSensor = <K extends keyof TrustCalibrationConfig['sensor']>(key: K, value: TrustCalibrationConfig['sensor'][K]) => {
    setDraft(prev => ({ ...prev, sensor: { ...prev.sensor, [key]: value } }));
  };
  const updateThreat = <K extends keyof TrustCalibrationConfig['threat']>(key: K, value: TrustCalibrationConfig['threat'][K]) => {
    setDraft(prev => ({ ...prev, threat: { ...prev.threat, [key]: value } }));
  };
  const updateDisplay = <K extends keyof TrustCalibrationConfig['display']>(key: K, value: TrustCalibrationConfig['display'][K]) => {
    setDraft(prev => ({ ...prev, display: { ...prev.display, [key]: value } }));
  };
  const applySensorThresholdPatch = useCallback((patch: BehaviorThresholdPatch) => {
    setDraft(prev => ({ ...prev, sensor: { ...prev.sensor, ...patch } }));
  }, []);
  const applyThreatThresholdPatch = useCallback((patch: BehaviorThresholdPatch) => {
    setDraft(prev => ({ ...prev, threat: { ...prev.threat, ...patch } }));
  }, []);

  const applyDraft = () => {
    const nextConfig = cloneConfig(draft);
    agentStore.setTrustCalibrationConfig(nextConfig);
    if (connected && sendMessage) {
      sendMessage({
        type: 'config_update',
        trust_calibration: nextConfig,
        timestamp: Date.now(),
      });
      setSaveStatus('sent');
    } else {
      setSaveStatus('local');
    }
    setLastAppliedAt(Date.now());
  };

  const resetDraft = () => {
    setDraft(cloneConfig(DEFAULT_TRUST_CALIBRATION_CONFIG));
    setSaveStatus('idle');
  };

  const copyJson = async () => {
    const json = JSON.stringify({ trust_calibration: draft }, null, 2);
    await navigator.clipboard?.writeText(json);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  };

  const sensorBreakdown = useMemo<ScoreBreakdown>(() => {
    const lowConfidenceScore = clamp((draft.sensor.low_confidence_max - simSensorConfidence) / Math.max(0.01, draft.sensor.low_confidence_max) * 35, 0, 35);
    const candidateGapScore = clamp((draft.sensor.candidate_gap_threshold - simSensorGap) / Math.max(0.01, draft.sensor.candidate_gap_threshold) * 20, 0, 20);
    const highConfidenceBase = clamp((simSensorConfidence - draft.sensor.high_confidence) / Math.max(0.01, 1 - draft.sensor.high_confidence) * 20, 0, 20);
    const highConfidenceTimeoutScore = simSensorConfidence >= draft.sensor.high_confidence
      ? clamp(simSensorAgeMs / Math.max(1, draft.sensor.unconfirmed_timeout_ms) * 15, 0, 15)
      : 0;

    const factors: ScoreFactor[] = [
      {
        key: 'sensor-low-confidence',
        label: '低置信风险',
        direction: 'over',
        score: lowConfidenceScore,
        maxScore: 35,
        reason: `AI 置信度 ${simSensorConfidence.toFixed(2)}；低置信上限 ${draft.sensor.low_confidence_max}`,
      },
      {
        key: 'sensor-candidate-gap',
        label: '候选接近风险',
        direction: 'over',
        score: candidateGapScore,
        maxScore: 20,
        reason: `候选差距 ${simSensorGap.toFixed(2)}；阈值 ${draft.sensor.candidate_gap_threshold}`,
      },
      {
        key: 'sensor-iff',
        label: 'IFF 未确认风险',
        direction: 'over',
        score: 0,
        maxScore: 20,
        reason: '运行态输入：真实任务中 IFF 未确认时给 O 加分',
      },
      {
        key: 'sensor-direct-accept',
        label: '未看证据直接接受',
        direction: 'over',
        score: 0,
        maxScore: 20,
        reason: `运行态输入：直接接受达到 ${draft.sensor.direct_accept_threshold} 次时给 O 加分`,
      },
      {
        key: 'sensor-high-confidence',
        label: '高可靠 AI 证据',
        direction: 'under',
        score: highConfidenceBase,
        maxScore: 20,
        reason: `AI 置信度 ${simSensorConfidence.toFixed(2)}；高置信起点 ${draft.sensor.high_confidence}`,
      },
      {
        key: 'sensor-unconfirmed-timeout',
        label: '高置信未采纳',
        direction: 'under',
        score: highConfidenceTimeoutScore,
        maxScore: 15,
        reason: `未确认 ${simSensorAgeMs}ms；阈值 ${draft.sensor.unconfirmed_timeout_ms}ms`,
      },
      {
        key: 'sensor-reject',
        label: '连续拒绝 AI',
        direction: 'under',
        score: 0,
        maxScore: 20,
        reason: `运行态输入：连续拒绝达到 ${draft.sensor.consecutive_reject_threshold} 次时给 U 加分`,
      },
    ];

    const overScore = factors.filter(factor => factor.direction === 'over').reduce((total, factor) => total + factor.score, 0);
    const underScore = factors.filter(factor => factor.direction === 'under').reduce((total, factor) => total + factor.score, 0);
    const score = underScore - overScore;
    return {
      state: getScoreState(score),
      score,
      overScore,
      underScore,
      factors,
      summary: scoreReason(score),
    };
  }, [draft.sensor, simSensorAgeMs, simSensorConfidence, simSensorGap]);

  const threatBreakdown = useMemo<ScoreBreakdown>(() => {
    const gapScore = clamp((draft.threat.score_gap_threshold - simThreatGap) / Math.max(0.01, draft.threat.score_gap_threshold) * 35, 0, 35);
    const delayScore = clamp((simThreatDelayMs - draft.threat.data_delay_ms) / Math.max(1, draft.threat.data_delay_ms) * 25, 0, 25);
    const timeoutScore = clamp((simThreatDelayMs - draft.threat.unconfirmed_timeout_ms) / Math.max(1, draft.threat.unconfirmed_timeout_ms) * 25, 0, 25);

    const factors: ScoreFactor[] = [
      {
        key: 'threat-score-gap',
        label: '第一/第二分差过小',
        direction: 'over',
        score: gapScore,
        maxScore: 35,
        reason: `排序分差 ${simThreatGap.toFixed(2)}；阈值 ${draft.threat.score_gap_threshold}`,
      },
      {
        key: 'threat-data-delay',
        label: '数据延迟风险',
        direction: 'over',
        score: delayScore,
        maxScore: 25,
        reason: `数据延迟 ${simThreatDelayMs}ms；阈值 ${draft.threat.data_delay_ms}ms`,
      },
      {
        key: 'threat-direct-submit',
        label: '未看证据直接查看结果',
        direction: 'over',
        score: 0,
        maxScore: 20,
        reason: `运行态输入：直接查看达到 ${draft.threat.direct_accept_threshold} 次时给 O 加分`,
      },
      {
        key: 'threat-top-change',
        label: '排序变化未理解',
        direction: 'under',
        score: 0,
        maxScore: 25,
        reason: '运行态输入：临机事件导致最高威胁变化时给 U 加分',
      },
      {
        key: 'threat-unconfirmed-timeout',
        label: '排序长时间未确认',
        direction: 'under',
        score: timeoutScore,
        maxScore: 25,
        reason: `未确认 ${simThreatDelayMs}ms；阈值 ${draft.threat.unconfirmed_timeout_ms}ms`,
      },
      {
        key: 'threat-reject',
        label: '连续拒绝 AI 排序',
        direction: 'under',
        score: 0,
        maxScore: 20,
        reason: `运行态输入：连续拒绝达到 ${draft.threat.consecutive_reject_threshold} 次时给 U 加分`,
      },
    ];

    const overScore = factors.filter(factor => factor.direction === 'over').reduce((total, factor) => total + factor.score, 0);
    const underScore = factors.filter(factor => factor.direction === 'under').reduce((total, factor) => total + factor.score, 0);
    const score = underScore - overScore;
    return {
      state: getScoreState(score),
      score,
      overScore,
      underScore,
      factors,
      summary: scoreReason(score),
    };
  }, [draft.threat, simThreatDelayMs, simThreatGap]);

  const sensorLowConfidenceHit = simSensorConfidence <= draft.sensor.low_confidence_max;
  const sensorCandidateGapHit = simSensorGap < draft.sensor.candidate_gap_threshold;
  const sensorHighConfidenceHit = simSensorConfidence >= draft.sensor.high_confidence && simSensorAgeMs >= draft.sensor.unconfirmed_timeout_ms;
  const threatGapHit = simThreatGap < draft.threat.score_gap_threshold;
  const threatDelayHit = simThreatDelayMs > draft.threat.data_delay_ms;
  const threatTimeoutHit = simThreatDelayMs >= draft.threat.unconfirmed_timeout_ms;
  const historySummary = history?.summary;
  const historySampleCount = historySummary?.human_decision_count ?? 0;
  const historyMinimumSampleSize = history?.minimum_sample_size ?? 30;

  const setSensorScenario = (target: DecisionState) => {
    if (target === 'over') {
      setSimSensorConfidence(Math.max(0, Number((draft.sensor.low_confidence_max - 0.05).toFixed(2))));
      setSimSensorGap(Math.max(0, Number((draft.sensor.candidate_gap_threshold - 0.02).toFixed(2))));
      setSimSensorAgeMs(Math.max(0, draft.sensor.unconfirmed_timeout_ms - 1000));
      setSection('sensor');
      return;
    }
    if (target === 'under') {
      setSimSensorConfidence(Math.min(1, Number((draft.sensor.high_confidence + 0.03).toFixed(2))));
      setSimSensorGap(Math.min(0.5, Number((draft.sensor.candidate_gap_threshold + 0.08).toFixed(2))));
      setSimSensorAgeMs(draft.sensor.unconfirmed_timeout_ms + 1000);
      setSection('sensor');
      return;
    }
    setSimSensorConfidence(Number(((draft.sensor.low_confidence_max + draft.sensor.high_confidence) / 2).toFixed(2)));
    setSimSensorGap(Math.min(0.5, Number((draft.sensor.candidate_gap_threshold + 0.08).toFixed(2))));
    setSimSensorAgeMs(Math.max(0, draft.sensor.unconfirmed_timeout_ms - 1000));
    setSection('sensor');
  };

  const setThreatScenario = (target: DecisionState) => {
    if (target === 'over') {
      setSimThreatGap(Math.max(0, Number((draft.threat.score_gap_threshold - 0.03).toFixed(2))));
      setSimThreatDelayMs(draft.threat.data_delay_ms + 500);
      setSection('threat');
      return;
    }
    if (target === 'under') {
      setSimThreatGap(Math.min(0.5, Number((draft.threat.score_gap_threshold + 0.12).toFixed(2))));
      setSimThreatDelayMs(draft.threat.unconfirmed_timeout_ms + 500);
      setSection('threat');
      return;
    }
    setSimThreatGap(Math.min(0.5, Number((draft.threat.score_gap_threshold + 0.12).toFixed(2))));
    setSimThreatDelayMs(Math.max(0, Math.min(draft.threat.data_delay_ms - 200, draft.threat.unconfirmed_timeout_ms - 1000)));
    setSection('threat');
  };

  const renderOverview = () => (
    <div style={{ display: 'grid', gap: '14px' }}>
      <ToggleField
        label="启用信任调控"
        hint="关闭后所有解释、复核和拦截门槛都不生效"
        checked={draft.enabled}
        onChange={setEnabled}
      />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '14px' }}>
        <TrustStateSelect label="传感器后台状态" value={draft.state.sensor} onChange={value => updateConfiguredState('sensor', value)} />
        <TrustStateSelect label="威胁排序后台状态" value={draft.state.threat} onChange={value => updateConfiguredState('threat', value)} />
      </div>
      <DataCollectionNotice
        history={history}
        loading={historyLoading}
        error={historyError}
        onRefresh={loadTrustHistory}
      />
      <div style={{ ...panelStyle, padding: '18px', borderColor: '#176a8a', background: 'rgba(0, 24, 20, 0.76)' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 240px', gap: '18px', alignItems: 'center' }}>
          <div>
            <div style={{ color: '#5ec8ff', fontSize: '13px', letterSpacing: '0.14em', marginBottom: '8px' }}>规则预览分数</div>
            <div style={{ color: '#dfffea', fontSize: '22px', letterSpacing: '0.08em', marginBottom: '10px' }}>
              S = 欠信任风险 - 过信任风险
            </div>
            <div style={{ color: '#cdebd4', fontSize: '12px', lineHeight: 1.7 }}>
              S 往左是过信任复核区，往右是欠信任解释区；这里只演示规则阈值，不展示当前用户状态。
            </div>
          </div>
          <BackendStateCard sensorState={draft.state.sensor} threatState={draft.state.threat} />
        </div>
        <div style={{ marginTop: '18px' }}>
          <ScoreAxis score={0} />
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '14px' }}>
        <OverviewRuleCard
          title="传感器任务：规则预览"
          description="目标识别里的置信度、候选差距和 IFF 复核。"
          overText="低置信、候选接近、IFF 未确认时，先查看证据或人工复核。"
          underText="高置信但超时未采纳、连续拒绝时，展开 AI 推荐依据。"
          onConfigure={() => setSection('sensor')}
        />
        <OverviewRuleCard
          title="威胁排序任务：规则预览"
          description="排序分差、数据延迟和查看结果前的复核门槛。"
          overText="第一/第二分差小、数据延迟或直接查看结果时，要求复核。"
          underText="最高威胁变化未理解、排序长时间未确认时，解释变化原因。"
          onConfigure={() => setSection('threat')}
        />
      </div>
    </div>
  );

  const renderSensor = () => (
    <div style={{ display: 'grid', gap: '14px' }}>
      <RuleConfigNotice
        title="这里配置的是规则边界"
        body="调高低置信上限会更容易进入复核；调低高置信阈值会更容易进入解释。后台状态在总览中配置，行为类阈值只作为实验日志校准依据。"
      />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '14px' }}>
        <RangeField label="高置信阈值" hint="达到该值且超时未确认时，判定欠信任" value={draft.sensor.high_confidence} min={0.5} max={1} step={0.01} highlight={sensorHighConfidenceHit ? 'under' : undefined} statusText={sensorHighConfidenceHit ? `模拟置信度 ${simSensorConfidence.toFixed(2)} ≥ ${draft.sensor.high_confidence}，且等待 ${simSensorAgeMs}ms ≥ ${draft.sensor.unconfirmed_timeout_ms}ms` : `当前模拟未触发：需置信度 ≥ ${draft.sensor.high_confidence} 且未确认时间 ≥ ${draft.sensor.unconfirmed_timeout_ms}ms`} onChange={value => updateSensor('high_confidence', value)} />
        <RangeField label="低置信上限" hint="低于该值时，判定过信任风险" value={draft.sensor.low_confidence_max} min={0.3} max={0.95} step={0.01} highlight={sensorLowConfidenceHit ? 'over' : undefined} statusText={sensorLowConfidenceHit ? `模拟置信度 ${simSensorConfidence.toFixed(2)} ≤ ${draft.sensor.low_confidence_max}` : `当前模拟未触发：模拟置信度需 ≤ ${draft.sensor.low_confidence_max}`} onChange={value => updateSensor('low_confidence_max', value)} />
        <RangeField label="低置信下限" hint="用于 UI 分段展示低置信范围" value={draft.sensor.low_confidence_min} min={0.1} max={0.9} step={0.01} onChange={value => updateSensor('low_confidence_min', value)} />
        <RangeField label="候选差距阈值" hint="候选目标差距小于该值时提示复核" value={draft.sensor.candidate_gap_threshold} min={0.01} max={0.5} step={0.01} highlight={sensorCandidateGapHit ? 'over' : undefined} statusText={sensorCandidateGapHit ? `模拟候选差距 ${simSensorGap.toFixed(2)} < ${draft.sensor.candidate_gap_threshold}` : `当前模拟未触发：候选差距需 < ${draft.sensor.candidate_gap_threshold}`} onChange={value => updateSensor('candidate_gap_threshold', value)} />
        <RangeField label="未确认超时" hint="高置信推荐等待多久后展开解释" value={draft.sensor.unconfirmed_timeout_ms} min={500} max={15000} step={500} unit="ms" highlight={sensorHighConfidenceHit ? 'under' : undefined} statusText={sensorHighConfidenceHit ? `模拟等待 ${simSensorAgeMs}ms 已超过阈值` : `当前模拟未触发：需同时满足高置信和超时`} onChange={value => updateSensor('unconfirmed_timeout_ms', value)} />
        <RangeField label="连续拒绝阈值" hint="连续拒绝达到该次数后触发欠信任提示" value={draft.sensor.consecutive_reject_threshold} min={1} max={6} step={1} onChange={value => updateSensor('consecutive_reject_threshold', value)} />
        <RangeField label="直接接受阈值" hint="连续直接接受达到该次数后检查证据查看" value={draft.sensor.direct_accept_threshold} min={1} max={6} step={1} onChange={value => updateSensor('direct_accept_threshold', value)} />
        <RangeField label="行为窗口大小" hint="只统计最近 N 次人工确认/拒绝操作" value={draft.sensor.window_size} min={3} max={12} step={1} onChange={value => updateSensor('window_size', value)} />
        <RangeField label="状态回滞" hint="状态退出时保留的阈值余量，避免来回跳变" value={draft.sensor.hysteresis} min={0} max={3} step={1} onChange={value => updateSensor('hysteresis', value)} />
        <RangeField label="确认时延阈值" hint="最近确认平均耗时超过该值时判定欠信任倾向" value={draft.sensor.latency_threshold_ms} min={500} max={15000} step={500} unit="ms" onChange={value => updateSensor('latency_threshold_ms', value)} />
        <ToggleField label="确认前要求证据" hint="低置信或候选接近时，要求先查看证据或人工复核" checked={draft.sensor.require_evidence_before_confirm} onChange={checked => updateSensor('require_evidence_before_confirm', checked)} />
      </div>
    </div>
  );

  const renderThreat = () => (
    <div style={{ display: 'grid', gap: '14px' }}>
      <RuleConfigNotice
        title="排序规则同样只做预览"
        body="分差和延迟主要推高复核风险；排序长时间未确认、连续拒绝主要推高解释需求。后台状态在总览中配置，历史数据只用于校准阈值。"
      />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '14px' }}>
        <RangeField label="排序分差阈值" hint="第一/第二威胁分差小于该值时标记排序不稳定" value={draft.threat.score_gap_threshold} min={0.01} max={0.5} step={0.01} highlight={threatGapHit ? 'over' : undefined} statusText={threatGapHit ? `模拟分差 ${simThreatGap.toFixed(2)} < ${draft.threat.score_gap_threshold}` : `当前模拟未触发：排序分差需 < ${draft.threat.score_gap_threshold}`} onChange={value => updateThreat('score_gap_threshold', value)} />
        <RangeField label="数据延迟阈值" hint="威胁数据超过该延迟后提示数据质量风险" value={draft.threat.data_delay_ms} min={300} max={6000} step={100} unit="ms" highlight={threatDelayHit ? 'over' : undefined} statusText={threatDelayHit ? `模拟延迟 ${simThreatDelayMs}ms > ${draft.threat.data_delay_ms}ms` : `当前模拟未触发：数据延迟需 > ${draft.threat.data_delay_ms}ms`} onChange={value => updateThreat('data_delay_ms', value)} />
        <RangeField label="未确认超时" hint="排序长时间未确认时触发解释提示" value={draft.threat.unconfirmed_timeout_ms} min={500} max={15000} step={500} unit="ms" highlight={threatTimeoutHit ? 'under' : undefined} statusText={threatTimeoutHit ? `模拟未确认 ${simThreatDelayMs}ms ≥ ${draft.threat.unconfirmed_timeout_ms}ms` : `当前模拟未触发：未确认时间需 ≥ ${draft.threat.unconfirmed_timeout_ms}ms`} onChange={value => updateThreat('unconfirmed_timeout_ms', value)} />
        <RangeField label="连续拒绝阈值" hint="连续拒绝 AI 排序达到该次数后触发欠信任提示" value={draft.threat.consecutive_reject_threshold} min={1} max={6} step={1} onChange={value => updateThreat('consecutive_reject_threshold', value)} />
        <RangeField label="直接接受阈值" hint="连续直接查看结果达到该次数后检查证据查看" value={draft.threat.direct_accept_threshold} min={1} max={6} step={1} onChange={value => updateThreat('direct_accept_threshold', value)} />
        <RangeField label="行为窗口大小" hint="只统计最近 N 次威胁选择/查看结果操作" value={draft.threat.window_size} min={3} max={12} step={1} onChange={value => updateThreat('window_size', value)} />
        <RangeField label="状态回滞" hint="状态退出时保留的阈值余量，避免来回跳变" value={draft.threat.hysteresis} min={0} max={3} step={1} onChange={value => updateThreat('hysteresis', value)} />
        <RangeField label="确认时延阈值" hint="最近确认平均耗时超过该值时判定欠信任倾向" value={draft.threat.latency_threshold_ms} min={500} max={15000} step={500} unit="ms" onChange={value => updateThreat('latency_threshold_ms', value)} />
        <ToggleField label="提交前要求复核" hint="排序不稳定或数据延迟时，查看结果前必须复核" checked={draft.threat.require_evidence_before_submit} onChange={checked => updateThreat('require_evidence_before_submit', checked)} />
      </div>
    </div>
  );

  const renderDisplay = () => (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '14px' }}>
      <ToggleField label="显示解释面板" hint="开启右侧栏解释卡片" checked={draft.display.show_explanation_panel} onChange={checked => updateDisplay('show_explanation_panel', checked)} />
      <ToggleField label="显示候选对比" hint="在雷达或威胁列表中展示候选差异" checked={draft.display.show_candidate_comparison} onChange={checked => updateDisplay('show_candidate_comparison', checked)} />
      <ToggleField label="显示数据质量条" hint="威胁排序数据延迟时展示质量提示" checked={draft.display.show_data_quality_bar} onChange={checked => updateDisplay('show_data_quality_bar', checked)} />
      <ToggleField label="显示能力边界" hint="展示 AI 置信边界、IFF 限制等说明" checked={draft.display.show_capability_boundary} onChange={checked => updateDisplay('show_capability_boundary', checked)} />
      <ToggleField label="低置信阻止一键确认" hint="过信任风险下阻止直接确认或查看结果" checked={draft.display.block_one_click_on_low_confidence} onChange={checked => updateDisplay('block_one_click_on_low_confidence', checked)} />
    </div>
  );

  const renderExperiment = () => (
    <ExperimentStatusPanel
      history={history}
      config={draft}
      loading={historyLoading}
      error={historyError}
      onRefresh={loadTrustHistory}
      onApplySensorThresholds={applySensorThresholdPatch}
      onApplyThreatThresholds={applyThreatThresholdPatch}
    />
  );

  const currentContent = section === 'overview'
    ? renderOverview()
    : section === 'sensor'
      ? renderSensor()
      : section === 'threat'
        ? renderThreat()
        : section === 'experiment'
          ? renderExperiment()
          : renderDisplay();

  return (
    <div style={{
      flex: 1,
      minHeight: 0,
      display: 'grid',
      gridTemplateColumns: '250px minmax(520px, 1fr) 340px',
      gap: '16px',
      padding: '18px',
      overflow: 'auto',
      background: 'radial-gradient(ellipse 70% 70% at 50% 20%, rgba(0, 70, 30, 0.16), #030a05 62%)',
    }}>
      <aside style={{ ...panelStyle, padding: '16px', alignSelf: 'start' }}>
        <div className="panel-label">SETTINGS</div>
        <h2 style={{ margin: '0 0 6px', color: '#00ff88', fontSize: '20px', letterSpacing: '0.12em' }}>信任调控设置</h2>
        <p style={{ margin: '0 0 18px', color: '#5f9a68', fontSize: '12px', lineHeight: 1.6 }}>
          后台配置每个任务的调控状态；规则预览和历史样本只用于校准阈值。
        </p>
        <div style={{ display: 'grid', gap: '10px' }}>
          <NavButton active={section === 'overview'} label="总览" description="一个指数，一眼判断" onClick={() => setSection('overview')} />
          <NavButton active={section === 'sensor'} label="传感器任务" description="配置规则值" onClick={() => setSection('sensor')} />
          <NavButton active={section === 'threat'} label="威胁排序任务" description="配置规则值" onClick={() => setSection('threat')} />
          <NavButton active={section === 'experiment'} label="实验数据" description="样本量与采集状态" onClick={() => setSection('experiment')} />
          <NavButton active={section === 'display'} label="展示与拦截" description="提示、复核、一键确认" onClick={() => setSection('display')} />
        </div>
      </aside>

      <main style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '14px', alignItems: 'center', marginBottom: '14px' }}>
          <div>
            <div style={{ color: '#5ec8ff', fontSize: '12px', letterSpacing: '0.2em', marginBottom: '5px' }}>TRUST CALIBRATION</div>
            <h1 style={{ margin: 0, color: '#dfffea', fontSize: '24px', letterSpacing: '0.08em' }}>
              信任校准设置：后台状态与规则预览
            </h1>
          </div>
          <div style={{ display: 'flex', gap: '10px' }}>
            <button type="button" style={{ ...actionButtonStyle, background: 'rgba(28, 28, 8, 0.8)', borderColor: '#7a6a1e', color: '#ffdf73' }} onClick={resetDraft}>
              恢复默认
            </button>
            <button type="button" style={actionButtonStyle} onClick={applyDraft}>
              应用并保存
            </button>
            <button type="button" style={{ ...actionButtonStyle, background: 'rgba(35, 0, 0, 0.65)', borderColor: '#7a2626', color: '#ff8c8c' }} onClick={onClose}>
              返回任务
            </button>
          </div>
        </div>

        {saveStatus !== 'idle' && (
          <div style={{
            ...panelStyle,
            marginBottom: '14px',
            padding: '10px 12px',
            borderColor: saveStatus === 'sent' ? '#168842' : '#7a6a1e',
            background: saveStatus === 'sent' ? 'rgba(0, 48, 20, 0.7)' : 'rgba(45, 36, 0, 0.42)',
            color: saveStatus === 'sent' ? '#9effb5' : '#ffdf73',
            fontSize: '12px',
            letterSpacing: '0.06em',
          }}>
            {saveStatus === 'sent'
              ? '规则已应用到当前任务，并已发送后端保存请求。'
              : '规则已应用到当前任务；当前未连接后端，尚未写入配置文件。'}
            {lastAppliedAt && (
              <span style={{ marginLeft: '10px', color: '#6fa878' }}>
                {new Date(lastAppliedAt).toLocaleTimeString()}
              </span>
            )}
          </div>
        )}

        {currentContent}
      </main>

      <aside style={{ display: 'grid', gap: '14px', alignSelf: 'start' }}>
        <div style={{ ...panelStyle, padding: '16px', borderColor: draft.enabled ? '#13884a' : '#6a3232' }}>
          <div className="panel-label">PREVIEW</div>
          <div style={{ color: draft.enabled ? '#00ff88' : '#ff7777', fontSize: '18px', letterSpacing: '0.12em', marginBottom: '12px' }}>
            规则模拟器
          </div>
          <div style={{
            border: '1px solid rgba(255,223,115,0.55)',
            background: 'rgba(45,36,0,0.36)',
            padding: '10px 12px',
            borderRadius: '4px',
            marginBottom: '10px',
          }}>
            <div style={{ color: '#ffdf73', fontSize: '13px', fontWeight: 700, marginBottom: '5px' }}>仅模拟，不代表后台状态</div>
            <div style={{ color: '#d8ffe3', fontSize: '11px', lineHeight: 1.5 }}>用于观察规则阈值改动会把模拟样例推向哪个区间。</div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '10px' }}>
            <div style={{ border: '1px solid rgba(255,223,115,0.45)', background: 'rgba(45,36,0,0.28)', padding: '10px', borderRadius: '4px' }}>
              <div style={{ color: '#86c58f', fontSize: '11px', marginBottom: '4px' }}>实验样本</div>
              <div style={{ color: history?.sample_sufficient ? '#00ff88' : '#ffdf73', fontSize: '18px', fontWeight: 800 }}>
                {historyLoading ? '读取中' : `${historySampleCount} / ${historyMinimumSampleSize}`}
              </div>
            </div>
            <div style={{ border: '1px solid rgba(0,255,136,0.28)', background: 'rgba(0,35,16,0.24)', padding: '10px', borderRadius: '4px' }}>
              <div style={{ color: '#86c58f', fontSize: '11px', marginBottom: '4px' }}>规则验证</div>
              <div style={{ color: history?.sample_sufficient ? '#00ff88' : '#ffdf73', fontSize: '18px', fontWeight: 800 }}>
                {historyLoading ? '读取中' : history?.sample_sufficient ? '样本充足' : '样本不足'}
              </div>
            </div>
          </div>
          <div style={{ display: 'grid', gap: '10px' }}>
            {(section === 'overview' || section === 'sensor' || section === 'display') && (
              <>
            <MiniScoreCard title="传感器模拟预览" breakdown={sensorBreakdown} />
            <div style={{ display: 'grid', gap: '8px', padding: '10px', border: '1px solid #123a1d', background: 'rgba(0,12,5,0.58)' }}>
              <div style={{ color: '#86c58f', fontSize: '12px', letterSpacing: '0.08em' }}>传感器一键演示</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '8px' }}>
                <ScenarioButton state="over" label="触发过信任" onClick={() => setSensorScenario('over')} />
                <ScenarioButton state="under" label="触发欠信任" onClick={() => setSensorScenario('under')} />
                <ScenarioButton state="normal" label="回到正常" onClick={() => setSensorScenario('normal')} />
              </div>
            </div>
            <div style={{ display: 'grid', gap: '8px', padding: '10px', border: '1px solid #123a1d', background: 'rgba(0,12,5,0.58)' }}>
              <RangeField label="模拟置信度" hint="拖动观察低置信/高置信边界" value={simSensorConfidence} min={0} max={1} step={0.01} onChange={setSimSensorConfidence} />
              {section !== 'overview' && (
                <>
              <RangeField label="模拟候选差距" hint="小于候选差距阈值时进入过信任复核" value={simSensorGap} min={0} max={0.5} step={0.01} onChange={setSimSensorGap} />
              <RangeField label="模拟未确认时间" hint="高置信且超过超时阈值时进入欠信任解释" value={simSensorAgeMs} min={0} max={15000} step={500} unit="ms" onChange={setSimSensorAgeMs} />
                </>
              )}
            </div>
              </>
            )}
            {(section === 'overview' || section === 'threat' || section === 'display') && (
              <>
            <MiniScoreCard title="威胁排序模拟预览" breakdown={threatBreakdown} />
            <div style={{ display: 'grid', gap: '8px', padding: '10px', border: '1px solid #123a1d', background: 'rgba(0,12,5,0.58)' }}>
              <div style={{ color: '#86c58f', fontSize: '12px', letterSpacing: '0.08em' }}>威胁排序一键演示</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '8px' }}>
                <ScenarioButton state="over" label="触发过信任" onClick={() => setThreatScenario('over')} />
                <ScenarioButton state="under" label="触发欠信任" onClick={() => setThreatScenario('under')} />
                <ScenarioButton state="normal" label="回到正常" onClick={() => setThreatScenario('normal')} />
              </div>
            </div>
            <div style={{ display: 'grid', gap: '8px', padding: '10px', border: '1px solid #123a1d', background: 'rgba(0,12,5,0.58)' }}>
              <RangeField label="模拟排序分差" hint="越小越容易触发过信任复核" value={simThreatGap} min={0} max={0.5} step={0.01} onChange={setSimThreatGap} />
              <RangeField label="模拟数据延迟" hint="超过数据延迟阈值时进入过信任复核" value={simThreatDelayMs} min={0} max={8000} step={100} unit="ms" onChange={setSimThreatDelayMs} />
            </div>
              </>
            )}
          </div>
        </div>

        <div style={{ ...panelStyle, padding: '16px' }}>
          <div className="panel-label">CONFIG JSON</div>
          <pre style={{
            maxHeight: '330px',
            overflow: 'auto',
            margin: 0,
            padding: '12px',
            background: 'rgba(0, 8, 3, 0.86)',
            border: '1px solid #0b2a14',
            color: '#83d994',
            fontSize: '11px',
            lineHeight: 1.45,
            borderRadius: '3px',
          }}>
            {JSON.stringify({ trust_calibration: draft }, null, 2)}
          </pre>
          <button type="button" style={{ ...actionButtonStyle, width: '100%', marginTop: '12px' }} onClick={copyJson}>
            {copied ? '已复制 JSON' : '复制 JSON'}
          </button>
        </div>
      </aside>
    </div>
  );
});

export default TrustCalibrationSettings;
