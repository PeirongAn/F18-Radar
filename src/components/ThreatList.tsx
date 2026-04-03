import React from 'react';

interface ThreatData {
  id: string;
  type: string;
  label: string;
  index: number;
  distance: number;
  score: number;
  displayType: string;
  priorityLevel: string;
  priorityColor: string;
}

interface ThreatListProps {
  threats: ThreatData[];
  showDetailedInfo?: boolean;
}

const MONO: React.CSSProperties = {
  fontFamily: "'Share Tech Mono', monospace",
};

const ThreatList: React.FC<ThreatListProps> = ({ threats, showDetailedInfo = false }) => {
  // grid columns: index | type | label | [distance] | [score] | priority-dot
  const cols = showDetailedInfo
    ? '28px 1fr 1fr 62px 58px 52px'
    : '28px 1fr 1fr 52px';

  const headerCellStyle: React.CSSProperties = {
    ...MONO,
  fontSize: '12px',
  letterSpacing: '0.18em',
    color: '#4aaa60',
    textTransform: 'uppercase',
    padding: '4px 4px',
  };

  const rowBase: React.CSSProperties = {
    display: 'grid',
    gridTemplateColumns: cols,
    alignItems: 'center',
    padding: '5px 4px',
    borderBottom: '1px solid #071a0a',
    gap: '4px',
  };

  return (
    <div style={{
      padding: '10px 14px 12px',
      background: 'rgba(0,8,3,0.9)',
      display: 'flex',
      flexDirection: 'column',
      gap: '6px',
    }}>

      {/* ── Panel title ── */}
      <div className="panel-label">威胁列表</div>

      {(!threats || threats.length === 0) ? (
        <div style={{
          ...MONO,
      fontSize: '14px',
      color: '#4a9a55',
      textAlign: 'center',
      padding: '12px 0',
          letterSpacing: '0.1em',
        }}>
          暂无威胁数据
        </div>
      ) : (
        <div style={{
          border: '1px solid #0d2a10',
          borderRadius: '2px',
          overflow: 'hidden',
        }}>

          {/* ── Header ── */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: cols,
            gap: '4px',
            background: 'rgba(0,20,8,0.8)',
            borderBottom: '1px solid #0d3018',
            padding: '0 4px',
          }}>
            <div style={{ ...headerCellStyle, textAlign: 'center' }}>#</div>
            <div style={headerCellStyle}>类型</div>
            <div style={headerCellStyle}>标签</div>
            {showDetailedInfo && <div style={{ ...headerCellStyle, textAlign: 'right' }}>距离</div>}
            {showDetailedInfo && <div style={{ ...headerCellStyle, textAlign: 'right' }}>得分</div>}
            <div style={{ ...headerCellStyle, textAlign: 'center' }}>优先</div>
          </div>

          {/* ── Rows ── */}
          <div style={{ maxHeight: '200px', overflowY: 'auto' }}>
            {threats.map((threat, idx) => {
              const isFirst = idx === 0;
              return (
                <div
                  key={threat.id}
                  style={{
                    ...rowBase,
                    background: isFirst
                      ? 'rgba(0,30,10,0.7)'
                      : idx % 2 === 0
                        ? 'rgba(0,10,4,0.6)'
                        : 'rgba(0,6,2,0.5)',
                    borderLeft: isFirst ? `2px solid ${threat.priorityColor}` : '2px solid transparent',
                  }}
                >
                  {/* # */}
                  <div style={{
                    ...MONO,
    fontSize: '13px',
    color: isFirst ? '#00cc55' : '#4a9a55',
    textAlign: 'center',
                    fontWeight: isFirst ? 'bold' : 'normal',
                  }}>
                    {threat.index}
                  </div>

                  {/* 类型 */}
                  <div style={{
                    ...MONO,
    fontSize: '14px',
    color: isFirst ? '#00cc55' : '#4db87a',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    fontWeight: isFirst ? 'bold' : 'normal',
                  }} title={threat.displayType}>
                    {threat.displayType}
                  </div>

                  {/* 标签 */}
                  <div style={{
                    ...MONO,
    fontSize: '14px',
    color: isFirst ? '#c8a800' : '#8aaa66',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }} title={threat.label}>
                    {threat.label}
                  </div>

                  {/* 距离 */}
                  {showDetailedInfo && (
                    <div style={{
                      ...MONO,
                      fontSize: '13px',
                      color: '#4db87a',
                      textAlign: 'right',
                    }}>
                      {typeof threat.distance === 'number' && threat.distance >= 0
                        ? threat.distance.toFixed(1)
                        : '--'}
                    </div>
                  )}

                  {/* 得分 */}
                  {showDetailedInfo && (
                    <div style={{
                      ...MONO,
                      fontSize: '13px',
                      color: isFirst ? '#c8a800' : '#aa8833',
                      textAlign: 'right',
                      fontWeight: isFirst ? 'bold' : 'normal',
                    }}>
                      {typeof threat.score === 'number' && threat.score >= 0
                        ? threat.score.toFixed(2)
                        : '--'}
                    </div>
                  )}

                  {/* 优先级 */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px' }}>
                    <span style={{
                      display: 'inline-block',
                      width: '6px',
                      height: '6px',
                      borderRadius: '50%',
                      backgroundColor: threat.priorityColor,
                      boxShadow: `0 0 4px ${threat.priorityColor}`,
                      flexShrink: 0,
                    }} />
                    <span style={{
                      ...MONO,
                    fontSize: '13px',
                    color: isFirst ? '#cccccc' : '#778877',
                    }}>
                      {threat.priorityLevel}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

        </div>
      )}
    </div>
  );
};

export default ThreatList;
