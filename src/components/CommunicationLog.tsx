import React, { useState, useEffect, useRef, useCallback } from 'react';

export type MessageType = 'info' | 'warning' | 'error' | 'success' | 'client' | 'server' | 'system' 
  | 'sa_init' | 'sa_emergency' | 'sa_threat' | 'sa_missile';

export interface LogMessage {
  id: string;
  type: MessageType;
  content: string;
  timestamp: Date;
}

interface CommunicationLogProps {
  userId?: string;
  isStarted?: boolean; // 系统是否已启动的标志
  taskId?: number | null;
  currentTask?: 'radar' | 'sa'; // 当前任务类型
  messages: LogMessage[];
  onAddMessage?: (type: MessageType, content: string) => void;
  radarRange?: number;
  scanAngle?: number;
  antennaAdjustmentRequired?: boolean;
  targetAntennaElevation?: number;
  initSettings?: any;
  connected?: boolean;
  error?: string | null;
  operations?: any[];
  // SA任务相关状态
  emergencyReceived?: boolean; // 是否收到临机事件
  lastEmergencyType?: string; // 最后一次临机事件类型
  lastEmergencyTime?: Date; // 最后一次临机事件时间
}

const CommunicationLog: React.FC<CommunicationLogProps> = ({ 
  userId, 
  isStarted = false,
  taskId = null,
  currentTask = 'radar',
  messages: incomingMessages,
  onAddMessage: onAddMessageProp,
  radarRange,
  scanAngle,
  antennaAdjustmentRequired = false,
  targetAntennaElevation,
  initSettings,
  connected = false,
  error = null,
  operations = [],
  emergencyReceived,
  lastEmergencyType,
  lastEmergencyTime
}) => {
  const logContainerRef = useRef<HTMLDivElement>(null);
  const antennaPromptRef = useRef<HTMLDivElement>(null);
  const prevRangeRef = useRef<number | undefined>(undefined);
  const prevAngleRef = useRef<number | undefined>(undefined);
  const prevAntennaAdjustmentRef = useRef<boolean>(false);
  const prevAntennaPromptVisibleRef = useRef<boolean>(false);
  const attentionTimerRef = useRef<number | null>(null);
  const initSettingsProcessedRef = useRef<boolean>(false);
  const prevConnectedRef = useRef<boolean>(false);
  const [antennaPromptAttentionActive, setAntennaPromptAttentionActive] = useState<boolean>(false);
  
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [incomingMessages]);
  
  useEffect(() => {
    if (isStarted && onAddMessageProp) {
      if (radarRange !== undefined && radarRange !== prevRangeRef.current) {
        // onAddMessageProp('system', `雷达范围已设置为: ${radarRange} 海里`);
        prevRangeRef.current = radarRange;
      }
      
      if (scanAngle !== undefined && scanAngle !== prevAngleRef.current) {
        // onAddMessageProp('system', `扫描角度已设置为: ${scanAngle}°`);
        prevAngleRef.current = scanAngle;
      }
    }
  }, [radarRange, scanAngle, isStarted, onAddMessageProp]);
  
  useEffect(() => {
    if (isStarted && initSettings && !initSettingsProcessedRef.current && onAddMessageProp) {
      onAddMessageProp('server', '收到服务器参数设置');
      console.log('initSettings', initSettings);
    
      if (initSettings.range) {
        onAddMessageProp('system', `服务器建议雷达范围: ${initSettings.range} 海里, 扫描角度: ${initSettings.scanAngle}°`);
      }
      initSettingsProcessedRef.current = true;
    }
  }, [initSettings, isStarted, onAddMessageProp]);
  
  useEffect(() => {
    if (isStarted && onAddMessageProp) {
      if (antennaAdjustmentRequired && !prevAntennaAdjustmentRef.current) {
        if (targetAntennaElevation !== undefined) {
          onAddMessageProp('system', `需要调整天线${targetAntennaElevation > 0 ? '上移' : '下移'} ${Math.abs(targetAntennaElevation)}格，请使用b/t键进行调整`);
        } else {
          onAddMessageProp('warning', '重置系统');
        }
        prevAntennaAdjustmentRef.current = true;
      } else if (!antennaAdjustmentRequired && prevAntennaAdjustmentRef.current) {
        onAddMessageProp('success', '天线高度已调整到合适位置');
        prevAntennaAdjustmentRef.current = false;
      }
    }
  }, [antennaAdjustmentRequired, isStarted, targetAntennaElevation, onAddMessageProp]);

  // 在天线提示框出现时，测量其相对整张页面(左上角为原点)的像素坐标并广播一次
  useEffect(() => {
    if (antennaAdjustmentRequired && !prevAntennaPromptVisibleRef.current) {
      const rafId = requestAnimationFrame(() => {
        if (!antennaPromptRef.current) return;
        const rect = antennaPromptRef.current.getBoundingClientRect();
        const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;

        // gazerelation: 坐标统一按物理像素上报（CSS像素 * DPR）
        const left = Math.round(rect.left * dpr);
        const top = Math.round(rect.top * dpr);
        const right = Math.round(rect.right * dpr);
        const bottom = Math.round(rect.bottom * dpr);
        const width = Math.round(rect.width * dpr);
        const height = Math.round(rect.height * dpr);
        // console.log("gazerelation:1111")
        // } else {
        //   const winScreenX = typeof window.screenX === 'number' ? window.screenX : (window as any).screenLeft || 0;
        //   const winScreenY = typeof window.screenY === 'number' ? window.screenY : (window as any).screenTop || 0;
        //   const chromeLeft = Math.max(0, (window.outerWidth - window.innerWidth) / 2);
        //   const chromeTop = Math.max(0, window.outerHeight - window.innerHeight - chromeLeft);
        //   const viewportScreenLeft = winScreenX + chromeLeft;
        //   const viewportScreenTop = winScreenY + chromeTop;
        //   left = viewportScreenLeft + rect.left;
        //   top = viewportScreenTop + rect.top;
        //   right = viewportScreenLeft + rect.right;
        //   bottom = viewportScreenTop + rect.bottom;
        //   console.log("gazerelation:2222")
        // }
        // const left =  rect.left;
        // const top =  rect.top;
        // const right =  rect.right;
        // const bottom =  rect.bottom;
        console.log('gazerelation:rect:physical', { left, top, right, bottom, width, height, dpr });
        window.dispatchEvent(
          new CustomEvent('antenna-prompt-position', {
            detail: {
              x: left,
              y: top,
              left,
              top,
              right,
              bottom,
              width,
              height,
              gazeCoordinateSpace: 'physical',
              gazeDpr: dpr,
              timestamp: Date.now(),
            },
          })
        );
      });

      prevAntennaPromptVisibleRef.current = true;
      return () => cancelAnimationFrame(rafId);
    }

    if (!antennaAdjustmentRequired) {
      prevAntennaPromptVisibleRef.current = false;
    }
  }, [antennaAdjustmentRequired]);

  // 监听外部触发的提醒事件（如 flash_mode），让提示框额外高亮3秒
  useEffect(() => {
    const handleAntennaPromptAttention = (event: Event) => {
      const customEvent = event as CustomEvent<{ mode?: string; durationMs?: number }>;
      const durationMs = customEvent.detail?.durationMs ?? 3000;

      setAntennaPromptAttentionActive(true);
      if (attentionTimerRef.current) {
        window.clearTimeout(attentionTimerRef.current);
      }
      attentionTimerRef.current = window.setTimeout(() => {
        setAntennaPromptAttentionActive(false);
        attentionTimerRef.current = null;
      }, durationMs);
    };

    window.addEventListener('antenna-prompt-attention', handleAntennaPromptAttention as EventListener);
    return () => {
      window.removeEventListener('antenna-prompt-attention', handleAntennaPromptAttention as EventListener);
      if (attentionTimerRef.current) {
        window.clearTimeout(attentionTimerRef.current);
      }
    };
  }, []);
  
  useEffect(() => {
    if (!isStarted || !onAddMessageProp) return;
    
    onAddMessageProp('client', '正在连接到雷达服务器...');
      
    if (userId) {
      onAddMessageProp('system', `飞行员 ${userId} 已登入系统`);
    }
    
  }, [userId, isStarted, onAddMessageProp]);
  
  useEffect(() => {
    if (isStarted && operations && onAddMessageProp) {
      const timeoutOp = operations.find(op => 
        op.operationType === 'settings_validation_timeout' && 
        !op._displayed 
      );
      
      if (timeoutOp) {
        onAddMessageProp('warning', timeoutOp.parameters.message || '服务器响应超时，参数可能不正确');
        timeoutOp._displayed = true;
      }

      const validationOp = operations.find(op => 
        op.operationType === 'settings_validation_received' && 
        !op._displayed
      );

      if (validationOp) {
        const { status, message, settings } = validationOp.parameters;
        if (status === 'success') {
          onAddMessageProp('success', `参数验证成功: ${message}`);
          if (settings) {
            onAddMessageProp('info', `当前参数设置: 范围 ${settings.range} 海里, 扫描角度 ${settings.scanAngle}°`);
          }
        } else {
          // onAddMessageProp('error', `参数验证失败: ${message}`);
        }
        validationOp._displayed = true;
      }
    }
  }, [operations, isStarted, onAddMessageProp]);
  
  const addExternalMessage = useCallback((type: MessageType, content: string) => {
    if (onAddMessageProp) {
      onAddMessageProp(type, content);
    }
  }, [onAddMessageProp]);
  
  const getMessageStyle = (type: MessageType): React.CSSProperties => {
    switch (type) {
      case 'info':        return { color: '#4db87a' };
      case 'warning':     return { color: '#c8a800', fontWeight: 'bold' };
      case 'error':       return { color: '#cc4444', fontWeight: 'bold' };
      case 'success':     return { color: '#00cc55', fontWeight: 'bold' };
      case 'client':      return { color: '#3a9a5a' };
      case 'server':      return { color: '#2a8a4a' };
      case 'system':      return { color: '#00aa44', fontWeight: 'bold' };
      case 'sa_init':     return { color: '#00cc55', fontWeight: 'bold' };
      case 'sa_emergency':return { color: '#cc6633', fontWeight: 'bold' };
      case 'sa_threat':   return { color: '#c8a800', fontWeight: 'bold' };
      case 'sa_missile':  return { color: '#dd2222', fontWeight: 'bold', fontSize: '17px' };
      default:            return { color: '#3a6a44' };
    }
  };
  
  const getMessagePrefix = (type: MessageType): string => {
    switch (type) {
      case 'info': return '信息';
      case 'warning': return '警告';
      case 'error': return '错误';
      case 'success': return '成功';
      case 'client': return '客户端';
      case 'server': return '服务器';
      case 'system': return '系统';
      case 'sa_init': return 'SA系统';
      case 'sa_emergency': return '临机事件';
      case 'sa_threat': return '威胁处理';
      case 'sa_missile': return '导弹来袭';
      default: return '';
    }
  };
  
  const renderRadarParams = () => {
    if (!isStarted || currentTask !== 'radar') return null;
    
    return (
      <div style={{
        padding: '8px 12px',
        marginBottom: '4px',
        background: 'rgba(0,12,5,0.6)',
        borderBottom: '1px solid #0a2010',
      }}>
        <div style={{
          fontSize: '12px',
          letterSpacing: '0.2em',
          color: '#4aaa60',
          textTransform: 'uppercase' as const,
          marginBottom: '8px',
          fontFamily: "'Share Tech Mono', monospace",
        }}>
          ── 雷达参数 ──
        </div>

        {(antennaAdjustmentRequired || antennaPromptAttentionActive || true) && (
          <div
            ref={antennaPromptRef}
            className={antennaPromptAttentionActive ? 'animate-pulse' : ''}
            style={{
              fontFamily: "'Share Tech Mono', monospace",
              fontSize: '22px',
              fontWeight: 'bold',
              letterSpacing: '0.05em',
              color: antennaPromptAttentionActive ? '#ff4444' : '#c8a800',
              background: antennaPromptAttentionActive ? 'rgba(80,0,0,0.3)' : 'transparent',
              border: antennaPromptAttentionActive ? '1px solid #882222' : '1px solid transparent',
              borderRadius: '3px',
              padding: antennaPromptAttentionActive ? '4px 8px' : '0',
            }}
          >
            请调整天线高度{targetAntennaElevation !== undefined ? ` 至 ${targetAntennaElevation}°` : ''}!
          </div>
        )}

        {initSettings && initSettings.settings && (
          <div style={{ marginTop: '8px', paddingTop: '6px', borderTop: '1px solid #0a2010' }}>
            <div style={{
              fontSize: '12px',
              letterSpacing: '0.15em',
              color: '#4aaa60',
              marginBottom: '6px',
              fontFamily: "'Share Tech Mono', monospace",
            }}>
              服务器建议参数
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px' }}>
              {initSettings.settings.range && (
                <div style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '14px' }}>
                  <span style={{ color: '#55aa66' }}>范围 </span>
                  <span style={{ color: '#00aa44' }}>{initSettings.settings.range} 海里</span>
                </div>
              )}
              {initSettings.settings.scanAngle && (
                <div style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '14px' }}>
                  <span style={{ color: '#55aa66' }}>角度 </span>
                  <span style={{ color: '#00aa44' }}>{initSettings.settings.scanAngle}°</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderSAStatus = () => {
    if (!isStarted || currentTask !== 'sa') return null;
    
    const rowStyle: React.CSSProperties = {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'baseline',
      fontFamily: "'Share Tech Mono', monospace",
      fontSize: '14px',
      marginBottom: '3px',
    };
    const labelStyle: React.CSSProperties = { color: '#55aa66' };

    return (
      <div style={{
        padding: '8px 12px',
        marginBottom: '4px',
        background: 'rgba(0,12,5,0.6)',
        borderBottom: '1px solid #0a2010',
      }}>
        <div style={{
          fontSize: '12px',
          letterSpacing: '0.2em',
          color: '#4aaa60',
          textTransform: 'uppercase' as const,
          marginBottom: '8px',
          fontFamily: "'Share Tech Mono', monospace",
        }}>
          ── SA 任务状态 ──
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <div style={rowStyle}>
            <span style={labelStyle}>任务状态</span>
            <span style={{ color: '#00aa44', fontWeight: 'bold' }}>威胁评估中</span>
          </div>

          <div style={rowStyle}>
            <span style={labelStyle}>临机事件</span>
            <span
              className={emergencyReceived ? 'animate-pulse' : ''}
              style={{ color: emergencyReceived ? '#cc4444' : '#55aa66', fontWeight: emergencyReceived ? 'bold' : 'normal' }}
            >
              {emergencyReceived ? '已收到' : '等待中'}
            </span>
          </div>

          {emergencyReceived && lastEmergencyType && (
            <div style={rowStyle}>
              <span style={labelStyle}>事件类型</span>
              <span style={{ color: '#c8a800', fontWeight: 'bold' }}>
                {lastEmergencyType === 'missile' ? '导弹来袭' :
                 lastEmergencyType === 'upgrade' ? '威胁升级' :
                 lastEmergencyType === 'task_updated' ? '威胁任务更新' : lastEmergencyType}
              </span>
            </div>
          )}

          {emergencyReceived && lastEmergencyTime && (
            <div style={rowStyle}>
              <span style={labelStyle}>事件时间</span>
              <span style={{ color: '#4db87a', fontSize: '13px' }}>
                {lastEmergencyTime.toLocaleTimeString()}
              </span>
            </div>
          )}
        </div>

        {emergencyReceived && (
          <div className="animate-pulse" style={{
            marginTop: '8px',
            paddingTop: '6px',
            borderTop: '1px solid #2a1a00',
            fontFamily: "'Share Tech Mono', monospace",
            fontSize: '15px',
            fontWeight: 'bold',
            color: '#cc4444',
          }}>
            ！ 请立即处理临机事件
          </div>
        )}
      </div>
    );
  };
  
  return (
    <div className="flex flex-col h-full">
      {/* ── Status bar ── */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '6px 12px',
        background: 'rgba(0,10,4,0.85)',
        borderBottom: '1px solid #0a2010',
        flexShrink: 0,
      }}>
        <span style={{
          fontFamily: "'Share Tech Mono', monospace",
          fontSize: '12px',
          letterSpacing: '0.22em',
          color: '#4aaa60',
          textTransform: 'uppercase',
        }}>
          系统通信日志
        </span>
        <span style={{
          fontFamily: "'Share Tech Mono', monospace",
          fontSize: '13px',
          color: isStarted ? '#00cc55' : '#c8a800',
          fontWeight: 'bold',
        }}>
          {isStarted ? '● 已连接' : '○ 等待启动'}
        </span>
      </div>

      {/* ── User / Task info ── */}
      {(userId || taskId !== null) && (
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          padding: '4px 12px',
          background: 'rgba(0,6,2,0.5)',
          borderBottom: '1px solid #051008',
          flexShrink: 0,
        }}>
          {userId && (
            <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '14px', color: '#55bb70' }}>
              飞行员 {userId}
            </span>
          )}
          {taskId !== null && (
            <span style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: '14px', color: '#55bb70' }}>
              任务 {taskId}
            </span>
          )}
        </div>
      )}

      {renderRadarParams()}

      {renderSAStatus()}

      {/* ── Log feed ── */}
      <div
        ref={logContainerRef}
        className="flex-1 overflow-y-auto mb-10"
        style={{ padding: '8px 12px', background: 'rgba(0,4,2,0.9)' }}
      >
        {!isStarted ? (
          <div style={{
            textAlign: 'center',
            paddingTop: '40px',
            fontFamily: "'Share Tech Mono', monospace",
            fontSize: '15px',
            color: '#4a9a55',
            letterSpacing: '0.1em',
        }}>
          等待系统启动...
          </div>
        ) : (
          incomingMessages.map(msg => {
            const style = getMessageStyle(msg.type);
            const isMissile = msg.type === 'sa_missile';
            return (
              <div
                key={msg.id}
                className={isMissile ? 'animate-pulse' : ''}
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'max-content max-content 1fr',
                  gap: '6px',
                  alignItems: 'baseline',
                  marginBottom: '5px',
                  fontFamily: "'Share Tech Mono', monospace",
                  fontSize: style.fontSize ?? '15px',
                  lineHeight: '1.55',
                }}
              >
                <span style={{ color: '#55aa66', fontSize: '13px' }}>
                  {msg.timestamp.toLocaleTimeString('zh-CN', { hour12: false })}
                </span>
                <span style={{ ...style, opacity: 0.8 }}>
                  [{getMessagePrefix(msg.type)}]
                </span>
                <span style={style}>
                  {msg.content}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

export default CommunicationLog;
