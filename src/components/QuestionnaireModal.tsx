import React, {
  useState,
  useEffect,
  useCallback,
  useRef,
  forwardRef,
  useImperativeHandle,
} from 'react';
import {
  isQuestionnaireAnswerValid,
  resolveQuestionnaireQuestions,
  type ManualQuestionnaireConfig,
  type QuestionnaireQuestion,
} from '../utils/questionnaireQuestions';

/* ─────────────────────────────────────────────────────────────
   Types
───────────────────────────────────────────────────────────── */
export type TaskType = 'RADAR_TARGETING' | 'SA_THREAT_RESPONSE' | 'PLATFORM_CONTROL' | 'WEAPON_FIRING';

export interface RepetitionInfo {
  current: number;
  total: number;
  difficulty?: string;
  is_ai_active?: boolean;
  control_mode?: string;
  autonomy_level?: string;
  is_practice?: boolean;
  scenario_index?: number;
  scenario_total?: number;
  previous_task_completed?: boolean;
  task_id?: number;
  task_group_id?: number;
}

interface AllRepetitionInfos {
  RADAR_TARGETING: RepetitionInfo | 'ALL_COMPLETED' | null;
  SA_THREAT_RESPONSE: RepetitionInfo | 'ALL_COMPLETED' | null;
  PLATFORM_CONTROL: RepetitionInfo | 'ALL_COMPLETED' | null;
  WEAPON_FIRING: RepetitionInfo | 'ALL_COMPLETED' | null;
}

interface QuestionnaireConfig {
  title?: string;
  instruction?: string;
  taskTitles?: Partial<Record<TaskType, string>>;
  scales?: string[];
  questions: QuestionnaireQuestion[];
  manualQuestionnaire?: ManualQuestionnaireConfig;
  difficultyLabels?: Record<string, string>;
  autonomyLabels?: Record<string, string>;
  taskTypeLabels?: Partial<Record<TaskType, string>>;
}

export interface QuestionnaireSubmitData {
  taskType: TaskType;
  userId: string;
  repetitionCurrent: number;
  repetitionTotal: number;
  taskGroupId?: number;
  answers: Record<number, number>;
  taskInfo: {
    difficulty?: string;
    autonomyLevel?: string;
    controlMode?: string;
    isPractice?: boolean;
  };
  timestamp: number;
}

export interface QuestionnaireModalHandle {
  show: (taskType?: TaskType, completionInfo?: RepetitionInfo) => void;
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
  scales: ['1', '2', '3', '4', '5', '6', '7'],
  questions: [
    {
      id: 1,
      text: '我对该智能辅助系统有信心。',
      options: ['非常不同意', '不同意', '比较不同意', '中立', '比较同意', '同意', '非常同意'],
    },
    {
      id: 2,
      text: '我认为该智能辅助系统是可靠的。',
      options: ['非常不同意', '不同意', '比较不同意', '中立', '比较同意', '同意', '非常同意'],
    },
    {
      id: 3,
      text: '我愿意信任该辅助智能系统。',
      options: ['非常不同意', '不同意', '比较不同意', '中立', '比较同意', '同意', '非常同意'],
    },
    {
      id: 4,
      text: '请根据你此刻的实际感受，评价你当前的清醒或困倦程度。',
      options: ['非常清醒，状态良好', '清醒，状态较好', '略感困倦，但反应基本正常', '既不清醒，也不困倦', '有些困倦，精力有所下降', '比较困倦，反应明显变慢', '非常困倦，难以保持清醒'],
    },
    {
      id: 5,
      text: '请评估你完成本轮任务所投入的脑力努力程度。',
      options: ['完全不费脑力', '非常轻微费脑力', '轻微费脑力', '中等程度费脑力', '比较费脑力', '很费脑力', '非常费脑力'],
    },
    {
      id: 6,
      text: '请评价你在本轮任务过程中感到紧张或不安的程度。',
      options: ['完全不紧张', '非常轻微', '较轻', '中等', '较强', '很强', '极度紧张'],
    },
  ],
  manualQuestionnaire: {
    taskTypes: [
      'RADAR_TARGETING',
      'SA_THREAT_RESPONSE',
      'PLATFORM_CONTROL',
      'WEAPON_FIRING',
    ],
    questionIds: [4, 5, 6],
    additionalQuestions: [
      {
        id: 7,
        text: '你认为当前你在这类任务中的总体正确率大约是____%。',
        type: 'number',
        min: 0,
        max: 100,
        step: 1,
        suffix: '%',
        placeholder: '请输入 0–100',
      },
    ],
  },
};

/* ─────────────────────────────────────────────────────────────
   Shared inline styles
───────────────────────────────────────────────────────────── */
const fontBase: React.CSSProperties = {
  fontFamily: "'Microsoft YaHei', 'SimHei', 'PingFang SC', 'Noto Sans SC', sans-serif",
};

const selectStyle: React.CSSProperties = {
  padding: '5px 10px',
  border: '1px solid #b9c7d6',
  borderRadius: '6px',
  fontSize: '13px',
  background: '#f8fafc',
  color: '#14532d',
  WebkitTextFillColor: '#14532d',
  opacity: 1,
  cursor: 'default',
  outline: 'none',
  fontWeight: 600,
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
    const [completionInfo, setCompletionInfo] = useState<RepetitionInfo | null>(null);

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
      if (taskType === currentTaskType && completionInfo) return completionInfo;
      const info = repetitionInfos[taskType];
      if (info && info !== 'ALL_COMPLETED') return info;
      return lastInfoRef.current[taskType] ?? null;
    }, [repetitionInfos, currentTaskType, completionInfo]);

    /* ── Internal open helper ── */
    const openFor = useCallback((taskType: TaskType, info?: RepetitionInfo) => {
      setCurrentTaskType(taskType);
      setCompletionInfo(info ?? null);
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
      show: (taskType?: TaskType, info?: RepetitionInfo) => {
        openFor(taskType ?? (activeDisplay === 'sa' ? 'SA_THREAT_RESPONSE' : 'RADAR_TARGETING'), info);
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
      const infoObj = getInfoForTask(currentTaskType);
      const questions = resolveQuestionnaireQuestions(
        config.questions,
        config.manualQuestionnaire,
        infoObj?.control_mode,
        currentTaskType,
      );
      const allAnswered = questions.every(q => isQuestionnaireAnswerValid(q, answers[q.id]));
      if (!allAnswered) {
        setValidationError(true);
        return;
      }

      setIsSubmitting(true);

      const data: QuestionnaireSubmitData = {
        taskType: currentTaskType,
        userId,
        repetitionCurrent: infoObj?.current ?? 0,
        repetitionTotal: infoObj?.total ?? 0,
        taskGroupId: infoObj?.task_group_id,
        answers,
        taskInfo: {
          difficulty: infoObj?.difficulty,
          autonomyLevel: infoObj?.autonomy_level,
          controlMode: infoObj?.control_mode,
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
    const scales = config.scales ?? DEFAULT_CONFIG.scales!;
    const currentInfo = getInfoForTask(currentTaskType);
    const questions = resolveQuestionnaireQuestions(
      config.questions,
      config.manualQuestionnaire,
      currentInfo?.control_mode,
      currentTaskType,
    );

    const FALLBACK_TASK_LABELS: Record<string, string> = {
      RADAR_TARGETING: '传感器任务', SA_THREAT_RESPONSE: '威胁排序任务',
      PLATFORM_CONTROL: '平台控制', WEAPON_FIRING: '武器发射',
    };
    const taskLabel =
      config.taskTypeLabels?.[currentTaskType] ??
      FALLBACK_TASK_LABELS[currentTaskType] ?? currentTaskType;

    const modalTitle =
      config.taskTitles?.[currentTaskType] ?? config.title ?? '座舱认知状态问卷';
    const answeredCount = questions.filter(q => isQuestionnaireAnswerValid(q, answers[q.id])).length;
    const progressPercent = questions.length > 0
      ? Math.round((answeredCount / questions.length) * 100)
      : 0;

    if (!isVisible) return null;

    /* ─────── Render ─────── */
    return (
      <div
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 10000,
          background: 'rgba(7, 16, 28, 0.62)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '24px',
          ...fontBase,
        }}
      >
        <div
          style={{
            background: '#f6f8fb',
            border: '1px solid rgba(148, 163, 184, 0.55)',
            borderRadius: '12px',
            width: 'min(1500px, calc(100vw - 24px))',
            maxWidth: 'calc(100vw - 24px)',
            maxHeight: '92vh',
            overflowY: 'auto',
            boxShadow: '0 28px 70px rgba(15, 23, 42, 0.38)',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {/* ── Title bar ── */}
          <div
            style={{
              background: '#1f5fbf',
              color: 'white',
              padding: '13px 18px',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              fontSize: '16px',
              fontWeight: 700,
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
                width: '30px',
                height: '30px',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '16px',
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
          <div style={{ padding: '22px 30px 28px', flex: 1 }}>

            {/* Subject info row */}
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                alignItems: 'center',
                gap: '10px',
                marginBottom: '16px',
              }}
            >
              <span style={{ fontSize: '14px', color: '#475569' }}>被试姓名</span>
              <span
                style={{
                  padding: '5px 12px',
                  borderRadius: '6px',
                  background: '#e9f7ef',
                  border: '1px solid #b7e4c7',
                  color: '#047857',
                  fontWeight: 700,
                }}
              >
                {userId || '-'}
              </span>
              <span style={{ color: '#64748b', margin: '0 2px' }}>·</span>
              <span style={{ fontSize: '14px', color: '#475569' }}>任务类型</span>
              <select style={selectStyle} value={taskLabel} disabled onChange={() => {}}>
                <option>{taskLabel}</option>
              </select>

            </div>

            {/* Instruction */}
            {config.instruction && (
              <div
                style={{
                  fontSize: '14px',
                  color: '#334155',
                  marginBottom: '18px',
                  padding: '12px 14px',
                  background: '#eef4fb',
                  border: '1px solid #d7e2ef',
                  borderRadius: '8px',
                  lineHeight: 1.6,
                }}
              >
                {config.instruction}
              </div>
            )}

            {/* Validation error */}
            {validationError && (
              <div
                style={{
                  background: '#fff0f0',
                  border: '1px solid #e74c3c',
                  borderRadius: '8px',
                  padding: '10px 14px',
                  marginBottom: '16px',
                  color: '#c0392b',
                  fontSize: '14px',
                }}
              >
                ⚠ 请完成所有题目的作答后再提交。
              </div>
            )}

            {/* Questions */}
            <div
              style={{
                display: 'grid',
                gap: '12px',
              }}
            >
              {questions.map((q, questionIndex) => {
                const isAnswered = isQuestionnaireAnswerValid(q, answers[q.id]);
                const isMissing = validationError && !isAnswered;

                return (
                  <div
                    key={q.id}
                    style={{
                      background: isMissing ? '#fff7ed' : '#ffffff',
                      border: `1px solid ${isMissing ? '#fb923c' : '#d9e2ec'}`,
                      borderRadius: '10px',
                      padding: '14px 16px 16px',
                      boxShadow: '0 1px 2px rgba(15, 23, 42, 0.05)',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: '12px',
                        marginBottom: '12px',
                      }}
                    >
                      <span
                        style={{
                          minWidth: '28px',
                          height: '28px',
                          borderRadius: '6px',
                          background: isAnswered ? '#dbeafe' : '#edf2f7',
                          color: isAnswered ? '#1d4ed8' : '#475569',
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontWeight: 700,
                          fontVariantNumeric: 'tabular-nums',
                        }}
                      >
                        {questionIndex + 1}
                      </span>
                      <div style={{ color: '#172033', fontSize: '15px', lineHeight: 1.55, fontWeight: 600 }}>
                        {q.text}
                      </div>
                    </div>
                    {q.type === 'number' ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <input
                          type="number"
                          min={q.min}
                          max={q.max}
                          step={q.step ?? 1}
                          value={answers[q.id] ?? ''}
                          placeholder={q.placeholder}
                          onChange={event => {
                            const rawValue = event.target.value;
                            if (rawValue === '') {
                              setAnswers(prev => {
                                const next = { ...prev };
                                delete next[q.id];
                                return next;
                              });
                              return;
                            }
                            handleAnswer(q.id, Number(rawValue));
                          }}
                          style={{
                            width: '220px',
                            maxWidth: '100%',
                            padding: '11px 12px',
                            border: `1px solid ${isMissing ? '#fb923c' : '#b9c7d6'}`,
                            borderRadius: '8px',
                            color: '#172033',
                            background: '#f8fafc',
                            fontSize: '15px',
                            outline: 'none',
                            ...fontBase,
                          }}
                        />
                        <span style={{ color: '#334155', fontSize: '15px', fontWeight: 700 }}>
                          {q.suffix}
                        </span>
                      </div>
                    ) : (
                      <div
                        style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(7, minmax(115px, 1fr))',
                          gap: '8px',
                          overflowX: 'auto',
                          paddingBottom: '2px',
                        }}
                      >
                        {scales.map((scale, scaleIdx) => {
                        const value = scaleIdx + 1;
                        const checked = answers[q.id] === value;
                        const optionLabel = q.options?.[scaleIdx] ?? scale;
                        return (
                          <label
                            key={scaleIdx}
                            style={{
                              minHeight: '58px',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '8px',
                              cursor: 'pointer',
                              padding: '9px 10px',
                              borderRadius: '8px',
                              border: `1px solid ${checked ? '#2563eb' : '#d2dbe8'}`,
                              background: checked ? '#eff6ff' : '#f8fafc',
                              color: checked ? '#1e40af' : '#334155',
                              transition: 'border-color 0.16s, background 0.16s, box-shadow 0.16s',
                            }}
                          >
                            <input
                              type="radio"
                              name={`q_${q.id}`}
                              checked={checked}
                              onChange={() => handleAnswer(q.id, value)}
                              style={{
                                width: '17px',
                                height: '17px',
                                cursor: 'pointer',
                                accentColor: '#2563eb',
                                flexShrink: 0,
                              }}
                            />
                            <span style={{ display: 'grid', gap: '2px', minWidth: 0 }}>
                              <span style={{ fontSize: '13px', lineHeight: 1, fontWeight: 700 }}>{scale}</span>
                              <span style={{ fontSize: '12px', lineHeight: 1.35 }}>{optionLabel}</span>
                            </span>
                          </label>
                        );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Progress indicator */}
            <div
              style={{
                marginTop: '16px',
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                color: '#64748b',
                fontSize: '13px',
              }}
            >
              <div style={{ flex: 1, height: '8px', borderRadius: '999px', background: '#dbe3ee', overflow: 'hidden' }}>
                <div
                  style={{
                    width: `${progressPercent}%`,
                    height: '100%',
                    background: '#2563eb',
                    transition: 'width 0.2s',
                  }}
                />
              </div>
              <span style={{ minWidth: '110px', textAlign: 'right' }}>
                已完成：{answeredCount} / {questions.length} 题
              </span>
            </div>

            {/* Submit area */}
            <div style={{ marginTop: '22px', textAlign: 'center' }}>
              {submitted ? (
                <div
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '12px 32px',
                    background: '#ecfdf5',
                    border: '1px solid #86efac',
                    borderRadius: '8px',
                    color: '#166534',
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
                    minWidth: '220px',
                    padding: '12px 72px',
                    background: isSubmitting ? '#93c5fd' : '#1f5fbf',
                    color: 'white',
                    border: 'none',
                    borderRadius: '8px',
                    fontSize: '16px',
                    fontWeight: 'bold',
                    cursor: isSubmitting ? 'not-allowed' : 'pointer',
                    letterSpacing: '0.08em',
                    boxShadow: '0 10px 24px rgba(31, 95, 191, 0.26)',
                    transition: 'background 0.2s, transform 0.2s',
                    ...fontBase,
                  }}
                  onMouseEnter={e => {
                    if (!isSubmitting) (e.currentTarget as HTMLButtonElement).style.background = '#174ea6';
                  }}
                  onMouseLeave={e => {
                    if (!isSubmitting) (e.currentTarget as HTMLButtonElement).style.background = '#1f5fbf';
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
