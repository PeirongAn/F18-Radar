import React from 'react';
import { ThreatTrustDecision } from '../types/trustCalibration';

export interface ThreatRow {
  id: string;
  type: string;
  target: string;
  label: string;
  currentOrder: number;
  distance: number;
  time: string;
  displayType: string;
  priorityColor: string;
  isSelected?: boolean;
  isAiRecommended?: boolean;
}

export interface AttackRow {
  id: string;
  number: string;
  targetId: string;
  target: string;
  type: string;
  distance: number;
  source: string;
  isSelected?: boolean;
  isAiRecommended?: boolean;
}

export interface ThreatListData {
  threats: ThreatRow[];
  attacks: AttackRow[];
}

interface ThreatListProps extends ThreatListData {
  showDetailedInfo?: boolean;
  trustDecision?: ThreatTrustDecision;
}

const MONO: React.CSSProperties = {
  fontFamily: "'Share Tech Mono', monospace",
};

const headerCellStyle: React.CSSProperties = {
  ...MONO,
  fontSize: '12px',
  letterSpacing: '0.12em',
  color: '#4aaa60',
  padding: '5px 4px',
};

const cellBase: React.CSSProperties = {
  ...MONO,
  fontSize: '13px',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};

const formatDistance = (distance: number) => (
  typeof distance === 'number' && Number.isFinite(distance) && distance >= 0
    ? distance.toFixed(1)
    : '--'
);

const ThreatList: React.FC<ThreatListProps> = ({ threats, attacks, showDetailedInfo = false, trustDecision }) => {
  void showDetailedInfo;

  const renderEmpty = (text: string) => (
    <div style={{
      ...MONO,
      fontSize: '14px',
      color: '#4a9a55',
      textAlign: 'center',
      padding: '12px 0',
      letterSpacing: '0.1em',
    }}>
      {text}
    </div>
  );

  const renderTrustNotice = () => {
    if (!trustDecision?.enabled || trustDecision.controlLevel === 'none') {
      return null;
    }
    return (
      <div style={{
        ...MONO,
        fontSize: '12px',
        color: trustDecision.controlLevel === 'review' ? '#ffb45c' : '#5ec8ff',
        border: `1px solid ${trustDecision.controlLevel === 'review' ? '#9a5b1d' : '#155f8a'}`,
        padding: '5px 7px',
        marginBottom: '6px',
        background: 'rgba(0,20,8,0.65)',
      }}>
        {trustDecision.primaryMessage}
        {trustDecision.scoreGap !== undefined ? ` / 分差 ${trustDecision.scoreGap.toFixed(2)}` : ''}
      </div>
    );
  };

  return (
    <div data-gaze-aoi="left_candidate_list" style={{
      padding: '10px 14px 12px',
      background: 'rgba(0,8,3,0.9)',
      display: 'grid',
      gridTemplateColumns: 'minmax(0, 1.35fr) minmax(0, 1fr)',
      gap: '12px',
    }}>
      <section style={{ minWidth: 0 }}>
        <div className="panel-label">威胁列表</div>
        {renderTrustNotice()}
        {(!threats || threats.length === 0) ? renderEmpty('暂无威胁数据') : (
          <div style={{
            border: '1px solid #0d2a10',
            borderRadius: '2px',
            overflow: 'hidden',
          }}>
            <div style={{
              display: 'grid',
              gridTemplateColumns: '72px 1fr 1fr 60px 78px',
              gap: '4px',
              background: 'rgba(0,20,8,0.8)',
              borderBottom: '1px solid #0d3018',
              padding: '0 4px',
            }}>
              <div style={{ ...headerCellStyle, textAlign: 'center' }}>威胁排序</div>
              <div style={headerCellStyle}>目标</div>
              <div style={headerCellStyle}>类型</div>
              <div style={{ ...headerCellStyle, textAlign: 'right' }}>距离</div>
              <div style={{ ...headerCellStyle, textAlign: 'center' }}>时间</div>
            </div>
            <div style={{ maxHeight: '190px', overflowY: 'auto' }}>
              {threats.map((threat, idx) => {
                const isFirst = idx === 0;
                const isSelected = threat.isSelected === true;
                const isAiRecommended = threat.isAiRecommended === true;
                return (
                  <div
                    key={threat.id}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '72px 1fr 1fr 60px 78px',
                      alignItems: 'center',
                      gap: '4px',
                      padding: '5px 4px',
                      borderBottom: '1px solid #071a0a',
                      background: isSelected
                        ? 'rgba(75,58,0,0.78)'
                        : isAiRecommended
                          ? 'rgba(0,35,18,0.72)'
                          : isFirst
                            ? 'rgba(0,30,10,0.7)'
                            : idx % 2 === 0
                              ? 'rgba(0,10,4,0.6)'
                              : 'rgba(0,6,2,0.5)',
                      borderLeft: isSelected
                        ? '2px solid #ffd700'
                        : isAiRecommended
                          ? '2px solid #00ff66'
                          : isFirst
                            ? `2px solid ${threat.priorityColor}`
                            : '2px solid transparent',
                    }}
                  >
                    <div style={{
                      ...cellBase,
                      color: isFirst ? '#00cc55' : '#4a9a55',
                      textAlign: 'center',
                      fontWeight: isFirst ? 'bold' : 'normal',
                    }}>
                      {threat.currentOrder}
                    </div>
                    <div style={{
                      ...cellBase,
                      color: isSelected ? '#ffe66a' : isAiRecommended ? '#73ff9a' : isFirst ? '#c8a800' : '#8aaa66',
                    }} title={threat.target}>
                      {threat.target}
                      {isAiRecommended && <span style={{ marginLeft: '5px', color: '#00ff66', fontSize: '10px' }}>AI</span>}
                      {isSelected && <span style={{ marginLeft: '5px', color: '#ffd700', fontSize: '10px' }}>已选</span>}
                    </div>
                    <div style={{
                      ...cellBase,
                      color: isFirst ? '#00cc55' : '#4db87a',
                      fontWeight: isFirst ? 'bold' : 'normal',
                    }} title={threat.displayType}>
                      {threat.displayType}
                    </div>
                    <div style={{
                      ...cellBase,
                      color: '#4db87a',
                      textAlign: 'right',
                    }}>
                      {formatDistance(threat.distance)}
                    </div>
                    <div style={{
                      ...cellBase,
                      color: isFirst ? '#cccccc' : '#778877',
                      textAlign: 'center',
                    }}>
                      {threat.time}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </section>

      <section style={{ minWidth: 0 }}>
        <div className="panel-label">攻击列表</div>
        {(!attacks || attacks.length === 0) ? renderEmpty('暂无攻击数据') : (
          <div style={{
            border: '1px solid #0d2a10',
            borderRadius: '2px',
            overflow: 'hidden',
          }}>
            <div style={{
              display: 'grid',
              gridTemplateColumns: '58px minmax(78px, 1fr) minmax(78px, 1fr) 60px 56px',
              gap: '4px',
              background: 'rgba(0,20,8,0.8)',
              borderBottom: '1px solid #0d3018',
              padding: '0 4px',
            }}>
              <div style={{ ...headerCellStyle, textAlign: 'center' }}>编号</div>
              <div style={headerCellStyle}>目标</div>
              <div style={headerCellStyle}>类型</div>
              <div style={{ ...headerCellStyle, textAlign: 'right' }}>距离</div>
              <div style={{ ...headerCellStyle, textAlign: 'center' }}>来源</div>
            </div>
            <div style={{ maxHeight: '190px', overflowY: 'auto' }}>
              {attacks.map((attack, idx) => {
                const isSelected = attack.isSelected === true;
                const isAiRecommended = attack.isAiRecommended === true;
                return (
                  <div
                    key={attack.id}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '58px minmax(78px, 1fr) minmax(78px, 1fr) 60px 56px',
                      alignItems: 'center',
                      gap: '4px',
                      padding: '5px 4px',
                      borderBottom: '1px solid #071a0a',
                      background: isSelected
                        ? 'rgba(75,58,0,0.78)'
                        : isAiRecommended
                          ? 'rgba(0,35,18,0.72)'
                          : idx % 2 === 0
                            ? 'rgba(0,10,4,0.6)'
                            : 'rgba(0,6,2,0.5)',
                      borderLeft: isSelected
                        ? '2px solid #ffd700'
                        : isAiRecommended
                          ? '2px solid #00ff66'
                          : '2px solid transparent',
                    }}
                  >
                    <div style={{ ...cellBase, color: '#4a9a55', textAlign: 'center' }}>
                      {attack.number}
                    </div>
                    <div style={{ ...cellBase, color: '#8aaa66' }} title={attack.target}>
                      {attack.target}
                    </div>
                    <div style={{ ...cellBase, color: '#4db87a' }} title={attack.type}>
                      {attack.type}
                    </div>
                    <div style={{ ...cellBase, color: '#4db87a', textAlign: 'right' }}>
                      {formatDistance(attack.distance)}
                    </div>
                    <div style={{ ...cellBase, color: '#c8a800', textAlign: 'center' }}>
                      {attack.source}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </section>
    </div>
  );
};

export default ThreatList;
