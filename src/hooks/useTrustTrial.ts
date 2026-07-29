import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type {
  ManualReviewFeedback,
  TrustCandidate,
  TrustControlState,
  TrustTaskType,
  TrustTrialSnapshot,
} from '../types/trustControl';

type SendMessage = (message: Record<string, unknown>) => void;

interface UseTrustTrialInput {
  taskId: string | number | null;
  taskGroupId: string | number | null;
  taskType: TrustTaskType;
  trialSequence?: number;
  userId?: string;
  control: TrustControlState | null;
  aiRecommendation: TrustCandidate | null;
  candidates: TrustCandidate[];
  groundTruthId: string | null;
  button3: boolean;
  joystickConnected: boolean;
  sendMessage?: SendMessage;
}

interface ReviewContext {
  taskId: string | number;
  taskGroupId: string | number | null;
  taskType: TrustTaskType;
  trialSequence?: number;
  userId?: string;
  uiMode: string;
}

interface ActiveReview {
  sessionId: string;
  candidate: TrustCandidate;
  startedAt: number;
  sequence: number;
  context: ReviewContext;
}

const IDLE_REVIEW_FEEDBACK: ManualReviewFeedback = { status: 'idle', message: '未启动人工复核' };
const candidateKey = (candidate: TrustCandidate | null) => candidate?.id ?? null;

const observationSnapshot = (candidate: TrustCandidate) => ({
  display_target_number: candidate.displayNumber,
  azimuth_deg: candidate.azimuthDeg,
  distance_nm: candidate.distanceNm ?? candidate.distance,
  speed_raw: candidate.speedRaw,
  heading_deg: candidate.headingDeg,
  relative_heading_deg: candidate.relativeHeadingDeg,
  observed_at_ms: candidate.observedAtMs ?? candidate.updatedAt,
});

export function useTrustTrial(input: UseTrustTrialInput) {
  const {
    taskId, taskGroupId, taskType, trialSequence, userId, control,
    aiRecommendation, candidates, groundTruthId, button3, joystickConnected, sendMessage,
  } = input;
  const [focusedCandidate, setFocusedCandidate] = useState<TrustCandidate | null>(null);
  const [humanSelection, setHumanSelection] = useState<TrustCandidate | null>(null);
  const [manualReviewCount, setManualReviewCount] = useState(0);
  const [invalidReviewCount, setInvalidReviewCount] = useState(0);
  const [manualReviewActive, setManualReviewActive] = useState(false);
  const [manualReviewDurationMs, setManualReviewDurationMs] = useState(0);
  const [manualReviewCandidate, setManualReviewCandidate] = useState<TrustCandidate | null>(null);
  const [manualReviewFeedback, setManualReviewFeedback] = useState<ManualReviewFeedback>(IDLE_REVIEW_FEEDBACK);
  const [glowActive, setGlowActive] = useState(false);
  const [aiRecommendationShownAt, setAiRecommendationShownAt] = useState<number | null>(null);
  const pendingFocusRef = useRef<TrustCandidate | null>(null);
  const humanSelectionRef = useRef<TrustCandidate | null>(null);
  const focusTimerRef = useRef<number | null>(null);
  const previousButton3Ref = useRef(false);
  const currentButton3Ref = useRef(button3);
  currentButton3Ref.current = button3;
  const focusStartedAtRef = useRef<number | null>(null);
  const comparisonStartedAtRef = useRef<number | null>(null);
  const previousComparisonRef = useRef(false);
  const completedEventRef = useRef(false);
  const recommendationEventKeyRef = useRef('');
  const activeReviewRef = useRef<ActiveReview | null>(null);
  const manualReviewCountRef = useRef(0);
  const invalidReviewCountRef = useRef(0);
  const manualReviewDurationRef = useRef(0);
  const previousTaskIdRef = useRef<string | number | null>(taskId);
  const previousUserIdRef = useRef(userId);

  const sendEventForContext = useCallback((
    context: ReviewContext,
    eventType: string,
    targetId?: string | null,
    extra?: Record<string, unknown>,
    timestamp = Date.now(),
  ) => {
    if (!sendMessage) return;
    sendMessage({
      type: 'trust_trial_event',
      event_type: eventType,
      event_id: `${context.taskId}:${eventType}:${timestamp}:${Math.random().toString(16).slice(2)}`,
      trial_id: String(context.taskId),
      task_id: context.taskId,
      task_group_id: context.taskGroupId,
      trial_sequence: context.trialSequence,
      task_type: context.taskType,
      user_id: context.userId,
      ui_mode: context.uiMode,
      target_id: targetId ?? undefined,
      timestamp,
      extra: extra ?? {},
    });
  }, [sendMessage]);

  const currentContext = useMemo<ReviewContext | null>(() => (
    taskId && control?.enabled ? {
      taskId,
      taskGroupId,
      taskType,
      trialSequence,
      userId,
      uiMode: control.ui_mode,
    } : null
  ), [control, taskGroupId, taskId, taskType, trialSequence, userId]);

  const emit = useCallback((eventType: string, targetId?: string | null, extra?: Record<string, unknown>) => {
    if (!currentContext) return;
    sendEventForContext(currentContext, eventType, targetId, extra);
  }, [currentContext, sendEventForContext]);

  const endManualReview = useCallback((
    reason: 'button_released' | 'trial_completed' | 'task_changed' | 'user_changed' |
      'recommendation_invalidated' | 'joystick_disconnected' | 'page_unloaded',
    endedAt = Date.now(),
  ) => {
    const active = activeReviewRef.current;
    if (!active) return 0;
    const duration = Math.max(0, endedAt - active.startedAt);
    manualReviewDurationRef.current += duration;
    setManualReviewDurationMs(manualReviewDurationRef.current);
    setManualReviewActive(false);
    setManualReviewCandidate(null);
    setManualReviewFeedback({
      status: 'completed',
      message: `已完成AI推荐目标${active.candidate.displayNumber ?? ''}复核，本次 ${(duration / 1000).toFixed(1)} 秒`,
    });
    sendEventForContext(active.context, 'manual_review_ended', active.candidate.id, {
      review_session_id: active.sessionId,
      joystick_button: 3,
      ai_recommendation_id: active.candidate.id,
      display_target_number: active.candidate.displayNumber,
      started_at_ms: active.startedAt,
      ended_at_ms: endedAt,
      duration_ms: duration,
      end_reason: reason,
    }, endedAt);
    activeReviewRef.current = null;
    return duration;
  }, [sendEventForContext]);

  const endManualReviewRef = useRef(endManualReview);
  useEffect(() => {
    endManualReviewRef.current = endManualReview;
  }, [endManualReview]);

  useEffect(() => {
    const previousTaskId = previousTaskIdRef.current;
    if (activeReviewRef.current && previousTaskId && taskId !== previousTaskId) {
      endManualReviewRef.current('task_changed');
    }
    previousTaskIdRef.current = taskId;

    setFocusedCandidate(null);
    setHumanSelection(null);
    setManualReviewCount(0);
    setInvalidReviewCount(0);
    setManualReviewActive(false);
    setManualReviewDurationMs(0);
    setManualReviewCandidate(null);
    setManualReviewFeedback(IDLE_REVIEW_FEEDBACK);
    setGlowActive(false);
    setAiRecommendationShownAt(null);
    pendingFocusRef.current = null;
    humanSelectionRef.current = null;
    activeReviewRef.current = null;
    manualReviewCountRef.current = 0;
    invalidReviewCountRef.current = 0;
    manualReviewDurationRef.current = 0;
    recommendationEventKeyRef.current = '';
    previousComparisonRef.current = false;
    focusStartedAtRef.current = null;
    comparisonStartedAtRef.current = null;
    completedEventRef.current = false;
    previousButton3Ref.current = currentButton3Ref.current;
    if (focusTimerRef.current !== null) window.clearTimeout(focusTimerRef.current);
  }, [taskId]); // Task identity owns all per-trial process state.

  useEffect(() => {
    const previousUserId = previousUserIdRef.current;
    if (activeReviewRef.current && previousUserId && userId && previousUserId !== userId) {
      endManualReview('user_changed');
    }
    previousUserIdRef.current = userId;
  }, [endManualReview, userId]);

  useEffect(() => {
    if (!taskId || !aiRecommendation || !control?.enabled) return;
    const key = `${taskId}:${aiRecommendation.id}`;
    if (recommendationEventKeyRef.current === key) return;
    recommendationEventKeyRef.current = key;
    const now = Date.now();
    setAiRecommendationShownAt(now);
    emit('ai_recommendation_shown', aiRecommendation.id, {
      candidate_count: candidates.length,
      display_target_number: aiRecommendation.displayNumber,
      observation_snapshot: observationSnapshot(aiRecommendation),
    });
    if (control.ui_mode === 'trust_support') {
      setGlowActive(true);
      emit('glow_started', aiRecommendation.id);
    }
  }, [aiRecommendation, candidates.length, control, emit, taskId]);

  useEffect(() => {
    const active = activeReviewRef.current;
    if (active && (!aiRecommendation || active.candidate.id !== aiRecommendation.id)) {
      endManualReview('recommendation_invalidated');
    }
  }, [aiRecommendation, endManualReview]);

  useEffect(() => {
    if (!joystickConnected && activeReviewRef.current) {
      endManualReview('joystick_disconnected');
    }
  }, [endManualReview, joystickConnected]);

  useEffect(() => {
    const handlePageUnload = () => endManualReviewRef.current('page_unloaded');
    window.addEventListener('pagehide', handlePageUnload);
    return () => {
      window.removeEventListener('pagehide', handlePageUnload);
      endManualReviewRef.current('page_unloaded');
    };
  }, []);

  const commitFocus = useCallback((candidate: TrustCandidate | null) => {
    setFocusedCandidate(previous => {
      if (candidateKey(previous) === candidateKey(candidate)) return previous;
      if (previous) {
        const duration = focusStartedAtRef.current === null
          ? 0
          : Math.max(0, Date.now() - focusStartedAtRef.current);
        emit('tdc_focus_leave', previous.id, { duration_ms: duration });
        emit('detail_hidden', previous.id, { exposure_duration_ms: duration });
      }
      if (candidate) {
        focusStartedAtRef.current = Date.now();
        emit('tdc_focus_enter', candidate.id, { display_target_number: candidate.displayNumber });
        emit('detail_shown', candidate.id, { display_target_number: candidate.displayNumber });
      } else {
        focusStartedAtRef.current = null;
      }
      return candidate;
    });
    if (candidate && glowActive && candidate.id === aiRecommendation?.id) {
      setGlowActive(false);
      emit('glow_ended', candidate.id, { reason: 'tdc_focus' });
    }
  }, [aiRecommendation?.id, emit, glowActive]);

  const updateTdcCandidate = useCallback((candidate: TrustCandidate | null) => {
    if (candidateKey(pendingFocusRef.current) === candidateKey(candidate)) return;
    pendingFocusRef.current = candidate;
    if (focusTimerRef.current !== null) window.clearTimeout(focusTimerRef.current);
    if (!candidate) {
      commitFocus(null);
      return;
    }
    focusTimerRef.current = window.setTimeout(() => {
      if (candidateKey(pendingFocusRef.current) === candidate.id) commitFocus(candidate);
    }, Math.max(0, control?.focus_dwell_ms ?? 150));
  }, [commitFocus, control?.focus_dwell_ms]);

  const recordHumanSelection = useCallback((candidate: TrustCandidate | null) => {
    if (candidateKey(humanSelectionRef.current) === candidateKey(candidate)) return;
    humanSelectionRef.current = candidate;
    setHumanSelection(candidate);
    if (candidate) emit('human_selection_changed', candidate.id, { display_target_number: candidate.displayNumber });
  }, [emit]);

  useEffect(() => {
    if (button3 && !previousButton3Ref.current) {
      if (aiRecommendation && currentContext) {
        const sequence = manualReviewCountRef.current + 1;
        const startedAt = Date.now();
        const sessionId = `${taskId}:manual_review:${sequence}:${startedAt}`;
        const active: ActiveReview = {
          sessionId,
          candidate: aiRecommendation,
          startedAt,
          sequence,
          context: currentContext,
        };
        activeReviewRef.current = active;
        manualReviewCountRef.current = sequence;
        setManualReviewCount(sequence);
        setManualReviewActive(true);
        setManualReviewCandidate(aiRecommendation);
        setManualReviewFeedback({
          status: 'active',
          message: `正在复核AI推荐目标${aiRecommendation.displayNumber ?? ''}`,
        });
        if (glowActive) {
          setGlowActive(false);
          emit('glow_ended', aiRecommendation.id, { reason: 'manual_review_started' });
        }
        sendEventForContext(currentContext, 'manual_review_started', aiRecommendation.id, {
          review_session_id: sessionId,
          joystick_button: 3,
          ai_recommendation_id: aiRecommendation.id,
          display_target_number: aiRecommendation.displayNumber,
          valid: true,
          review_sequence: sequence,
          started_at_ms: startedAt,
          observation_snapshot: observationSnapshot(aiRecommendation),
        }, startedAt);
      } else {
        const sequence = invalidReviewCountRef.current + 1;
        const ignoredAt = Date.now();
        invalidReviewCountRef.current = sequence;
        setInvalidReviewCount(sequence);
        setManualReviewFeedback({ status: 'ignored', message: '暂无可复核的AI推荐目标' });
        if (currentContext) {
          sendEventForContext(currentContext, 'manual_review_ignored', null, {
            joystick_button: 3,
            valid: false,
            review_sequence: sequence,
            reason: 'no_ai_recommendation',
            timestamp_ms: ignoredAt,
          }, ignoredAt);
        }
      }
    } else if (!button3 && previousButton3Ref.current) {
      endManualReview('button_released');
    }
    previousButton3Ref.current = button3;
  }, [aiRecommendation, button3, currentContext, emit, endManualReview, glowActive, sendEventForContext, taskId]);

  const comparisonVisible = Boolean(
    aiRecommendation && humanSelection && aiRecommendation.id !== humanSelection.id
  );
  useEffect(() => {
    if (comparisonVisible !== previousComparisonRef.current) {
      const duration = comparisonStartedAtRef.current === null
        ? 0
        : Math.max(0, Date.now() - comparisonStartedAtRef.current);
      emit(comparisonVisible ? 'comparison_shown' : 'comparison_hidden', humanSelection?.id, {
        ai_recommendation_id: aiRecommendation?.id,
        ...(comparisonVisible ? {} : { exposure_duration_ms: duration }),
      });
      comparisonStartedAtRef.current = comparisonVisible ? Date.now() : null;
      previousComparisonRef.current = comparisonVisible;
    }
  }, [aiRecommendation?.id, comparisonVisible, emit, humanSelection?.id]);

  const buildTrustTrial = useCallback((confirmedSelection?: TrustCandidate | null) => {
    const finalHumanSelection = confirmedSelection ?? humanSelectionRef.current ?? (
      taskType === 'SA_THREAT_RESPONSE' ? aiRecommendation : null
    );
    if (!taskId || !aiRecommendation || !finalHumanSelection || !groundTruthId) return null;
    const confirmedAt = Date.now();
    if (candidateKey(humanSelectionRef.current) !== finalHumanSelection.id) {
      humanSelectionRef.current = finalHumanSelection;
      setHumanSelection(finalHumanSelection);
      emit('human_selection_changed', finalHumanSelection.id, {
        display_target_number: finalHumanSelection.displayNumber,
        source: 'result_confirmation',
      });
    }
    endManualReview('trial_completed', confirmedAt);
    if (!completedEventRef.current) {
      emit('final_selection_confirmed', finalHumanSelection.id);
      if (glowActive) emit('glow_ended', aiRecommendation.id, { reason: 'trial_completed' });
      if (comparisonVisible) {
        const duration = comparisonStartedAtRef.current === null
          ? 0
          : Math.max(0, confirmedAt - comparisonStartedAtRef.current);
        emit('comparison_hidden', finalHumanSelection.id, {
          ai_recommendation_id: aiRecommendation.id,
          exposure_duration_ms: duration,
          reason: 'trial_completed',
        });
      }
      emit('trial_completed', finalHumanSelection.id);
      completedEventRef.current = true;
    }
    return {
      trial_id: String(taskId),
      trial_sequence: trialSequence,
      ai_recommendation: aiRecommendation.id,
      human_final_selection: finalHumanSelection.id,
      ground_truth: groundTruthId,
      ai_recommendation_shown_at_ms: aiRecommendationShownAt,
      final_selection_confirmed_at_ms: confirmedAt,
      manual_review_used: manualReviewCountRef.current > 0,
      manual_review_count: manualReviewCountRef.current,
      manual_review_duration_ms: manualReviewDurationRef.current,
      invalid_review_count: invalidReviewCountRef.current,
    };
  }, [aiRecommendation, aiRecommendationShownAt, comparisonVisible, emit, endManualReview, glowActive, groundTruthId, taskId, taskType, trialSequence]);

  const snapshot = useMemo<TrustTrialSnapshot>(() => ({
    taskId, taskGroupId, taskType, trialSequence, control, aiRecommendation, candidates,
    focusedCandidate, humanSelection, groundTruthId, manualReviewCount, invalidReviewCount,
    manualReviewActive, manualReviewDurationMs, manualReviewCandidate, manualReviewFeedback,
    comparisonVisible, glowActive, aiRecommendationShownAt,
  }), [aiRecommendation, aiRecommendationShownAt, candidates, comparisonVisible, control, focusedCandidate, groundTruthId, glowActive, humanSelection, invalidReviewCount, manualReviewActive, manualReviewCandidate, manualReviewCount, manualReviewDurationMs, manualReviewFeedback, taskGroupId, taskId, taskType, trialSequence]);

  return { snapshot, updateTdcCandidate, recordHumanSelection, buildTrustTrial, emit };
}
