import React, { useEffect, useState, useRef } from 'react';
import { observer } from 'mobx-react-lite';
import agentStore from '../stores/AgentStore';

interface AIAssistantProps {
  selectedTarget: string | null;
}

interface LogEntry {
  id: number;
  message: string;
  timestamp: Date;
  type: 'info' | 'warning' | 'success' | 'error';
}

const LOG_TYPE = {
  info:    { color: '#4db87a', prefix: 'INFO' },
  success: { color: '#00cc55', prefix: 'OK  ' },
  warning: { color: '#c8a800', prefix: 'WARN' },
  error:   { color: '#cc4444', prefix: 'ERR ' },
} as const;

const AIAssistant: React.FC<AIAssistantProps> = observer(({ selectedTarget }) => {
  const [logs, setLogs] = useState<LogEntry[]>([
    { id: Date.now(), message: '智能辅助系统已初始化', timestamp: new Date(), type: 'info' }
  ]);
  const logIdCounter = useRef(Date.now());
  const logsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  useEffect(() => {
    if (selectedTarget) {
      addLog(`已检测到目标 ${selectedTarget}，开始分析`, 'info');
      setTimeout(() => {
        addLog(`目标 ${selectedTarget} 分析完成：敌方战斗机，距离35海里，高度23,000英尺`, 'success');
      }, 1500);
    }
  }, [selectedTarget]);

  useEffect(() => {
    if (agentStore.isAIActive) {
      addLog('智能辅助系统已激活，开始自动分析雷达数据', 'success');
    } else {
      addLog('智能辅助系统已停用，切换到手动控制模式', 'warning');
    }
  }, [agentStore.isAIActive]);

  const addLog = (message: string, type: 'info' | 'warning' | 'success' | 'error') => {
    setLogs(prev => [...prev, { id: ++logIdCounter.current, message, timestamp: new Date(), type }]);
  };

  const handleToggleAI = () => {
    agentStore.setAIActive(!agentStore.isAIActive);
  };

  const isActive = agentStore.isAIActive;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>

      {/* ── Status Row ── */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '7px 12px',
        background: 'rgba(0,18,7,0.7)',
        border: '1px solid #0a2010',
        borderLeft: `2px solid ${isActive ? '#00cc55' : '#4a2800'}`,
      }}>
        {/* Left: indicator + label */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div className={isActive ? 'pulse-dot' : ''} style={{
            width: 7, height: 7, borderRadius: '50%',
            flexShrink: 0,
            background: isActive ? '#00cc55' : '#774400',
            boxShadow: isActive ? '0 0 5px #00cc55, 0 0 10px rgba(0,204,85,0.3)' : 'none',
          }} />
          <span style={{
            fontFamily: "'Share Tech Mono', monospace",
            fontSize: '14px',
            letterSpacing: '0.12em',
            color: isActive ? '#00cc55' : '#775533',
          }}>
            {isActive ? 'AI·ACTIVE' : 'STANDBY'}
          </span>
          <span style={{
            fontFamily: "'Share Tech Mono', monospace",
            fontSize: '12px',
            color: '#4a9a55',
            letterSpacing: '0.08em',
          }}>
            {isActive ? '// 自动分析' : '// 人工接管'}
          </span>
        </div>

        {/* Right: clock + toggle */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{
            fontFamily: "'Share Tech Mono', monospace",
            fontSize: '13px',
            color: '#4aaa5a',
            letterSpacing: '0.05em',
          }}>
            {new Date().toLocaleTimeString('zh-CN', { hour12: false })}
          </span>
          <button
            onClick={handleToggleAI}
            style={{
              fontFamily: "'Share Tech Mono', monospace",
              fontSize: '12px',
              letterSpacing: '0.12em',
              padding: '4px 12px',
              border: `1px solid ${isActive ? '#4a2000' : '#0a3818'}`,
              background: isActive ? 'rgba(60,15,0,0.5)' : 'rgba(0,30,12,0.5)',
              color: isActive ? '#aa5522' : '#00aa44',
              cursor: 'pointer',
              transition: 'background 0.2s, color 0.2s',
              outline: 'none',
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLButtonElement).style.background = isActive
                ? 'rgba(90,25,0,0.7)' : 'rgba(0,50,20,0.7)';
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLButtonElement).style.background = isActive
                ? 'rgba(60,15,0,0.5)' : 'rgba(0,30,12,0.5)';
            }}
          >
            {isActive ? '人工接管' : '激活 AI'}
          </button>
        </div>
      </div>

      {/* ── Log Feed ── */}
      <div style={{
        maxHeight: '88px',
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        gap: '1px',
      }}>
        {logs.slice(-10).map(log => {
          const t = LOG_TYPE[log.type];
          return (
            <div key={log.id} style={{
              display: 'grid',
              gridTemplateColumns: '68px 44px 1fr',
              gap: '6px',
              alignItems: 'baseline',
              fontFamily: "'Share Tech Mono', monospace",
              fontSize: '13px',
              lineHeight: '1.6',
            }}>
              <span style={{ color: '#4a9a55', fontSize: '12px' }}>
                {log.timestamp.toLocaleTimeString('zh-CN', { hour12: false })}
              </span>
              <span style={{ color: t.color, opacity: 0.85 }}>
                [{t.prefix}]
              </span>
              <span style={{ color: t.color }}>
                {log.message}
              </span>
            </div>
          );
        })}
        <div ref={logsEndRef} />
      </div>

    </div>
  );
});

export default AIAssistant;
