import React from 'react';
import type { TrustCandidate, TrustControlState, TrustTrialSnapshot } from '../types/trustControl';
import './TrustControlPanel.css';

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

interface ObservationItem {
  label: string;
  value: string;
}

const ObservationGrid: React.FC<{ candidate: TrustCandidate | null; compact?: boolean }> = ({ candidate, compact = false }) => {
  const items: ObservationItem[] = [
    { label: '方位', value: `${numberValue(candidate?.azimuthDeg)}°` },
    { label: '距离', value: `${numberValue(candidate?.distanceNm ?? candidate?.distance)} NM` },
    { label: '速度', value: `${numberValue(candidate?.speedRaw)}（原始值）` },
    { label: '航向', value: `${numberValue(candidate?.headingDeg)}°` },
    { label: '相对航向', value: `${numberValue(candidate?.relativeHeadingDeg)}°` },
    { label: '数据时间', value: dataTime(candidate) },
  ];
  return <ObservationItems items={items} compact={compact} />;
};

const ThreatObservationGrid: React.FC<{ candidate: TrustCandidate | null; compact?: boolean }> = ({ candidate, compact = false }) => {
  const items: ObservationItem[] = [
    { label: '威胁类别', value: candidate?.categoryLabel ?? '--' },
    { label: '目标特征', value: candidate?.sourceLabel ?? '--' },
    { label: '中心距离', value: numberValue(candidate?.distance) },
    { label: '显示坐标', value: `${numberValue(candidate?.positionX, 0)}, ${numberValue(candidate?.positionY, 0)}` },
    { label: '数据时间', value: dataTime(candidate) },
  ];
  return <ObservationItems items={items} compact={compact} />;
};

const ObservationItems: React.FC<{ items: ObservationItem[]; compact: boolean }> = ({ items, compact }) => (
  <dl className={`trust-observation${compact ? ' trust-observation--compact' : ''}`}>
    {items.map(item => (
      <div className="trust-observation__item" key={item.label}>
        <dt className="trust-observation__label">{item.label}</dt>
        <dd className="trust-observation__value" title={item.value}>{item.value}</dd>
      </div>
    ))}
  </dl>
);

const AccuracyTrend: React.FC<{ control: TrustControlState }> = ({ control }) => {
  const series = control.ai_statistical_accuracy_series ?? [];
  const currentPercent = control.ai_statistical_accuracy === null
    ? null
    : Math.round(control.ai_statistical_accuracy * 100);
  const lowerBound = control.ai_statistical_accuracy_lower_bound;
  const upperBound = control.ai_statistical_accuracy_upper_bound;
  const lowerPercent = lowerBound === null ? null : Math.round(lowerBound * 100);
  const upperPercent = upperBound === null ? null : Math.round(upperBound * 100);
  const aiLevel = control.condition_key.ai_level || '--';
  const rangeText = lowerPercent === null || upperPercent === null
    ? '范围未知'
    : `${lowerPercent}%～${upperPercent}%`;
  const conditionText = `${aiLevel} · 波动范围 ${rangeText}`;
  const left = 18;
  const right = 388;
  const top = 12;
  const bottom = 48;
  const verticalSpan = lowerBound !== null && upperBound !== null
    ? upperBound - lowerBound
    : 0;
  const verticalMin = verticalSpan > 0 && lowerBound !== null
    ? Math.max(0, lowerBound - verticalSpan * 0.15)
    : 0;
  const verticalMax = verticalSpan > 0 && upperBound !== null
    ? Math.min(1, upperBound + verticalSpan * 0.15)
    : 1;
  const points = series.map((value, index) => {
    const x = series.length === 1
      ? right
      : left + ((right - left) * index) / (series.length - 1);
    const bounded = Math.max(0, Math.min(1, value));
    const displayRatio = verticalMax === verticalMin
      ? bounded
      : (bounded - verticalMin) / (verticalMax - verticalMin);
    const y = bottom - Math.max(0, Math.min(1, displayRatio)) * (bottom - top);
    return { x, y, value, sourceIndex: index };
  });
  const path = points.map((point, index) => (
    `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`
  )).join(' ');
  const statisticText = currentPercent === null ? '暂无统计值' : `${currentPercent}%`;

  return (
    <div>
      <div className="trust-accuracy-header">
        <span className="trust-accuracy-title">AI 统计识别准确率</span>
        <span className="trust-accuracy-value">等级统计值 · {statisticText}</span>
      </div>
      <div className="trust-chart">
        {points.length > 0 ? (
          <svg
            viewBox="0 0 460 72"
            preserveAspectRatio="none"
            role="img"
            aria-label={`AI统计识别准确率 ${statisticText} ${conditionText}`}
            style={{ display: 'block', width: '100%', height: '100%' }}
          >
            <line x1={left} y1={bottom} x2={right} y2={bottom} stroke="rgba(71,142,152,0.16)" strokeWidth="1" />
            <path d={path} fill="none" stroke="#39d8b2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ filter: 'drop-shadow(0 0 3px rgba(57,216,178,0.45))' }} />
            {points.map((point, index) => {
              const isCurrent = index === points.length - 1;
              const color = isCurrent ? '#f4aa32' : '#7af7d5';
              return (
                <g key={point.sourceIndex}>
                  <title>{`参考点${point.sourceIndex + 1}：${Math.round(point.value * 100)}%`}</title>
                  {isCurrent && <circle cx={point.x} cy={point.y} r="8" fill="rgba(244,170,50,0.12)" stroke="rgba(244,170,50,0.32)" />}
                  <circle cx={point.x} cy={point.y} r={isCurrent ? 5 : 3.6} fill="#eafff9" stroke={color} strokeWidth={isCurrent ? 2.2 : 1.5} style={{ filter: `drop-shadow(0 0 3px ${color})` }} />
                </g>
              );
            })}
            <text x={left} y="65" fill="#4f7580" fontSize="9">能力波动</text>
            <text x={right - 26} y="65" fill="#708e98" fontSize="9">统计水平</text>
            <text x="414" y="42" fill="#f4b33c" fontSize="14" fontWeight="700">{currentPercent ?? '--'}%</text>
            <text x="402" y="56" fill="#806e45" fontSize="8">{aiLevel} · {rangeText}</text>
          </svg>
        ) : (
          <div className="trust-empty" role="img" aria-label={`AI统计识别准确率 暂无统计值 ${aiLevel}`}>
            暂无统计值
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
  const detailCandidate = manualReviewActive ? manualReviewCandidate : focusedCandidate;
  const renderObservation = (candidate: TrustCandidate | null, compact = false) => (
    isSaTask
      ? <ThreatObservationGrid candidate={candidate} compact={compact} />
      : <ObservationGrid candidate={candidate} compact={compact} />
  );

  return (
    <aside className={`trust-panel${support ? ' trust-panel--support' : ''}`} aria-label="AI 决策辅助面板">
      <section className="trust-section trust-section--secondary" data-gaze-aoi="right_ai_history_accuracy">
        <AccuracyTrend control={control} />
      </section>

      <section className="trust-section" data-gaze-aoi="right_recommendation">
        <div className="trust-section-heading">
          <span className="trust-eyebrow">AI 推荐结果</span>
          <span className="trust-count">实时决策辅助</span>
        </div>
        <div className={`trust-hero${snapshot.glowActive ? ' trust-hero--glow' : ''}`}>
          <div className="trust-hero-topline">
            <span className="trust-hero-label">{isSaTask ? '建议优先处置目标' : '建议优先锁定目标'}</span>
            <span className="trust-recommendation-state">当前推荐</span>
          </div>
          <div className="trust-hero-title-row">
            <strong className="trust-hero-name">{displayName(aiRecommendation)}</strong>
            <span className="trust-priority">高优先级</span>
          </div>
          {renderObservation(aiRecommendation)}
        </div>
      </section>

      <section className="trust-section" data-gaze-aoi="right_candidate_list">
        <div className="trust-section-heading">
          <span className="trust-eyebrow">候选目标优先级</span>
          <span className="trust-count">{Math.min(candidates.length, 5)} / {candidates.length}</span>
        </div>
        <div className="trust-candidate-table">
          <div className="trust-candidate-header" aria-hidden="true">
            <span>序</span>
            <span>目标</span>
            <span>{isSaTask ? '威胁类别' : '方位'}</span>
            <span>{isSaTask ? '中心距离' : '距离'}</span>
            <span>更新时间</span>
          </div>
          {candidates.slice(0, 5).map((candidate, index) => {
            const recommended = candidate.id === aiRecommendation?.id;
            return (
              <div
                className={`trust-candidate-row${recommended ? ' trust-candidate-row--recommended' : ''}`}
                data-recommended={recommended ? 'true' : 'false'}
                key={candidate.id}
              >
                <span className="trust-candidate-rank">{String(index + 1).padStart(2, '0')}</span>
                <span className="trust-candidate-name">
                  {displayName(candidate)}
                  {recommended && <span className="trust-candidate-badge">AI 推荐</span>}
                </span>
                <span>{isSaTask ? candidate.categoryLabel ?? '--' : `${numberValue(candidate.azimuthDeg)}°`}</span>
                <span>{isSaTask ? numberValue(candidate.distance) : `${numberValue(candidate.distanceNm ?? candidate.distance)} NM`}</span>
                <span>{dataTime(candidate)}</span>
              </div>
            );
          })}
          {candidates.length === 0 && <div className="trust-empty">等待候选目标数据</div>}
        </div>
      </section>

      <section className="trust-section trust-section--secondary" data-gaze-aoi="right_detail">
        <div className="trust-section-heading">
          <span className="trust-eyebrow">{manualReviewActive ? '人工复核 · AI 推荐目标' : 'TDC 聚焦详情'}</span>
        </div>
        {detailCandidate ? (
          <>
            <div className="trust-detail-name">{displayName(detailCandidate)}</div>
            {renderObservation(detailCandidate, true)}
          </>
        ) : <div className="trust-empty">移动 TDC 聚焦目标后自动显示</div>}
        <div className={`trust-review-status${
          manualReviewFeedback.status === 'active'
            ? ' trust-review-status--active'
            : manualReviewFeedback.status === 'ignored'
              ? ' trust-review-status--ignored'
              : ''
        }`}>
          第3键人工复核：{manualReviewFeedback.message} · {snapshot.manualReviewCount}次 · 累计{(snapshot.manualReviewDurationMs / 1000).toFixed(1)}秒
        </div>
      </section>

      <section
        className={`trust-section trust-section--secondary${snapshot.comparisonVisible ? '' : ' trust-section--dimmed'}`}
        data-gaze-aoi="right_comparison"
        data-visible={snapshot.comparisonVisible ? 'true' : 'false'}
      >
        <div className="trust-section-heading">
          <span className="trust-eyebrow">人机选择观测对比</span>
        </div>
        {snapshot.comparisonVisible ? (
          <div className="trust-comparison">
            <div className="trust-comparison-card">
              <div className="trust-comparison-card__title">AI · {displayName(aiRecommendation)}</div>
              {renderObservation(aiRecommendation, true)}
            </div>
            <div className="trust-comparison-card">
              <div className="trust-comparison-card__title">人工 · {displayName(humanSelection)}</div>
              {renderObservation(humanSelection, true)}
            </div>
          </div>
        ) : <div className="trust-empty">人机选择一致时无需对比</div>}
      </section>
    </aside>
  );
};

export default TrustControlPanel;
