import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import Radar from './components/Radar';
import AIAssistant from './components/AIAssistant';
import SAPage from './components/SAPage';
import CommunicationLog, { LogMessage, MessageType } from './components/CommunicationLog';
import ThreatList from './components/ThreatList';
import GazePointOverlay, { type GazePointDebug } from './components/GazePointOverlay';
import useRadarData, { globalWS } from './hooks/useRadarData';
import { observer } from 'mobx-react-lite';
import { useStore } from './stores/StoreProvider';
import agentStore from './stores/AgentStore';
import audioManager from './managers/AudioManager';
import { Toaster } from 'react-hot-toast';
import QuestionnaireModal, { QuestionnaireModalHandle, QuestionnaireSubmitData } from './components/QuestionnaireModal.tsx';
interface TargetSelectParams {
  targetId: string | undefined;
  lockX?: number;
  iffMode?: boolean;
  externalTargetsTimestamp?: number | null;
  event_owner?: 'AI' | 'manual';
}

type TaskType = 'RADAR_TARGETING' | 'SA_THREAT_RESPONSE' | 'PLATFORM_CONTROL' | 'WEAPON_FIRING';

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

/* ── Corner decoration ────────────────────────────── */
const MilCorners: React.FC<{ color?: string }> = ({ color = '#00aa44' }) => (
  <>
    {([
      'top-0 left-0 border-t-2 border-l-2',
      'top-0 right-0 border-t-2 border-r-2',
      'bottom-0 left-0 border-b-2 border-l-2',
      'bottom-0 right-0 border-b-2 border-r-2',
    ] as const).map((cls, i) => (
      <span key={i} className={`absolute ${cls} w-3 h-3`} style={{ borderColor: color }} />
    ))}
  </>
);

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

/* ══════════════════════════════════════════════════════
   App
══════════════════════════════════════════════════════ */
const App: React.FC = observer(() => {
  const [selectedTarget] = useState<string | null>(null);
  const [userId, setUserId] = useState<string>('');
  const [includeAI, setIncludeAI] = useState<boolean>(false);
  const [isStarted, setIsStarted] = useState<boolean>(false);
  const [showGazePoint, setShowGazePoint] = useState<boolean>(false);
  const [gazePointDebug, setGazePointDebug] = useState<GazePointDebug | null>(null);
  const [useJoystick, setUseJoystick] = useState<boolean>(false);
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
  const [isQuestionnaireVisible, setIsQuestionnaireVisible] = useState(false);

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
    platformTaskConfig,
    platformAutoStart,
    lastMessage,
    joystickEnabled,
    button2,
  } = useRadarData();

  const [messages, setMessages] = useState<LogMessage[]>([]);
  const [completionNoticeTask, setCompletionNoticeTask] = useState<TaskType | null>(null);
  const previousCompletionNoticeButton2Ref = useRef(false);
  const messageIdRef = useRef(0);
  const suppressRadarJoystickActions = !!completionNoticeTask || isQuestionnaireVisible;

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

  useEffect(() => {
    if (completionNoticeTask && joystickEnabled && button2 && !previousCompletionNoticeButton2Ref.current) {
      setCompletionNoticeTask(null);
    }
    previousCompletionNoticeButton2Ref.current = button2;
  }, [completionNoticeTask, joystickEnabled, button2]);

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
  ) => {
    const startKey = `${id}::${taskType}::${withAI ? 'ai' : 'manual'}::${practice ? 'practice' : 'formal'}`;
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
    radarStore.startSystem(id, withAI, practice);
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
      });
    } else {
      setActiveDisplay('radar');
      initializeSystem(id, withAI, practice);
    }
  }, [sendMessage, initializeSystem, radarStore]);

  /* ── 任务启动后自动连接操纵杆 ────────────────────── */
  useEffect(() => {
    if (joystickInitedRef.current) return;
    joystickInitedRef.current = true;
    globalWS.sendMessage({ type: 'joystick_connect', timestamp: Date.now(), user_id: userId });
    globalWS.sendMessage({ type: 'joystick_subscribe', timestamp: Date.now(), user_id: userId });
  }, [isStarted, connected, useJoystick, userId]);

  useEffect(() => {
    if (!platformAutoStart) return;
    handleStartApp(
      platformAutoStart.userId,
      platformAutoStart.includeAI,
      platformAutoStart.taskType,
      platformAutoStart.isPractice,
      false,
    );
  }, [platformAutoStart, handleStartApp]);

  const handleStartTask = useCallback(() => {
    audioManager.unlock();
    fetch('/init_config.json')
      .then(r => r.json())
      .then((cfg: { userId: string; includeAI: boolean; taskType: 'radar' | 'sa'; isPractice: boolean; useJoystick: boolean }) => {
        const fromPlatform = platformTaskConfig?.normalized?.web_task_kind;
        const taskType: 'radar' | 'sa' =
          fromPlatform === 'sa' || fromPlatform === 'radar' ? fromPlatform : cfg.taskType;
        handleStartApp(cfg.userId, cfg.includeAI, taskType, cfg.isPractice, cfg.useJoystick);
      })
      .catch(err => console.error('[App] 加载 init_config.json 失败:', err));
  }, [handleStartApp, platformTaskConfig]);

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
      <GazePointOverlay enabled={showGazePoint} onGazePointChange={setGazePointDebug} />
      {/* ── Startup Modal ──────────────────────────────── */}
      {!isStarted && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 50,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(2, 8, 4, 0.97)',
        }}>
          <div style={{
            position: 'absolute', inset: 0,
            background: 'radial-gradient(ellipse 60% 50% at 50% 50%, rgba(0,80,30,0.12) 0%, transparent 70%)',
            pointerEvents: 'none',
          }} />
          <div
            className="mil-frame"
            style={{
              position: 'relative', padding: '52px 72px',
              background: 'rgba(4, 14, 7, 0.97)',
              border: '1px solid #1a5c2a',
              boxShadow: '0 0 60px rgba(0,255,80,0.06), 0 0 120px rgba(0,255,80,0.03)',
              textAlign: 'center', minWidth: '380px',
            }}
          >
            <MilCorners color="#00cc55" />
            <div style={{ color: '#1a6a2a', fontSize: '12px', letterSpacing: '0.35em', marginBottom: '10px' }}>
              航空电子任务环境系统
            </div>
            <h1
              className="glow-green"
              style={{
                fontFamily: "'Share Tech Mono', 'Microsoft YaHei', monospace",
                color: '#00ff66', fontSize: '32px', fontWeight: 700,
                letterSpacing: '0.2em', margin: '0 0 6px',
              }}
            >
              JF-17
            </h1>
            <div style={{ color: '#00aa44', fontSize: '13px', letterSpacing: '0.3em', marginBottom: '36px' }}>
              AEMS · 传感器任务系统
            </div>
            <div style={{ width: '80px', height: '1px', background: 'linear-gradient(to right, transparent, #1a6a2a, transparent)', margin: '0 auto 36px' }} />
            <button
              className="start-btn"
              disabled={!connected}
              onClick={handleStartTask}
              style={{
                padding: '14px 52px',
                background: connected ? 'rgba(0, 170, 60, 0.12)' : 'rgba(20, 20, 20, 0.6)',
                border: `1px solid ${connected ? '#00aa44' : '#1a1a1a'}`,
                color: connected ? '#00ff77' : '#2a2a2a',
                fontFamily: "'SimHei', 'Microsoft YaHei', 'Noto Sans SC', sans-serif",
                fontSize: '13px', letterSpacing: '0.25em',
                cursor: connected ? 'pointer' : 'not-allowed',
                transition: 'all 0.25s', outline: 'none', width: '100%',
              }}
            >
              {connected ? '▶  开始训练' : '正在连接服务器...'}
            </button>
            <div style={{ marginTop: '20px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
              <span
                className={connected ? 'pulse-dot' : 'blink'}
                style={{
                  display: 'inline-block', width: '6px', height: '6px', borderRadius: '50%',
                  background: connected ? '#00ff55' : '#ff4444',
                  color: connected ? '#00ff55' : '#ff4444',
                }}
              />
              <span style={{ fontSize: '12px', letterSpacing: '0.2em', color: connected ? '#1a6a2a' : '#6a1a1a' }}>
                {connected ? '服务器连接正常' : '正在连接服务器...'}
              </span>
            </div>
          </div>
        </div>
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
        <Sep />
        <button
          type="button"
          aria-pressed={showGazePoint}
          onClick={() => setShowGazePoint(prev => !prev)}
          style={{
            margin: '0 14px',
            padding: '4px 12px',
            border: `1px solid ${showGazePoint ? '#1ccf7a' : '#1a5530'}`,
            borderRadius: '3px',
            background: showGazePoint ? 'rgba(0, 220, 120, 0.16)' : 'rgba(0, 40, 16, 0.35)',
            color: showGazePoint ? '#84ffd0' : '#2aaa55',
            fontFamily: "'SimHei', 'Microsoft YaHei', 'Noto Sans SC', sans-serif",
            fontSize: '13px',
            letterSpacing: '0.12em',
            lineHeight: 1.3,
            cursor: 'pointer',
            transition: 'all 0.18s ease',
            boxShadow: showGazePoint ? '0 0 14px rgba(0, 255, 130, 0.18)' : 'none',
          }}
          title={showGazePoint ? '关闭注视点渲染' : '开启注视点渲染'}
        >
          注视点 {showGazePoint ? 'ON' : 'OFF'}
        </button>

        {showGazePoint && (
          <div
            style={{
              padding: '0 8px',
              color: gazePointDebug ? '#ffdd66' : '#6a5530',
              fontFamily: "'Share Tech Mono', monospace",
              fontSize: '12px',
              letterSpacing: '0.04em',
              whiteSpace: 'nowrap',
            }}
          >
            {gazePointDebug
              ? `GAZE ${gazePointDebug.normalizedX.toFixed(3)},${gazePointDebug.normalizedY.toFixed(3)} | PX ${Math.round(gazePointDebug.pixelX)},${Math.round(gazePointDebug.pixelY)}`
              : 'GAZE --,-- | PX --,--'}
          </div>
        )}

        <div style={{ marginLeft: 'auto', padding: '0 20px', fontSize: '13px', letterSpacing: '0.1em', color: '#3a7a48' }}>
          {displayLabel}
        </div>
      </header>

      {/* ── Main Layout ────────────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* Left — 主显示区 ───────────────────────────── */}
        <div
          className="radar-panel-bg"
          style={{
            flex: '0 0 60%',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            borderRight: '1px solid #0a2010',
            background: 'radial-gradient(ellipse 70% 60% at 50% 50%, rgba(0,28,10,0.35) 0%, #030a05 70%)',
            padding: '16px',
            overflowY: 'auto',
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
              suppressJoystickActions={suppressRadarJoystickActions}
            />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', width: '100%' }}>
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
              />
              {activeDisplay === 'sa' && (
                <div style={{ width: '800px', borderTop: '1px solid #0a2010' }}>
                  <ThreatList threats={threatListData} showDetailedInfo={showDetailedInfo} />
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right — 侧边栏 ────────────────────────────── */}
        <div style={{ flex: '0 0 40%', display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#030c05' }}>

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
                targetAntennaElevation={targetAntennaElevation || undefined}
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


        </div>
      </div>

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
          onVisibilityChange={setIsQuestionnaireVisible}
        />
      )}
    </div>
  );
});

export default App;
