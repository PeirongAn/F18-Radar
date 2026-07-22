import React from 'react';
import type { TrustCandidate, TrustControlState, TrustTrialSnapshot } from '../types/trustControl';

const mono: React.CSSProperties = {
  fontFamily: "'Share Tech Mono', 'Microsoft YaHei', monospace",
};

const displayName = (candidate: TrustCandidate | null) => {
  if (!candidate) return '--';
  return candidate.displayNumber !== undefined ? `目标${candidate.displayNumber}` : candidate.label;
};

const numberValue = (value: number | undefined, digits = 1) => (
  typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '--'
);

const dataTime = (candidate: TrustCandidate | null) => {
  const timestamp = candidate?.observedAtMs ?? candidate?.updatedAt;
  if (!timestamp) return '--';
  const date = new Date(timestamp);
  const clock = date.toLocaleTimeString('zh-CN', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
  return `${clock}.${String(date.getMilliseconds()).padStart(3, '0')}`;
};

const ObservationGrid: React.FC<{ candidate: TrustCandidate | null; compact?: boolean }> = ({ candidate, compact = false }) => (
  <div style={{
    display: 'grid',
    gridTemplateColumns: compact ? '68px 1fr' : '76px 1fr',
    gap: compact ? '3px 8px' : '5px 10px',
    color: '#c8e8cf',
    fontSize: compact ? 11 : 12,
    lineHeight: 1.45,
  }}>
    <span style={{ color: '#619a70' }}>方位</span><span>{numberValue(candidate?.azimuthDeg)}°</span>
    <span style={{ color: '#619a70' }}>距离</span><span>{numberValue(candidate?.distanceNm ?? candidate?.distance)} NM</span>
    <span style={{ color: '#619a70' }}>速度</span><span>{numberValue(candidate?.speedRaw)}（原始值）</span>
    <span style={{ color: '#619a70' }}>航向</span><span>{numberValue(candidate?.headingDeg)}°</span>
    <span style={{ color: '#619a70' }}>相对航向</span><span>{numberValue(candidate?.relativeHeadingDeg)}°</span>
    <span style={{ color: '#619a70' }}>数据时间</span><span>{dataTime(candidate)}</span>
  </div>
);

const ThreatObservationGrid: React.FC<{ candidate: TrustCandidate | null; compact?: boolean }> = ({ candidate, compact = false }) => (
  <div style={{
    display: 'grid',
    gridTemplateColumns: compact ? '68px 1fr' : '76px 1fr',
    gap: compact ? '3px 8px' : '5px 10px',
    color: '#c8e8cf',
    fontSize: compact ? 11 : 12,
    lineHeight: 1.45,
  }}>
    <span style={{ color: '#619a70' }}>威胁类别</span><span>{candidate?.categoryLabel ?? '--'}</span>
    <span style={{ color: '#619a70' }}>目标特征</span><span>{candidate?.sourceLabel ?? '--'}</span>
    <span style={{ color: '#619a70' }}>中心距离</span><span>{numberValue(candidate?.distance)}</span>
    <span style={{ color: '#619a70' }}>显示坐标</span><span>{numberValue(candidate?.positionX, 0)}, {numberValue(candidate?.positionY, 0)}</span>
    <span style={{ color: '#619a70' }}>数据时间</span><span>{dataTime(candidate)}</span>
  </div>
);

const AccuracyTrend: React.FC<{ control: TrustControlState }> = ({ control }) => {
  const fullSeries = control.ai_history_accuracy_series ?? [];
  const fullCorrectness = control.ai_history_correctness_series ?? [];
  const firstVisibleIndex = Math.max(0, fullSeries.length - 12);
  const series = fullSeries.slice(firstVisibleIndex);
  const correctness = fullCorrectness.slice(firstVisibleIndex);
  const currentPercent = control.ai_history_accuracy === null
    ? null
    : Math.round(control.ai_history_accuracy * 100);
  const left = 18;
  const right = 388;
  const top = 12;
  const bottom = 48;
  const points = series.map((value, index) => {
    const x = series.length === 1
      ? right
      : left + ((right - left) * index) / (series.length - 1);
    const bounded = Math.max(0, Math.min(1, value));
    const y = bottom - bounded * (bottom - top);
    return { x, y, value, sourceIndex: firstVisibleIndex + index };
  });
  const path = points.map((point, index) => (
    `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`
  )).join(' ');
  const historyText = currentPercent === null
    ? '暂无历史（0次）'
    : `${currentPercent}%（${control.ai_history_correct_count}/${control.ai_history_valid_count}）`;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ color: '#9eb9c2', fontSize: 12, letterSpacing: '0.04em' }}>AI历史识别准确率</span>
        <span style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: '3px 8px',
          border: '1px solid rgba(235,166,45,0.62)',
          borderRadius: 4,
          background: 'rgba(126,79,8,0.20)',
          color: '#d9c695',
          fontSize: 10,
          letterSpacing: '0.08em',
        }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#f4b33c', boxShadow: '0 0 7px #f4b33c' }} />
          当前可靠性
        </span>
      </div>
      <div style={{
        position: 'relative',
        height: 78,
        overflow: 'hidden',
        border: '1px solid rgba(32,102,122,0.34)',
        borderRadius: 6,
        background: 'linear-gradient(180deg, rgba(0,31,45,0.72), rgba(0,19,31,0.82))',
        boxShadow: 'inset 0 0 18px rgba(0,130,155,0.05)',
      }}>
        {points.length > 0 ? (
          <svg
            viewBox="0 0 460 72"
            preserveAspectRatio="none"
            role="img"
            aria-label={`AI历史识别准确率 ${historyText}`}
            style={{ display: 'block', width: '100%', height: '100%' }}
          >
            <line x1={left} y1={bottom} x2={right} y2={bottom} stroke="rgba(71,142,152,0.16)" strokeWidth="1" />
            <path d={path} fill="none" stroke="#39d8b2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ filter: 'drop-shadow(0 0 3px rgba(57,216,178,0.45))' }} />
            {points.map((point, index) => {
              const isCurrent = index === points.length - 1;
              const isCorrect = correctness[index] !== false;
              const color = isCurrent || !isCorrect ? '#f4aa32' : '#7af7d5';
              return (
                <g key={point.sourceIndex}>
                  <title>{`历史试次${point.sourceIndex + 1}：累计准确率${Math.round(point.value * 100)}%${isCorrect ? '，AI识别正确' : '，AI识别错误'}`}</title>
                  {isCurrent && <circle cx={point.x} cy={point.y} r="8" fill="rgba(244,170,50,0.12)" stroke="rgba(244,170,50,0.32)" />}
                  <circle cx={point.x} cy={point.y} r={isCurrent ? 5 : 3.6} fill="#eafff9" stroke={color} strokeWidth={isCurrent ? 2.2 : 1.5} style={{ filter: `drop-shadow(0 0 3px ${color})` }} />
                </g>
              );
            })}
            <text x={left} y="65" fill="#4f7580" fontSize="9">历史</text>
            <text x={right - 16} y="65" fill="#708e98" fontSize="9">当前</text>
            <text x="414" y="42" fill="#f4b33c" fontSize="14" fontWeight="700">{currentPercent}%</text>
            <text x="416" y="56" fill="#806e45" fontSize="8">{control.ai_history_correct_count}/{control.ai_history_valid_count}</text>
          </svg>
        ) : (
          <div role="img" aria-label="AI历史识别准确率 暂无历史（0次）" style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#52727b', fontSize: 11, letterSpacing: '0.08em' }}>
            暂无历史（0次）
          </div>
        )}
      </div>
    </div>
  );
};

const TrustControlPanel: React.FC<{ snapshot: TrustTrialSnapshot | null }> = ({ snapshot }) => {
  if (!snapshot?.control?.enabled) return null;
  const {
    control, aiRecommendation, candidates, focusedCandidate, humanSelection,
    manualReviewActive, manualReviewCandidate, manualReviewFeedback,
  } = snapshot;
  const support = control.ui_mode === 'trust_support';
  const isSaTask = snapshot.taskType === 'SA_THREAT_RESPONSE';
  const accent = support ? '#7ad7e8' : '#27d97b';
  const emphasis: React.CSSProperties = support ? {
    borderColor: 'rgba(122,215,232,0.7)',
    boxShadow: 'inset 0 0 18px rgba(70,190,215,0.08)',
  } : {};
  const detailCandidate = manualReviewActive ? manualReviewCandidate : focusedCandidate;
  const renderObservation = (candidate: TrustCandidate | null, compact = false) => (
    isSaTask
      ? <ThreatObservationGrid candidate={candidate} compact={compact} />
      : <ObservationGrid candidate={candidate} compact={compact} />
  );

  return (
    <div style={{ ...mono, flexShrink: 0, borderBottom: '1px solid #0a2010', background: 'rgba(0,18,8,0.92)' }}>
      <section data-gaze-aoi="right_ai_history_accuracy" style={{ padding: '10px 16px 12px', borderBottom: '1px solid #0a2010', background: 'linear-gradient(180deg, rgba(0,28,21,0.48), rgba(0,18,8,0.16))' }}>
        <AccuracyTrend control={control} />
      </section>

      <section data-gaze-aoi="right_recommendation" style={{ padding: '12px 16px', borderBottom: '1px solid #0a2010', ...emphasis }}>
        <div className="panel-label" style={{ color: accent }}>AI 推荐观测</div>
        <div style={{ display: 'grid', gridTemplateColumns: '108px 1fr', gap: '5px 10px', marginBottom: 9, color: '#c8e8cf', fontSize: 12 }}>
          <span style={{ color: '#619a70' }}>推荐目标</span><span>{displayName(aiRecommendation)}</span>
        </div>
        {renderObservation(aiRecommendation)}
      </section>

      <section data-gaze-aoi="right_candidate_list" style={{ padding: '10px 16px', borderBottom: '1px solid #0a2010' }}>
        <div className="panel-label">候选目标观测</div>
        <div style={{ display: 'grid', gridTemplateColumns: '76px 1fr 1fr 92px', gap: 8, color: '#4f7f5b', fontSize: 10, paddingBottom: 4 }}>
          <span>目标</span><span>{isSaTask ? '类别' : '方位'}</span><span>{isSaTask ? '中心距离' : '距离'}</span><span>数据时间</span>
        </div>
        {candidates.slice(0, 5).map(candidate => (
          <div key={candidate.id} style={{ display: 'grid', gridTemplateColumns: '76px 1fr 1fr 92px', gap: 8, padding: '4px 0', color: candidate.id === aiRecommendation?.id ? '#d8ffe4' : '#79ad86', fontSize: 11 }}>
            <span>{candidate.id === aiRecommendation?.id ? 'AI · ' : ''}{displayName(candidate)}</span>
            <span>{isSaTask ? candidate.categoryLabel ?? '--' : `${numberValue(candidate.azimuthDeg)}°`}</span>
            <span>{isSaTask ? numberValue(candidate.distance) : `${numberValue(candidate.distanceNm ?? candidate.distance)} NM`}</span>
            <span>{dataTime(candidate)}</span>
          </div>
        ))}
      </section>

      <section data-gaze-aoi="right_detail" style={{ padding: '10px 16px', minHeight: 116, borderBottom: '1px solid #0a2010', ...emphasis }}>
        <div className="panel-label">{manualReviewActive ? '人工复核 · AI推荐目标' : 'TDC 聚焦详情'}</div>
        {detailCandidate ? (
          <>
            <div style={{ color: manualReviewActive ? '#c7f8ff' : '#c8e8cf', fontSize: 13, marginBottom: 6 }}>
              {displayName(detailCandidate)}
            </div>
            {renderObservation(detailCandidate, true)}
          </>
        ) : <div style={{ color: '#51745a', fontSize: 12 }}>移动TDC聚焦目标后自动显示</div>}
        <div style={{
          marginTop: 8,
          paddingTop: 7,
          borderTop: '1px solid rgba(80,170,100,0.18)',
          color: manualReviewFeedback.status === 'active' ? '#91e8f5' : manualReviewFeedback.status === 'ignored' ? '#e0b566' : '#6ba87a',
          fontSize: 11,
        }}>
          第3键人工复核：{manualReviewFeedback.message} · {snapshot.manualReviewCount}次 · 累计{(snapshot.manualReviewDurationMs / 1000).toFixed(1)}秒
        </div>
      </section>

      <section data-gaze-aoi="right_comparison" data-visible={snapshot.comparisonVisible ? 'true' : 'false'} style={{ padding: '10px 16px', minHeight: 96, opacity: snapshot.comparisonVisible ? 1 : 0.45 }}>
        <div className="panel-label">人机选择观测对比</div>
        {snapshot.comparisonVisible ? (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, fontSize: 11 }}>
            <div style={{ border: '1px solid #245337', padding: 7, color: '#bdecca' }}>
              <div style={{ marginBottom: 5 }}>AI · {displayName(aiRecommendation)}</div>
              {renderObservation(aiRecommendation, true)}
            </div>
            <div style={{ border: '1px solid #245337', padding: 7, color: '#bdecca' }}>
              <div style={{ marginBottom: 5 }}>人工 · {displayName(humanSelection)}</div>
              {renderObservation(humanSelection, true)}
            </div>
          </div>
        ) : <div style={{ color: '#51745a', fontSize: 12 }}>人机选择一致时无需对比</div>}
      </section>
    </div>
  );
};

export default TrustControlPanel;
