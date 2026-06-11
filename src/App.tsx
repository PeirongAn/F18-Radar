import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import Radar from './components/Radar';
import AIAssistant from './components/AIAssistant';
import SAPage from './components/SAPage';
import CommunicationLog, { LogMessage, MessageType } from './components/CommunicationLog';
import ThreatList from './components/ThreatList';
import useRadarData, { globalWS } from './hooks/useRadarData';
import { observer } from 'mobx-react-lite';
import { useStore } from './stores/StoreProvider';
import agentStore from './stores/AgentStore';
import audioManager from './managers/AudioManager';
import { Toaster } from 'react-hot-toast';
import QuestionnaireModal, { QuestionnaireModalHandle, QuestionnaireSubmitData } from './components/QuestionnaireModal.tsx';
import InitialFormModal from './components/InitialFormModal';
import TrustCalibrationSettings from './components/TrustCalibrationSettings';
import { SensorTrustDecision, ThreatTrustDecision } from './types/trustCalibration';
interface TargetSelectParams {
  targetId: string | undefined;
  lockX?: number;
  iffMode?: boolean;
  externalTargetsTimestamp?: number | null;
  event_owner?: 'AI' | 'manual';
  extra?: Record<string, unknown>;
}

type TaskType = 'RADAR_TARGETING' | 'SA_THREAT_RESPONSE' | 'PLATFORM_CONTROL' | 'WEAPON_FIRING';
type ThreatTrustActions = {
  markEvidenceViewed: () => void;
  markManualReviewDone: () => void;
};
type SensorTrustActions = {
  markEvidenceViewed: () => void;
  markManualReviewDone: () => void;
};

function translateDifficulty(d: string): string {
  switch (d) {
    case 'low':
    case '3':
      return '低';
    case 'medium':
    case '2':
      return '中';
    case 'high':
    case '1':
      return '高';
    default:       return d;
  }
}

const Sep: React.FC = () => <div className="status-divider" />;

const StatusItem: React.FC<{
  label: string;
  value: React.ReactNode;
  valueStyle?: React.CSSProperties;
}> = ({ label, value, valueStyle }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '0 16px' }}>
    <span style={{ color: '#4a9a62', fontSize: '13px', letterSpacing: '0.1em' }}>{label}</span>
    <span style={{ color: '#00ee77', fontSize: '16px', letterSpacing: '0.06em', ...valueStyle }}>{value}</span>
  </div>
);

const ProgressBadge: React.FC<{ current: number; total: number }> = ({ current, total }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '0 16px' }}>
    <span style={{ color: '#4a9a62', fontSize: '13px', letterSpacing: '0.1em' }}>进度</span>
    <div style={{
      display: 'flex', alignItems: 'center', gap: '2px',
      background: 'rgba(0, 200, 80, 0.10)',
      border: '1px solid #1e6e3a',
      borderRadius: '3px',
      padding: '2px 10px',
    }}>
      <span style={{ color: '#00ff88', fontSize: '16px', fontWeight: 700, letterSpacing: '0.05em', fontFamily: "'Share Tech Mono', monospace" }}>{current}</span>
      <span style={{ color: '#2a6a40', fontSize: '14px', margin: '0 3px' }}>/</span>
      <span style={{ color: '#00bb55', fontSize: '16px', letterSpacing: '0.05em', fontFamily: "'Share Tech Mono', monospace" }}>{total}</span>
    </div>
  </div>
);

const SidebarThreatTrustPanel: React.FC<{
  decision: ThreatTrustDecision;
  actions: ThreatTrustActions | null;
}> = ({ decision, actions }) => {
  const isReview = decision.controlLevel === 'review';
  const reviewComplete = decision.evidenceViewed || decision.manualReviewDone;
  const accent = reviewComplete ? '#00ff88' : isReview ? '#ff9f35' : '#2dd8ff';
  const muted = '#75b987';
  const title = reviewComplete
    ? '复核已完成，可继续确认'
    : decision.primaryMessage || (isReview ? '排序不稳定：需人工确认' : 'AI 推荐需要解释');

  return (
    <div style={{
      flexShrink: 0,
      padding: '14px 18px',
      borderBottom: '1px solid #0a2010',
      background: 'rgba(0,24,12,0.72)',
    }}>
      <div className="panel-label" style={{ color: accent }}>AI 排序解释</div>
      <div style={{
        border: `1px solid ${reviewComplete ? 'rgba(0,255,136,0.85)' : isReview ? 'rgba(255,159,53,0.85)' : 'rgba(45,216,255,0.75)'}`,
        borderRadius: '4px',
        background: reviewComplete ? 'rgba(0,42,18,0.46)' : isReview ? 'rgba(42,20,2,0.52)' : 'rgba(0,30,28,0.5)',
        boxShadow: `0 0 18px ${reviewComplete ? 'rgba(0,255,136,0.12)' : isReview ? 'rgba(255,159,53,0.10)' : 'rgba(45,216,255,0.10)'}`,
        padding: '12px 14px',
        fontFamily: "'Share Tech Mono', 'SimHei', 'Microsoft YaHei', monospace",
      }}>
        <div style={{
          color: accent,
          fontSize: '15px',
          fontWeight: 700,
          letterSpacing: '0.08em',
          marginBottom: '8px',
        }}>
          {title}
        </div>

        {decision.changeText && (
          <div style={{ color: '#00d777', fontSize: '12px', marginBottom: '6px' }}>
            {decision.changeText}
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '5px 10px', fontSize: '12px', lineHeight: 1.45 }}>
          {typeof decision.scoreGap === 'number' && (
            <>
              <span style={{ color: muted }}>第一/第二分差</span>
              <span style={{ color: decision.rankingUnstable ? '#ffd55c' : '#9effb5' }}>
                {decision.scoreGap.toFixed(2)}{decision.rankingUnstable ? ' ≈' : ''}
              </span>
            </>
          )}
          {typeof decision.dataDelayMs === 'number' && decision.triggers.includes('data_delay') && (
            <>
              <span style={{ color: muted }}>数据延迟</span>
              <span style={{ color: '#ffd55c' }}>{Math.round(decision.dataDelayMs)}ms</span>
            </>
          )}
          <span style={{ color: muted }}>复核状态</span>
          <span style={{ color: decision.evidenceViewed || decision.manualReviewDone ? '#9effb5' : '#ffd55c' }}>
            {decision.manualReviewDone ? '已人工确认' : decision.evidenceViewed ? '已查看证据' : '待复核'}
          </span>
        </div>

        {decision.candidates.length > 0 && (
          <div style={{ marginTop: '10px', borderTop: '1px solid rgba(80,170,100,0.2)', paddingTop: '8px' }}>
            {decision.candidates.slice(0, 3).map((candidate, index) => (
              <div key={candidate.id} style={{
                display: 'flex',
                justifyContent: 'space-between',
                gap: '10px',
                color: index === 0 ? '#eaffef' : '#c7c16b',
                fontSize: '12px',
                lineHeight: 1.5,
              }}>
                <span>#{index + 1} {candidate.label}</span>
                <span>{candidate.score.toFixed(2)}</span>
              </div>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', gap: '10px', marginTop: '12px' }}>
          <button
            type="button"
            onClick={actions?.markEvidenceViewed}
            disabled={!actions || decision.evidenceViewed}
            style={{
              flex: 1,
              height: '32px',
              background: decision.evidenceViewed ? 'rgba(0,62,28,0.8)' : 'rgba(0,40,16,0.7)',
              border: `1px solid ${decision.evidenceViewed ? '#00d46e' : '#158a42'}`,
              color: decision.evidenceViewed ? '#d6ffe4' : '#73ff9a',
              borderRadius: '3px',
              cursor: actions && !decision.evidenceViewed ? 'pointer' : 'not-allowed',
              fontFamily: 'inherit',
            }}
          >
            {decision.evidenceViewed ? '已查看证据' : '查看证据'}
          </button>
          <button
            type="button"
            onClick={actions?.markManualReviewDone}
            disabled={!actions || decision.manualReviewDone}
            style={{
              flex: 1,
              height: '32px',
              background: decision.manualReviewDone ? 'rgba(0,62,28,0.8)' : isReview ? 'rgba(90,42,0,0.65)' : 'rgba(0,45,45,0.65)',
              border: `1px solid ${decision.manualReviewDone ? '#00d46e' : accent}`,
              color: decision.manualReviewDone ? '#d6ffe4' : isReview ? '#ffd18c' : '#9cf6ff',
              borderRadius: '3px',
              cursor: actions && !decision.manualReviewDone ? 'pointer' : 'not-allowed',
              fontFamily: 'inherit',
            }}
          >
            {decision.manualReviewDone ? '已人工确认' : '人工确认'}
          </button>
        </div>
      </div>
    </div>
  );
};

const SidebarSensorTrustPanel: React.FC<{
  decision: SensorTrustDecision;
  actions: SensorTrustActions | null;
}> = ({ decision, actions }) => {
  const isReview = decision.controlLevel === 'review';
  const reviewComplete = decision.evidenceViewed || decision.manualReviewDone;
  const reviewStarted = decision.manualReviewRequested && !decision.manualReviewDone;
  const accent = reviewComplete ? '#00ff88' : isReview ? '#ff9f35' : '#2dd8ff';
  const title = reviewComplete
    ? '复核已完成，可继续确认'
    : reviewStarted
      ? '人工复核模式：请重新选择或确认目标'
      : decision.primaryMessage || '低置信建议：需要人工复核';
  const confidencePercent = typeof decision.confidence === 'number'
    ? Math.round(decision.confidence * 100)
    : undefined;
  const thresholdPercent = decision.configSnapshot.low_confidence_max !== undefined
    ? Math.round(decision.configSnapshot.low_confidence_max * 100)
    : 70;
  const counterCandidate = decision.candidates.find(candidate => candidate.id !== decision.aiTargetId);
  const uncertaintyItems = [
    decision.triggers.includes('low_confidence') && confidencePercent !== undefined
      ? `低置信：${confidencePercent}% < ${thresholdPercent}%`
      : null,
    decision.triggers.includes('candidate_close')
      ? '相似候选存在：建议比较后再锁定'
      : null,
    decision.triggers.includes('iff_unconfirmed') || decision.iffPending
      ? 'IFF未确认：敌我身份未完成核验'
      : null,
    decision.triggers.includes('direct_accept_without_evidence')
      ? '连续直接接受：尚未查看证据'
      : null,
  ].filter((item): item is string => Boolean(item));

  return (
    <div style={{
      flexShrink: 0,
      padding: '14px 18px',
      borderBottom: '1px solid #0a2010',
      background: 'rgba(0,24,12,0.72)',
    }}>
      <div style={{
        border: `1px solid ${reviewComplete ? 'rgba(0,255,136,0.85)' : isReview ? 'rgba(255,159,53,0.9)' : 'rgba(45,216,255,0.75)'}`,
        borderRadius: '6px',
        background: reviewComplete ? 'rgba(0,42,18,0.46)' : isReview ? 'rgba(56,24,0,0.58)' : 'rgba(0,30,36,0.52)',
        boxShadow: `0 0 18px ${reviewComplete ? 'rgba(0,255,136,0.12)' : isReview ? 'rgba(255,159,53,0.12)' : 'rgba(45,216,255,0.10)'}`,
        padding: '14px 16px',
        fontFamily: "'Share Tech Mono', 'SimHei', 'Microsoft YaHei', monospace",
      }}>
        <div className="panel-label" style={{ color: accent }}>
          {isReview ? '低置信建议复核' : 'AI 目标锁定解释'}
        </div>
        <div style={{ color: accent, fontSize: '15px', fontWeight: 700, letterSpacing: '0.08em', marginBottom: 10 }}>
          {title}
        </div>
        <div style={{ color: reviewComplete ? '#9effb5' : '#ffd55c', fontSize: 12, lineHeight: 1.7 }}>
          复核状态：{decision.manualReviewDone ? '已人工复核' : decision.evidenceViewed ? '已查看证据' : reviewStarted ? '复核模式中' : '待复核'}
        </div>
        {typeof decision.confidence === 'number' && (
          <div style={{ color: '#b8f7c2', fontSize: 12, lineHeight: 1.7 }}>
            AI锁定 {decision.aiTargetId} / 置信度 {confidencePercent}%
          </div>
        )}
        {isReview && decision.evidenceViewed && (
          <div style={{ marginTop: 10, borderTop: '1px solid rgba(255,159,53,0.25)', paddingTop: 9 }}>
            <div style={{ color: '#ffbd73', fontSize: 12, fontWeight: 700, marginBottom: 5 }}>不确定性来源</div>
            {uncertaintyItems.length > 0 ? uncertaintyItems.map(item => (
              <div key={item} style={{ color: '#ffe0b2', fontSize: 12, lineHeight: 1.55 }}>· {item}</div>
            )) : (
              <div style={{ color: '#ffe0b2', fontSize: 12, lineHeight: 1.55 }}>· 当前建议存在复核风险</div>
            )}
            <div style={{ color: '#775f42', fontSize: 11, lineHeight: 1.45, marginTop: 4 }}>
              航迹交叉、信号干扰检测：待接入
            </div>
          </div>
        )}
        {counterCandidate && decision.evidenceViewed && (
          <div style={{
            marginTop: 9,
            border: `1px solid ${isReview ? 'rgba(255,159,53,0.35)' : 'rgba(45,216,255,0.25)'}`,
            background: isReview ? 'rgba(52,28,0,0.36)' : 'rgba(0,26,34,0.32)',
            padding: '8px 10px',
            borderRadius: 4,
            color: '#e9ffef',
            fontSize: 12,
            lineHeight: 1.55,
          }}>
            反证提示：{counterCandidate.label} 置信度 {(counterCandidate.confidence * 100).toFixed(0)}% 接近，建议比较后再锁定。
          </div>
        )}
        {isReview && decision.blockedOneClick && !reviewComplete && !reviewStarted && (
          <div style={{ color: '#ffdf73', fontSize: 12, lineHeight: 1.6, marginTop: 8 }}>
            低于阈值 {thresholdPercent}% 或候选接近：禁止一键接受自动锁定。
          </div>
        )}
        {isReview && !decision.evidenceViewed && !reviewComplete && (
          <div style={{ color: '#9cf6ff', fontSize: 12, lineHeight: 1.6, marginTop: 8 }}>
            点击“查看证据”展开候选对比、置信度来源和不确定性来源。
          </div>
        )}
        {decision.evidenceViewed && (
          <div style={{ marginTop: 8 }}>
            {decision.candidates.slice(0, 3).map((candidate, index) => (
              <div key={candidate.id} style={{ color: index === 0 ? '#eaffef' : '#c7c16b', fontSize: 12, lineHeight: 1.55 }}>
                #{index + 1} {candidate.label} {(candidate.confidence * 100).toFixed(0)}% · {candidate.reason}
              </div>
            ))}
          </div>
        )}
        <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
          <button
            type="button"
            onClick={actions?.markManualReviewDone}
            disabled={!actions || reviewStarted || decision.manualReviewDone}
            style={{
              flex: 1,
              height: 32,
              background: decision.manualReviewDone ? 'rgba(0,62,28,0.8)' : reviewStarted ? 'rgba(70,52,0,0.72)' : 'rgba(86,44,0,0.72)',
              border: `1px solid ${decision.manualReviewDone ? '#00d46e' : reviewStarted ? '#ffdf73' : '#c69024'}`,
              color: decision.manualReviewDone ? '#d6ffe4' : reviewStarted ? '#ffdf73' : '#ffd37a',
              borderRadius: 3,
              cursor: actions && !reviewStarted && !decision.manualReviewDone ? 'pointer' : 'not-allowed',
              fontFamily: 'inherit',
            }}
          >
            {decision.manualReviewDone ? '已人工复核' : reviewStarted ? '复核模式中' : '人工复核'}
          </button>
          <button
            type="button"
            onClick={actions?.markEvidenceViewed}
            disabled={!actions || decision.evidenceViewed}
            style={{
              flex: 1,
              height: 32,
              background: decision.evidenceViewed ? 'rgba(0,62,28,0.8)' : 'rgba(0,45,56,0.7)',
              border: `1px solid ${decision.evidenceViewed ? '#00d46e' : '#16a4c8'}`,
              color: decision.evidenceViewed ? '#d6ffe4' : '#9cf6ff',
              borderRadius: 3,
              cursor: actions && !decision.evidenceViewed ? 'pointer' : 'not-allowed',
              fontFamily: 'inherit',
            }}
          >
            {decision.evidenceViewed ? '已查看证据' : '查看证据'}
          </button>
        </div>
      </div>
    </div>
  );
};

/* ══════════════════════════════════════════════════════
   App
══════════════════════════════════════════════════════ */
const App: React.FC = observer(() => {
  const [selectedTarget] = useState<string | null>(null);
  const [userId, setUserId] = useState<string>('');
  const [includeAI, setIncludeAI] = useState<boolean>(false);
  const [defaultTaskNumber, setDefaultTaskNumber] = useState<number | undefined>(undefined);
  const [isStarted, setIsStarted] = useState<boolean>(false);
  const [useJoystick, setUseJoystick] = useState<boolean>(false);
  const [showTrustSettings, setShowTrustSettings] = useState<boolean>(false);
  const joystickInitedRef = useRef<boolean>(false);
  const lastStartRequestRef = useRef<{ key: string; timestamp: number } | null>(null);
  const [radarRange, setRadarRange] = useState<number>(20);
  const [scanAngle, setScanAngle] = useState<number>(60);

  // 显示模式由后台指令驱动，不提供手动切换入口
  const [activeDisplay, setActiveDisplay] = useState<'radar' | 'sa'>('radar');

  // SA 临机事件状态
  const [emergencyReceived, setEmergencyReceived] = useState<boolean>(false);
  const [lastEmergencyType, setLastEmergencyType] = useState<string>('');
  const [lastEmergencyTime, setLastEmergencyTime] = useState<Date | undefined>(undefined);
  const lastEmergencyIdRef = useRef<string>('');

  // 威胁列表
  const [threatListData, setThreatListData] = useState<any[]>([]);
  const [showDetailedInfo, setShowDetailedInfo] = useState(false);
  const [sensorTrustDecision, setSensorTrustDecision] = useState<SensorTrustDecision | null>(null);
  const [sensorTrustActions, setSensorTrustActions] = useState<SensorTrustActions | null>(null);
  const [saTrustDecision, setSaTrustDecision] = useState<ThreatTrustDecision | null>(null);
  const [saTrustActions, setSaTrustActions] = useState<ThreatTrustActions | null>(null);

  // 问卷弹出控制：外部可通过 WebSocket 消息 { type:'set_questionnaire_popup', enabled:bool } 修改
  const [enableQuestionnairePopup, setEnableQuestionnairePopup] = useState<boolean>(true);
  const questionnaireRef = useRef<QuestionnaireModalHandle>(null);
  const questionnaireEligibilityRef = useRef<Record<TaskType, { isAIActive: boolean; isPractice: boolean } | null>>({
    RADAR_TARGETING: null,
    SA_THREAT_RESPONSE: null,
    PLATFORM_CONTROL: null,
    WEAPON_FIRING: null,
  });
  const shownQuestionnairesRef = useRef<Set<string>>(new Set());
  const shownCompletionNoticeRef = useRef<Set<string>>(new Set());
  const aiSelectedTargetRef = useRef<string | undefined>(undefined);

  const { radarStore } = useStore();
  const { antennaAdjustmentRequired, targetAntennaElevation } = radarStore;

  const {
    connected,
    error,
    taskId,
    initSettings,
    operations,
    sendMessage,
    initializeSystem,
    sendResetSA,
    repetitionInfos,
    platformAutoStart,
    lastMessage,
  } = useRadarData();

  const [messages, setMessages] = useState<LogMessage[]>([]);
  const [completionNoticeTask, setCompletionNoticeTask] = useState<TaskType | null>(null);
  const messageIdRef = useRef(0);

  const addMessage = useCallback((type: MessageType, content: string) => {
    setMessages(prev => [
      ...prev,
      { id: `msg_${Date.now()}_${++messageIdRef.current}`, type, content, timestamp: new Date() },
    ]);
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    messageIdRef.current = 0;
  }, []);

  useEffect(() => {
    radarStore.setUserId(userId);
  }, [userId, radarStore]);

  useEffect(() => {
    (['RADAR_TARGETING', 'SA_THREAT_RESPONSE', 'PLATFORM_CONTROL', 'WEAPON_FIRING'] as TaskType[]).forEach(taskType => {
      const info = repetitionInfos[taskType];
      if (!info || typeof info === 'string') return;
      questionnaireEligibilityRef.current[taskType] = {
        isAIActive: !!(info as any).is_ai_active,
        isPractice: !!(info as any).is_practice,
      };
    });
  }, [repetitionInfos]);

  const canShowQuestionnaire = useCallback((taskType: TaskType, source?: any) => {
    const fallback = questionnaireEligibilityRef.current[taskType];
    const isAIActive = typeof source?.is_ai_active === 'boolean'
      ? source.is_ai_active
      : fallback?.isAIActive;
    const isPractice = typeof source?.is_practice === 'boolean'
      ? source.is_practice
      : fallback?.isPractice;
    return enableQuestionnairePopup && isAIActive === true && isPractice === false;
  }, [enableQuestionnairePopup]);

  const showQuestionnaireForTask = useCallback((taskType: TaskType, source?: any) => {
    if (!canShowQuestionnaire(taskType, source)) return;
    const key = `${taskType}::AI_FORMAL_COMPLETED`;
    if (shownQuestionnairesRef.current.has(key)) return;
    shownQuestionnairesRef.current.add(key);
    questionnaireRef.current?.show(taskType);
  }, [canShowQuestionnaire]);

  const showCompletionNoticeForTask = useCallback((taskType: TaskType, source?: any) => {
    if (canShowQuestionnaire(taskType, source)) return;
    const key = `${taskType}::NO_QUESTIONNAIRE_COMPLETED`;
    if (shownCompletionNoticeRef.current.has(key)) return;
    shownCompletionNoticeRef.current.add(key);
    setCompletionNoticeTask(taskType);
  }, [canShowQuestionnaire]);

  /* ── 监听后台指令切换显示模式 ─────────────────────
     后台可发送以下消息驱动切换：
       { type: 'SwitchSA', ... }      → 切换到威胁排序
       { type: 'SwitchRadar', ... }   → 切换到传感器任务
  ───────────────────────────────────────────────── */
  useEffect(() => {
    if (!lastMessage) return;
    if (lastMessage.type === 'SwitchSA') {
      setActiveDisplay('sa');
      addMessage('system', '后台指令：切换至威胁排序任务');
    } else if (lastMessage.type === 'SwitchRadar') {
      setActiveDisplay('radar');
      addMessage('system', '后台指令：切换至传感器任务');
    }
  }, [lastMessage, addMessage]);

  /* ── 监听问卷弹窗外部控制指令 ────────────────────
     服务端可发送：
       { type: 'set_questionnaire_popup', enabled: bool }  → 开关自动弹出
       { type: 'show_questionnaire', task_type?: string }  → 兼容旧服务端；
      只有对应任务类型已完成，且为 AI 正式模式时才会弹出。
  ───────────────────────────────────────────────── */
  useEffect(() => {
    if (!lastMessage) return;
    if (lastMessage.type === 'set_questionnaire_popup') {
      setEnableQuestionnairePopup(!!lastMessage.enabled);
    } else if (lastMessage.type === 'show_questionnaire') {
      const taskType = lastMessage.task_type as TaskType | undefined;
      if (taskType && repetitionInfos[taskType] === 'ALL_COMPLETED') {
        showQuestionnaireForTask(taskType, lastMessage);
      }
    }
  }, [lastMessage, repetitionInfos, showQuestionnaireForTask]);

  /* ── 每个任务类型完成后：AI正式模式弹问卷；其它模式显示结束提示 ── */
  useEffect(() => {
    if (repetitionInfos.RADAR_TARGETING === 'ALL_COMPLETED') {
      const source = lastMessage?.task_type === 'RADAR_TARGETING' ? lastMessage : undefined;
      showQuestionnaireForTask('RADAR_TARGETING', source);
      showCompletionNoticeForTask('RADAR_TARGETING', source);
    }
    if (repetitionInfos.SA_THREAT_RESPONSE === 'ALL_COMPLETED') {
      const source = lastMessage?.task_type === 'SA_THREAT_RESPONSE' ? lastMessage : undefined;
      showQuestionnaireForTask('SA_THREAT_RESPONSE', source);
      showCompletionNoticeForTask('SA_THREAT_RESPONSE', source);
    }
  }, [repetitionInfos.RADAR_TARGETING, repetitionInfos.SA_THREAT_RESPONSE, lastMessage, showQuestionnaireForTask, showCompletionNoticeForTask]);

  /* ── 监听 SA 临机事件 ─────────────────────────── */
  useEffect(() => {
    if (!lastMessage) return;
    const messageId = JSON.stringify({
      type: lastMessage.type,
      timestamp: lastMessage.timestamp || Date.now(),
      event: lastMessage.event,
    });
    if (messageId !== lastEmergencyIdRef.current && lastMessage.type === 'SAEmergency') {
      setEmergencyReceived(true);
      setLastEmergencyType(lastMessage.event || 'unknown');
      setLastEmergencyTime(new Date());
      lastEmergencyIdRef.current = messageId;
      const eventText = lastMessage.event === 'missile' ? '导弹来袭'
        : lastMessage.event === 'upgrade' ? '威胁升级' : '未知事件';
      addMessage('sa_emergency', `收到临机事件：${eventText}`);
    }
  }, [lastMessage, addMessage]);

  /* ── 目标选择 ─────────────────────────────────── */
  const handleTargetSelect = useCallback((params: TargetSelectParams) => {
    if (params.event_owner === 'AI') {
      aiSelectedTargetRef.current = params.targetId;
    }
    const isManualRepeatOfAITarget =
      agentStore.isAIActive &&
      params.event_owner === 'manual' &&
      params.targetId &&
      params.targetId === aiSelectedTargetRef.current;

    radarStore.setLockedTargetId(params.targetId);
    if (params.targetId && params.lockX !== undefined) {
      radarStore.setLockScreenX(params.lockX);
    } else {
      radarStore.setLockScreenX(undefined);
    }
    if (params.targetId) {
      const payload: Record<string, unknown> = {
        type: 'target_selected',
        timestamp: Date.now(),
        target_id: params.targetId,
        action: 'select',
        event_owner: params.event_owner,
      };
      if (params.iffMode !== undefined) payload.iff_mode = params.iffMode;
      if (params.externalTargetsTimestamp != null) payload.receive_timestamp = params.externalTargetsTimestamp;
      if (params.extra) payload.extra = params.extra;
      if (!isManualRepeatOfAITarget) {
        sendMessage?.(payload);
      }
    }
  }, [sendMessage, radarStore]);

  /* ── 启动应用 ─────────────────────────────────── */
  const handleStartApp = useCallback((
    id: string,
    withAI: boolean,
    taskType: 'radar' | 'sa',
    practice: boolean,
    _useJoystick: boolean,
    taskNumber?: number,
  ) => {
    const startKey = `${id}::${taskType}::${withAI ? 'ai' : 'manual'}::${practice ? 'practice' : 'formal'}::${taskNumber ?? 'default'}`;
    const now = Date.now();
    const lastStart = lastStartRequestRef.current;
    if (lastStart?.key === startKey && now - lastStart.timestamp < 1000) {
      console.warn('[App] Ignored duplicate task start request:', startKey);
      return;
    }
    lastStartRequestRef.current = { key: startKey, timestamp: now };

    setUserId(id);
    setIncludeAI(withAI);
    setUseJoystick(_useJoystick);
    joystickInitedRef.current = false;
    radarStore.startSystem(id, withAI, practice, taskNumber);
    agentStore.setAIActive(withAI);
    setIsStarted(true);

    if (taskType === 'sa') {
      setActiveDisplay('sa');
      sendMessage?.({
        type: 'SwitchSA',
        timestamp: Date.now(),
        user_id: id,
        is_practice: practice,
        is_ai_active: withAI,
        task_number: taskNumber,
        repetition_total_override: taskNumber,
      });
    } else {
      setActiveDisplay('radar');
      initializeSystem(id, withAI, practice, taskNumber);
    }
  }, [sendMessage, initializeSystem, radarStore]);

  /* ── 任务启动后自动连接操纵杆 ────────────────────── */
  useEffect(() => {
    if (!isStarted || !useJoystick || !userId || !connected) return;
    if (joystickInitedRef.current) return;
    joystickInitedRef.current = true;
    globalWS.sendMessage({ type: 'joystick_connect', timestamp: Date.now(), user_id: userId });
    globalWS.sendMessage({ type: 'joystick_subscribe', timestamp: Date.now(), user_id: userId });
  }, [isStarted, connected, useJoystick, userId]);

  /* ── 启动弹窗默认任务次数：从 init_config.json 读取 ── */
  useEffect(() => {
    let cancelled = false;
    fetch('/init_config.json', { cache: 'no-store' })
      .then(res => (res.ok ? res.json() : null))
      .then(cfg => {
        if (cancelled || !cfg) return;
        const parsed = Number(cfg.taskNumber);
        if (Number.isFinite(parsed) && parsed > 0) {
          setDefaultTaskNumber(Math.min(100, Math.max(1, Math.floor(parsed))));
        }
      })
      .catch(() => { /* 读取失败时回退到弹窗内置默认值 */ });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!platformAutoStart) return;
    handleStartApp(
      platformAutoStart.userId,
      platformAutoStart.includeAI,
      platformAutoStart.taskType,
      platformAutoStart.isPractice,
      false,
      platformAutoStart.taskNumber,
    );
  }, [platformAutoStart, handleStartApp]);

  const handleStartFromModal = useCallback((
    id: string,
    withAI: boolean,
    taskType: 'radar' | 'sa',
    practice: boolean,
    modalUseJoystick: boolean,
    taskNumber: number,
  ) => {
    audioManager.unlock();
    handleStartApp(id, withAI, taskType, practice, modalUseJoystick, taskNumber);
  }, [handleStartApp]);

  /* ── 雷达参数更新 ─────────────────────────────── */
  const handleRadarParamsUpdate = useCallback((range: number, angle: number) => {
    setRadarRange(range);
    setScanAngle(angle);
    radarStore.updateRadarParams(range, angle);
  }, [radarStore]);

  const handleRadarTaskCompleted = useCallback(() => {
    const source = {
      is_ai_active: agentStore.isAIActive,
      is_practice: radarStore.isPractice,
    };
    showQuestionnaireForTask('RADAR_TARGETING', source);
    showCompletionNoticeForTask('RADAR_TARGETING', source);
  }, [radarStore, showQuestionnaireForTask, showCompletionNoticeForTask]);

  /* ── SA 查看结果确认回调保留给页面流程；问卷由任务类型完成状态统一控制 ── */
  const handleSAResultConfirmed = useCallback(() => {}, []);

  /* ── SA 重置 ──────────────────────────────────── */
  const handleSATaskReset = useCallback(() => {
    setEmergencyReceived(false);
    setLastEmergencyType('');
    setLastEmergencyTime(undefined);
    lastEmergencyIdRef.current = '';
    clearMessages();
    sendResetSA();
  }, [sendResetSA, clearMessages]);

  /* ── 威胁列表 ─────────────────────────────────── */
  const handleThreatListUpdate = useCallback((threatData: any[]) => {
    setThreatListData(threatData);
  }, []);

  const handleShowDetailedInfoChange = useCallback((showDetailed: boolean) => {
    setShowDetailedInfo(showDetailed);
  }, []);

  /* ── 当前任务信息 ──────────────────────────────── */
  const infoToShow = useMemo(() => {
    const key = activeDisplay === 'sa' ? 'SA_THREAT_RESPONSE' : 'RADAR_TARGETING';
    const taskType = activeDisplay === 'sa' ? 'SA_THREAT_RESPONSE' as const : 'RADAR_TARGETING' as const;
    const info = repetitionInfos[key];
    if (!info || typeof info === 'string') return null;
    return {
      ...info,
      task_type: taskType,
      difficulty: (info as any).difficulty as string | undefined,
      is_practice: (info as any).is_practice as boolean | undefined,
      is_ai_active: (info as any).is_ai_active as boolean | undefined,
      autonomy_level: (info as any).autonomy_level as string | undefined,
    };
  }, [activeDisplay, repetitionInfos]);

  /* ── 右侧标签文字 ─────────────────────────────── */
  const displayLabel = activeDisplay === 'sa' ? '威胁排序任务 · 态势感知' : '传感器任务 · 目标识别';

  /* ── 策略说明链接 ─────────────────────────────── */
  const rulesHref = activeDisplay === 'sa'
    ? '/threat_calculation_rules.html'
    : '/radar_target_identification.html';

  /* ════════════════════════════════════════════════════
     Render
  ════════════════════════════════════════════════════ */
  return (
    <div
      className="scanlines"
      style={{
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        background: '#030a05',
        fontFamily: "'SimHei', 'Microsoft YaHei', 'Noto Sans SC', 'PingFang SC', 'FangSong', sans-serif",
      }}
    >
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: '#071209',
            color: '#00ff88',
            border: '1px solid #0d3018',
            fontFamily: "'SimHei', 'Microsoft YaHei', 'Noto Sans SC', sans-serif",
            fontSize: '12px',
          },
        }}
      />
      {/* ── Startup Modal ──────────────────────────────── */}
      {!isStarted && !showTrustSettings && (
        <InitialFormModal
          onStart={handleStartFromModal}
          defaultUserId={userId}
          defaultIncludeAI={includeAI}
          defaultTaskNumber={defaultTaskNumber}
          onOpenTrustSettings={() => setShowTrustSettings(true)}
        />
      )}

      {/* ── Top Status Bar ─────────────────────────────── */}
      <header style={{
        height: '58px', flexShrink: 0,
        display: 'flex', alignItems: 'center',
        background: 'rgba(6, 20, 11, 0.98)',
        borderBottom: '1px solid #0e3018',
        boxShadow: '0 1px 0 rgba(0,255,80,0.08)',
      }}>
        {/* 系统名 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '0 16px' }}>
          <span
            className="glow-green"
            style={{
              fontFamily: "'Share Tech Mono', 'Microsoft YaHei', monospace",
              color: '#00ff55', fontSize: '19px', fontWeight: 700, letterSpacing: '0.18em',
            }}
          >
            ◈ JF-17 AEMS
          </span>
        </div>

        <Sep />

        {/* 连接状态 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '7px', padding: '0 14px' }}>
          <span
            className={connected ? 'pulse-dot' : 'blink'}
            style={{
              display: 'inline-block', width: '7px', height: '7px', borderRadius: '50%',
              background: connected ? '#00ff55' : '#ff4444',
              color: connected ? '#00ff55' : '#ff4444',
            }}
          />
          <span style={{ fontSize: '14px', letterSpacing: '0.12em', color: connected ? '#00cc55' : '#dd3333' }}>
            {connected ? '链路正常' : '未连接'}
          </span>
        </div>

        {userId && (
          <>
            <Sep />
            <StatusItem label="飞行员" value={userId} valueStyle={{ color: '#00ff88', fontWeight: 'bold' }} />
          </>
        )}

        {/* 当前任务模式标签 */}
        {isStarted && (
          <>
            <Sep />
            <div style={{ padding: '0 14px' }}>
              <span style={{
                fontSize: '14px', letterSpacing: '0.08em', padding: '4px 12px',
                border: `1px solid ${activeDisplay === 'sa' ? '#6a3a00' : '#006a28'}`,
                background: activeDisplay === 'sa' ? 'rgba(180,100,0,0.10)' : 'rgba(0,180,70,0.08)',
                color: activeDisplay === 'sa' ? '#ffbb22' : '#00ee66',
                transition: 'all 0.4s',
              }}>
                {activeDisplay === 'sa' ? '威胁排序任务' : '传感器任务'}
              </span>
            </div>
          </>
        )}

        {infoToShow && isStarted && (
          <>
            <Sep />
            <ProgressBadge current={infoToShow.current} total={infoToShow.total} />

            {infoToShow.difficulty && (
              <>
                <Sep />
                <StatusItem
                  label="难度"
                  value={translateDifficulty(infoToShow.difficulty)}
                  valueStyle={{ color: '#ffcc33', fontWeight: 'bold', textShadow: '0 0 10px rgba(255,200,0,0.5)' }}
                />
              </>
            )}

            <Sep />
            <div style={{ padding: '0 14px' }}>
              <span style={{
                fontSize: '14px', letterSpacing: '0.12em', padding: '4px 12px',
                border: `1px solid ${infoToShow.is_practice ? '#1a5a7a' : '#7a4a0a'}`,
                background: infoToShow.is_practice ? 'rgba(0,150,200,0.10)' : 'rgba(200,120,0,0.10)',
                color: infoToShow.is_practice ? '#22bbdd' : '#ddaa00',
              }}>
                {infoToShow.is_practice ? '练习模式' : '正式模式'}
              </span>
            </div>

            <Sep />
            <div style={{ padding: '0 14px' }}>
              <a
                href={rulesHref}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  fontSize: '14px', letterSpacing: '0.12em', color: '#2aaa55',
                  textDecoration: 'none', padding: '4px 12px',
                  border: '1px solid #1a5530', transition: 'all 0.2s',
                }}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLAnchorElement).style.color = '#00ff77';
                  (e.currentTarget as HTMLAnchorElement).style.borderColor = '#1a8a3a';
                  (e.currentTarget as HTMLAnchorElement).style.background = 'rgba(0,220,100,0.08)';
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLAnchorElement).style.color = '#2aaa55';
                  (e.currentTarget as HTMLAnchorElement).style.borderColor = '#1a5530';
                  (e.currentTarget as HTMLAnchorElement).style.background = 'transparent';
                }}
              >
                策略说明 ↗
              </a>
            </div>
          </>
        )}

        {/* 右侧任务标签 */}
        {isStarted && (
          <button
            type="button"
            onClick={() => setShowTrustSettings(prev => !prev)}
            style={{
              marginLeft: 'auto',
              height: '34px',
              padding: '0 14px',
              background: showTrustSettings ? 'rgba(0,180,90,0.18)' : 'transparent',
              border: `1px solid ${showTrustSettings ? '#00aa55' : '#1a5530'}`,
              color: showTrustSettings ? '#00ff88' : '#2aaa55',
              borderRadius: '3px',
              cursor: 'pointer',
              fontFamily: "'SimHei', 'Microsoft YaHei', sans-serif",
              fontSize: '13px',
              letterSpacing: '0.12em',
            }}
          >
            信任设置
          </button>
        )}
        <div style={{ marginLeft: 'auto', padding: '0 20px', fontSize: '13px', letterSpacing: '0.1em', color: '#3a7a48' }}>
          {displayLabel}
        </div>
      </header>

      {/* ── Main Layout ────────────────────────────────── */}
      {showTrustSettings ? (
        <TrustCalibrationSettings
          connected={connected}
          currentUserId={userId}
          sendMessage={sendMessage}
          onClose={() => setShowTrustSettings(false)}
        />
      ) : (
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* Left — 主显示区 ───────────────────────────── */}
        <div
          className="radar-panel-bg"
          style={{
            flex: '0 0 68%',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: activeDisplay === 'sa' ? 'flex-start' : 'center',
            borderRight: '1px solid #0a2010',
            background: 'radial-gradient(ellipse 70% 60% at 50% 50%, rgba(0,28,10,0.35) 0%, #030a05 70%)',
            padding: '16px',
            overflowY: 'auto',
            overflowX: 'auto',
          }}
        >
          {activeDisplay === 'radar' ? (
            <Radar
              width={700}
              height={700}
              onTargetSelect={handleTargetSelect}
              isStarted={isStarted}
              onRadarParamsUpdate={handleRadarParamsUpdate}
              onAddMessage={addMessage}
              onClearMessages={clearMessages}
              onTaskCompleted={handleRadarTaskCompleted}
              onTrustDecisionUpdate={setSensorTrustDecision}
              onTrustActionsUpdate={setSensorTrustActions}
            />
          ) : (
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-start',
              gap: '8px',
              width: 'max-content',
              minWidth: '100%',
              flexShrink: 0,
            }}>
              <SAPage
                width={800}
                height={600}
                onAddMessage={addMessage}
                onClearMessages={clearMessages}
                userId={userId}
                onResetSA={handleSATaskReset}
                onThreatListUpdate={handleThreatListUpdate}
                onShowDetailedInfoChange={handleShowDetailedInfoChange}
                onResultConfirmed={handleSAResultConfirmed}
                onTrustDecisionUpdate={setSaTrustDecision}
                onTrustActionsUpdate={setSaTrustActions}
              />
              {activeDisplay === 'sa' && (
                <div style={{ width: '800px', alignSelf: 'center', borderTop: '1px solid #0a2010' }}>
                  <ThreatList threats={threatListData} showDetailedInfo={showDetailedInfo} trustDecision={saTrustDecision || undefined} />
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right — 侧边栏 ────────────────────────────── */}
        <div style={{ flex: '0 0 32%', display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#030c05' }}>

          {/* AI Assistant */}
          {includeAI && (
            <div style={{
              flexShrink: 0, padding: '14px 18px',
              borderBottom: '1px solid #0a2010',
              background: 'rgba(0,20,8,0.5)',
            }}>
              <div className="panel-label">AI 辅助系统</div>
              <AIAssistant selectedTarget={selectedTarget} />
            </div>
          )}

          {/* Communication Log */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: '14px 18px' }}>
            <div className="panel-label">通信日志</div>
            <div style={{ flex: 1, overflow: 'hidden' }}>
              <CommunicationLog
                userId={userId}
                isStarted={isStarted}
                taskId={taskId}
                currentTask={activeDisplay === 'sa' ? 'sa' : 'radar'}
                radarRange={radarRange}
                scanAngle={scanAngle}
                antennaAdjustmentRequired={antennaAdjustmentRequired}
                targetAntennaElevation={targetAntennaElevation ?? undefined}
                initSettings={initSettings}
                connected={connected}
                error={error}
                operations={operations}
                onAddMessage={addMessage}
                messages={messages}
                emergencyReceived={emergencyReceived}
                lastEmergencyType={lastEmergencyType}
                lastEmergencyTime={lastEmergencyTime}
              />
            </div>
          </div>

          {activeDisplay === 'sa' && saTrustDecision?.enabled && saTrustDecision.controlLevel !== 'none' && (
            <SidebarThreatTrustPanel decision={saTrustDecision} actions={saTrustActions} />
          )}
          {activeDisplay === 'radar' && sensorTrustDecision?.enabled && sensorTrustDecision.controlLevel !== 'none' && (
            <SidebarSensorTrustPanel decision={sensorTrustDecision} actions={sensorTrustActions} />
          )}


        </div>
      </div>
      )}

      {completionNoticeTask && (
        <div style={{
          position: 'fixed',
          inset: 0,
          zIndex: 10001,
          background: 'rgba(0,0,0,0.48)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          pointerEvents: 'auto',
        }}>
          <div style={{
            background: 'rgba(1,12,4,0.97)',
            padding: '28px 36px',
            border: '1px solid #0d4020',
            borderLeft: '3px solid #00cc55',
            borderRadius: '4px',
            textAlign: 'center',
            boxShadow: '0 0 30px rgba(0,0,0,0.8), 0 0 20px rgba(0,180,70,0.08)',
            fontFamily: "'Share Tech Mono', 'SimHei', 'Microsoft YaHei', monospace",
            minWidth: '300px',
          }}>
            <p style={{
              margin: '0 0 20px 0',
              fontSize: '18px',
              letterSpacing: '0.12em',
              color: '#00cc55',
            }}>
              本次任务已结束
            </p>
            <button
              onClick={() => setCompletionNoticeTask(null)}
              style={{
                fontFamily: "'Share Tech Mono', 'SimHei', 'Microsoft YaHei', monospace",
                fontSize: '13px',
                letterSpacing: '0.15em',
                background: 'rgba(0,30,12,0.6)',
                border: '1px solid #0d4020',
                color: '#00aa44',
                padding: '8px 28px',
                cursor: 'pointer',
                borderRadius: '3px',
                transition: 'background 0.15s',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = 'rgba(0,50,20,0.8)'; }}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = 'rgba(0,30,12,0.6)'; }}
            >
              确认
            </button>
          </div>
        </div>
      )}

      {/* ── Questionnaire Modal ─────────────────────────────── */}
      {(repetitionInfos.RADAR_TARGETING !== null || repetitionInfos.SA_THREAT_RESPONSE !== null || repetitionInfos.PLATFORM_CONTROL !== null || repetitionInfos.WEAPON_FIRING !== null) && (
        <QuestionnaireModal
          ref={questionnaireRef}
          repetitionInfos={repetitionInfos}
          activeDisplay={activeDisplay}
          userId={userId}
          enableAutoPopup={false}
          questionnaireApiUrl="/questionnaire_config.json"
          sendMessage={sendMessage ?? undefined}
          onSubmit={(data: QuestionnaireSubmitData) => {
            const taskLabels: Record<string, string> = { RADAR_TARGETING: '传感器任务', SA_THREAT_RESPONSE: '威胁排序任务', PLATFORM_CONTROL: '平台控制', WEAPON_FIRING: '武器发射' };
            addMessage('system', `问卷已提交 · ${taskLabels[data.taskType] ?? data.taskType} · 第 ${data.repetitionCurrent} 次`);
          }}
        />
      )}
    </div>
  );
});

export default App;
