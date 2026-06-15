import React, {
  useState,
  useEffect,
  useCallback,
  useRef,
  forwardRef,
  useImperativeHandle,
} from 'react';

/* ─────────────────────────────────────────────────────────────
   Types
───────────────────────────────────────────────────────────── */
export type TaskType = 'RADAR_TARGETING' | 'SA_THREAT_RESPONSE' | 'PLATFORM_CONTROL' | 'WEAPON_FIRING';

export interface RepetitionInfo {
  current: number;
  total: number;
  difficulty?: string;
  is_ai_active?: boolean;
  autonomy_level?: string;
  is_practice?: boolean;
  scenario_index?: number;
  scenario_total?: number;
  previous_task_completed?: boolean;
  task_id?: number;
}

interface AllRepetitionInfos {
  RADAR_TARGETING: RepetitionInfo | 'ALL_COMPLETED' | null;
  SA_THREAT_RESPONSE: RepetitionInfo | 'ALL_COMPLETED' | null;
  PLATFORM_CONTROL: RepetitionInfo | 'ALL_COMPLETED' | null;
  WEAPON_FIRING: RepetitionInfo | 'ALL_COMPLETED' | null;
}

interface QuestionItem {
  id: number;
  text: string;
  options?: string[];
}

interface QuestionnaireConfig {
  title?: string;
  taskTitles?: Partial<Record<TaskType, string>>;
  scales?: string[];
  questions: QuestionItem[];
  difficultyLabels?: Record<string, string>;
  autonomyLabels?: Record<string, string>;
  taskTypeLabels?: Partial<Record<TaskType, string>>;
}

export interface QuestionnaireSubmitData {
  taskType: TaskType;
  taskId?: number;
  userId: string;
  repetitionCurrent: number;
  repetitionTotal: number;
  answers: Record<number, number>;
  taskInfo: {
    difficulty?: string;
    autonomyLevel?: string;
    isPractice?: boolean;
  };
  timestamp: number;
}

export interface QuestionnaireModalHandle {
  show: (taskType?: TaskType) => void;
  hide: () => void;
}

interface QuestionnaireModalProps {
  repetitionInfos: AllRepetitionInfos;
  activeDisplay: 'radar' | 'sa';
  userId: string;
  enableAutoPopup: boolean;
  questionnaireApiUrl: string;
  sendMessage?: (message: any) => void;
  onSubmit?: (data: QuestionnaireSubmitData) => void;
  onVisibilityChange?: (visible: boolean) => void;
}

/* ─────────────────────────────────────────────────────────────
   Helpers
───────────────────────────────────────────────────────────── */
const DEFAULT_CONFIG: QuestionnaireConfig = {
  title: '座舱认知状态问卷',
  scales: ['1', '2', '3', '4', '5'],
  questions: [
    {
      id: 1,
      text: 'T1：我对该智能辅助系统有信心。',
      options: ['非常不同意', '不太同意', '中立', '比较同意', '非常同意'],
    },
    {
      id: 2,
      text: 'T2：我认为该智能辅助系统是可靠的。',
      options: ['非常不同意', '不太同意', '中立', '比较同意', '非常同意'],
    },
    {
      id: 3,
      text: 'T3：我愿意信任该辅助智能系统的判断或建议。',
      options: ['非常不同意', '不太同意', '中立', '比较同意', '非常同意'],
    },
    {
      id: 4,
      text: 'MF：请评估您当前的精神疲劳/困倦程度。',
      options: ['非常清醒，状态良好', '清醒，但反应略慢', '既不清醒也不困倦', '有些困倦，精力下降', '非常困倦，难以保持清醒'],
    },
    {
      id: 5,
      text: 'PF：请评估你当前的身体疲劳程度。',
      options: ['完全不疲劳', '轻微疲劳', '比较疲劳', '很疲劳', '非常疲劳'],
    },
    {
      id: 6,
      text: 'ML：请评估你刚才完成任务所投入的脑力努力程度。',
      options: ['完全不费脑力', '轻微费脑力', '比较费脑力', '很费脑力', '非常费脑力'],
    },
    {
      id: 7,
      text: 'S：请评价你在本轮任务中感受到的压力或紧张程度。',
      options: ['完全没有压力，非常放松', '轻度压力，基本放松', '中等压力，需要持续注意和应对', '压力较大，明显感到紧张或负担', '非常有压力，难以放松'],
    },
  ],
};

function translateDifficulty(d: string | undefined, labels?: Record<string, string>): string {
  if (!d) return '-';
  if (labels?.[d]) return labels[d];
  switch (d) {
    case 'low': return '低';
    case 'medium': return '中';
    case 'high': return '高';
    case '1': return '高';
    case '2': return '中';
    case '3': return '低';
    default: return d;
  }
}

function translateAutonomyLevel(level: string | undefined, labels?: Record<string, string>): string {
  if (!level) return '-';
  if (labels?.[level]) return labels[level];
  switch (level) {
    case '0':
    case '1':
    case 'L0': return 'L0';
    case '2':
    case 'L1': return 'L1';
    case '3':
    case 'L2': return 'L2';
    default: return level;
  }
}

/* ─────────────────────────────────────────────────────────────
   Shared inline styles
───────────────────────────────────────────────────────────── */
const fontBase: React.CSSProperties = {
  fontFamily: "'Microsoft YaHei', 'SimHei', 'PingFang SC', 'Noto Sans SC', sans-serif",
};

const selectStyle: React.CSSProperties = {
  padding: '2px 6px',
  border: '1px solid #7a9ab5',
  borderRadius: '2px',
  fontSize: '13px',
  background: 'white',
  color: '#008000',
  WebkitTextFillColor: '#008000',
  opacity: 1,
  cursor: 'default',
  outline: 'none',
  ...fontBase,
};

/* ─────────────────────────────────────────────────────────────
   Component
───────────────────────────────────────────────────────────── */
const QuestionnaireModal = forwardRef<QuestionnaireModalHandle, QuestionnaireModalProps>(
  (
    {
      repetitionInfos,
      activeDisplay,
      userId,
      enableAutoPopup,
      questionnaireApiUrl,
      sendMessage,
      onSubmit,
      onVisibilityChange,
    },
    ref,
  ) => {
    const [isVisible, setIsVisible] = useState(false);
    const [currentTaskType, setCurrentTaskType] = useState<TaskType>('RADAR_TARGETING');
    const [config, setConfig] = useState<QuestionnaireConfig>(DEFAULT_CONFIG);
    const [configLoaded, setConfigLoaded] = useState(false);
    const [answers, setAnswers] = useState<Record<number, number>>({});
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [submitted, setSubmitted] = useState(false);
    const [validationError, setValidationError] = useState(false);

    // Track which task_ids already triggered popup (server-driven via show_questionnaire)
    const triggeredRef = useRef<Set<string>>(new Set());
    const lastInfoRef = useRef<Partial<Record<TaskType, RepetitionInfo>>>({});

    useEffect(() => {
      onVisibilityChange?.(isVisible);
    }, [isVisible, onVisibilityChange]);

    /* ── Fetch questionnaire config ── */
    useEffect(() => {
      fetch(questionnaireApiUrl)
        .then(r => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json();
        })
        .then((data: QuestionnaireConfig) => {
          setConfig({ ...DEFAULT_CONFIG, ...data });
          setConfigLoaded(true);
        })
        .catch(err => {
          console.warn('[QuestionnaireModal] 无法加载问卷配置，使用默认:', err);
          setConfigLoaded(true);
        });
    }, [questionnaireApiUrl]);

    /* ── Preserve the last concrete info before a task flips to ALL_COMPLETED ── */
    useEffect(() => {
      (Object.keys(repetitionInfos) as TaskType[]).forEach(taskType => {
        const info = repetitionInfos[taskType];
        if (info && info !== 'ALL_COMPLETED') {
          lastInfoRef.current[taskType] = info;
        }
      });
    }, [repetitionInfos]);

    const getInfoForTask = useCallback((taskType: TaskType): RepetitionInfo | null => {
      const info = repetitionInfos[taskType];
      if (info && info !== 'ALL_COMPLETED') return info;
      return lastInfoRef.current[taskType] ?? null;
    }, [repetitionInfos]);

    /* ── Internal open helper ── */
    const openFor = useCallback((taskType: TaskType) => {
      setCurrentTaskType(taskType);
      setAnswers({});
      setSubmitted(false);
      setValidationError(false);
      setIsSubmitting(false);
      setIsVisible(true);
    }, []);

    /* ── Legacy auto-popup path. App.tsx now owns questionnaire eligibility
       because it must check AI-active and formal-mode gates before opening. */
    useEffect(() => {
      if (!enableAutoPopup || !configLoaded) return;

      (['RADAR_TARGETING'] as TaskType[]).forEach(taskType => {
        if (repetitionInfos[taskType] !== 'ALL_COMPLETED') return;
        const key = `${taskType}::ALL_COMPLETED`;
        if (!triggeredRef.current.has(key)) {
          triggeredRef.current.add(key);
          openFor(taskType);
        }
      });
    }, [repetitionInfos, enableAutoPopup, configLoaded, openFor]);

    /* ── Expose imperative handle ── */
    useImperativeHandle(ref, () => ({
      show: (taskType?: TaskType) => {
        openFor(taskType ?? (activeDisplay === 'sa' ? 'SA_THREAT_RESPONSE' : 'RADAR_TARGETING'));
      },
      hide: () => setIsVisible(false),
    }));

    /* ── Answer handler ── */
    const handleAnswer = useCallback((questionId: number, value: number) => {
      setAnswers(prev => ({ ...prev, [questionId]: value }));
      setValidationError(false);
    }, []);

    /* ── Submit ── */
    const handleSubmit = useCallback(() => {
      if (!config) return;
      const allAnswered = config.questions.every(q => answers[q.id] !== undefined);
      if (!allAnswered) {
        setValidationError(true);
        return;
      }

      setIsSubmitting(true);
      const infoObj = getInfoForTask(currentTaskType);

      const data: QuestionnaireSubmitData = {
        taskType: currentTaskType,
        taskId: infoObj?.task_id,
        userId,
        repetitionCurrent: infoObj?.current ?? 0,
        repetitionTotal: infoObj?.total ?? 0,
        answers,
        taskInfo: {
          difficulty: infoObj?.difficulty,
          autonomyLevel: infoObj?.autonomy_level,
          isPractice: infoObj?.is_practice,
        },
        timestamp: Date.now(),
      };

      sendMessage?.({ type: 'questionnaire_submitted', ...data, source: 'react_modal' });
      sendMessage?.({
        type: 'task_exit_request',
        reason: 'task_completed',
        task_type: currentTaskType,
        task_id: infoObj?.task_id,
        user_id: userId,
        timestamp: data.timestamp,
      });
      onSubmit?.(data);

      setIsSubmitting(false);
      setSubmitted(true);
      setTimeout(() => setIsVisible(false), 1800);
    }, [config, answers, currentTaskType, userId, getInfoForTask, sendMessage, onSubmit]);

    /* ── Derive display values ── */
    const info = getInfoForTask(currentTaskType);

    const scales = config.scales ?? DEFAULT_CONFIG.scales!;

    const FALLBACK_TASK_LABELS: Record<string, string> = {
      RADAR_TARGETING: '传感器任务', SA_THREAT_RESPONSE: '威胁排序任务',
      PLATFORM_CONTROL: '平台控制', WEAPON_FIRING: '武器发射',
    };
    const taskLabel =
      config.taskTypeLabels?.[currentTaskType] ??
      FALLBACK_TASK_LABELS[currentTaskType] ?? currentTaskType;

    const difficultyLabel = translateDifficulty(info?.difficulty, config.difficultyLabels);
    const autonomyLabel = translateAutonomyLevel(info?.autonomy_level, config.autonomyLabels);

    const modalTitle =
      config.taskTitles?.[currentTaskType] ?? config.title ?? '座舱认知状态问卷';

    if (!isVisible) return null;

    /* ─────── Render ─────── */
    return (
      <div
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 10000,
          background: 'rgba(0,0,0,0.55)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          ...fontBase,
        }}
      >
        <div
          style={{
            background: '#f0f0f0',
            border: '1px solid #888',
            borderRadius: '3px',
            width: '820px',
            maxHeight: '92vh',
            overflowY: 'auto',
            boxShadow: '6px 6px 24px rgba(0,0,0,0.45)',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {/* ── Title bar ── */}
          <div
            style={{
              background: 'linear-gradient(180deg, #3a7bd5 0%, #2563c0 100%)',
              color: 'white',
              padding: '7px 14px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              fontSize: '14px',
              fontWeight: 'bold',
              userSelect: 'none',
              flexShrink: 0,
            }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.2">
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
            </svg>
            <span>{modalTitle}</span>
            <button
              onClick={() => setIsVisible(false)}
              style={{
                marginLeft: 'auto',
                background: 'rgba(255,255,255,0.15)',
                border: '1px solid rgba(255,255,255,0.3)',
                color: 'white',
                width: '22px',
                height: '22px',
                borderRadius: '2px',
                cursor: 'pointer',
                fontSize: '13px',
                lineHeight: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              ✕
            </button>
          </div>

          {/* ── Body ── */}
          <div style={{ padding: '20px 28px 28px', flex: 1 }}>

            {/* Subject info row */}
            <div style={{ display: 'flex', gap: '40px', marginBottom: '14px', fontSize: '15px' }}>
              <span>
                <strong>被试姓名：</strong>
                <span style={{ fontWeight: 'bold' }}>{userId || '-'}</span>
              </span>
            </div>

            {/* Task attribute row */}
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                alignItems: 'center',
                gap: '8px',
                marginBottom: '14px',
                fontSize: '14px',
              }}
            >
              <span style={{ color: '#cc0000', fontWeight: 'bold' }}>任务类型：</span>
              <select style={selectStyle} value={taskLabel} disabled onChange={() => {}}>
                <option>{taskLabel}</option>
              </select>

              <span style={{ color: '#cc0000', fontWeight: 'bold', marginLeft: '8px' }}>任务难度：</span>
              <select
                style={selectStyle}
                value={difficultyLabel}
                disabled
                onChange={() => {}}
              >
                <option>{difficultyLabel}</option>
              </select>

              <span style={{ color: '#cc0000', fontWeight: 'bold', marginLeft: '8px' }}>自主等级：</span>
              <select style={selectStyle} value={autonomyLabel} disabled onChange={() => {}}>
                <option>{autonomyLabel}</option>
              </select>
            </div>

            {/* Instruction */}
            <div style={{ fontSize: '13px', color: '#333', marginBottom: '20px' }}>
              请根据刚才这段任务中的真实感受作答。没有对错，请凭第一反应选择。
            </div>

            {/* Validation error */}
            {validationError && (
              <div
                style={{
                  background: '#fff0f0',
                  border: '1px solid #e74c3c',
                  borderRadius: '3px',
                  padding: '8px 14px',
                  marginBottom: '16px',
                  color: '#c0392b',
                  fontSize: '13px',
                }}
              >
                ⚠ 请完成所有题目的评分后再提交。
              </div>
            )}

            {/* Questions table */}
            <table
              style={{
                width: '100%',
                borderCollapse: 'collapse',
                fontSize: '14px',
              }}
            >
              <thead>
                <tr style={{ borderBottom: '2px solid #b0b0b0' }}>
                  <th
                    style={{
                      textAlign: 'left',
                      padding: '8px 6px',
                      fontWeight: 'bold',
                      width: '44%',
                      color: '#222',
                    }}
                  >
                    题目
                  </th>
                  {scales.map(scale => (
                    <th
                      key={scale}
                      style={{
                        textAlign: 'center',
                        padding: '8px 4px',
                        fontWeight: 'bold',
                        color: '#333',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {scale}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {config.questions.map((q, idx) => {
                  const isAnswered = answers[q.id] !== undefined;
                  const rowBg = validationError && !isAnswered
                    ? '#fff5f5'
                    : idx % 2 === 1
                    ? '#f7f7f7'
                    : 'transparent';

                  return (
                    <tr
                      key={q.id}
                      style={{
                        background: rowBg,
                        borderBottom: '1px solid #e8e8e8',
                        transition: 'background 0.15s',
                      }}
                    >
                      <td style={{ padding: '11px 6px', color: '#222', lineHeight: 1.5 }}>
                        {q.id}. {q.text}
                      </td>
                      {scales.map((scale, scaleIdx) => {
                        const value = scaleIdx + 1;
                        const checked = answers[q.id] === value;
                        const optionLabel = q.options?.[scaleIdx] ?? scale;
                        return (
                          <td
                            key={scaleIdx}
                            style={{ textAlign: 'center', padding: '11px 4px', verticalAlign: 'top' }}
                          >
                            <label
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: '5px',
                                width: '100%',
                                cursor: 'pointer',
                                fontSize: '12px',
                                lineHeight: 1.35,
                              }}
                            >
                              <input
                                type="radio"
                                name={`q_${q.id}`}
                                checked={checked}
                                onChange={() => handleAnswer(q.id, value)}
                                style={{
                                  width: '16px',
                                  height: '16px',
                                  cursor: 'pointer',
                                  accentColor: '#2563c0',
                                  flexShrink: 0,
                                }}
                              />
                              <span>{optionLabel}</span>
                            </label>
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {/* Progress indicator */}
            <div style={{ marginTop: '14px', fontSize: '12px', color: '#888', textAlign: 'right' }}>
              已完成：{Object.keys(answers).length} / {config.questions.length} 题
            </div>

            {/* Submit area */}
            <div style={{ marginTop: '20px', textAlign: 'center' }}>
              {submitted ? (
                <div
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '12px 32px',
                    background: '#e8f8e8',
                    border: '1px solid #4caf50',
                    borderRadius: '4px',
                    color: '#2e7d32',
                    fontWeight: 'bold',
                    fontSize: '15px',
                  }}
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#2e7d32" strokeWidth="2.5">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  提交成功！感谢您的参与。
                </div>
              ) : (
                <button
                  onClick={handleSubmit}
                  disabled={isSubmitting}
                  style={{
                    padding: '10px 72px',
                    background: isSubmitting ? '#88bb88' : '#22aa22',
                    color: 'white',
                    border: 'none',
                    borderRadius: '3px',
                    fontSize: '16px',
                    fontWeight: 'bold',
                    cursor: isSubmitting ? 'not-allowed' : 'pointer',
                    letterSpacing: '0.1em',
                    boxShadow: '0 2px 6px rgba(0,120,0,0.25)',
                    transition: 'background 0.2s',
                    ...fontBase,
                  }}
                  onMouseEnter={e => {
                    if (!isSubmitting) (e.currentTarget as HTMLButtonElement).style.background = '#1a8a1a';
                  }}
                  onMouseLeave={e => {
                    if (!isSubmitting) (e.currentTarget as HTMLButtonElement).style.background = '#22aa22';
                  }}
                >
                  提交
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  },
);

QuestionnaireModal.displayName = 'QuestionnaireModal';

export default QuestionnaireModal;
