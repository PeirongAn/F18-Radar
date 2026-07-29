export interface AIAgentSchedulerCallbacks<TThreat = unknown> {
  getDelayMs: () => number;
  getBestThreat: () => TThreat | null | undefined;
  onHandleEmergency: (threat: TThreat) => void;
}

export const AI_THREAT_RETRY_DELAY_MS = 50;
export const AI_THREAT_MAX_ATTEMPTS = 4;

type TimerHandle = ReturnType<typeof globalThis.setTimeout>;

const normalizeDelay = (delay: number, fallback: number): number => (
  Number.isFinite(delay) && delay >= 0 ? delay : fallback
);

/**
 * Owns AI selection timers independently from React effect lifecycles.
 *
 * SA emergency messages are edge-triggered pulses: a later websocket message
 * may clear the emergency prop immediately. Once an event is scheduled, only
 * AI deactivation or component disposal should cancel it.
 */
export class AIAgentScheduler<TThreat = unknown> {
  private callbacks: AIAgentSchedulerCallbacks<TThreat>;

  private active = false;

  private initialAssessmentTimer: TimerHandle | null = null;

  private readonly emergencyTimers = new Map<string, TimerHandle>();

  private readonly scheduledEmergencyIds = new Set<string>();

  private readonly handledEmergencyIds = new Set<string>();

  constructor(callbacks: AIAgentSchedulerCallbacks<TThreat>) {
    this.callbacks = callbacks;
  }

  updateCallbacks(callbacks: AIAgentSchedulerCallbacks<TThreat>): void {
    this.callbacks = callbacks;
  }

  setActive(active: boolean): void {
    this.active = active;
    if (!active) {
      this.cancelPendingTimers();
    }
  }

  scheduleInitialAssessment(): boolean {
    if (!this.active || this.initialAssessmentTimer !== null) return false;

    const delay = normalizeDelay(this.callbacks.getDelayMs(), 1500);
    this.initialAssessmentTimer = globalThis.setTimeout(() => {
      this.initialAssessmentTimer = null;
      if (!this.active) return;

      const threat = this.getBestThreatSafely('initial assessment');
      if (threat === null || threat === undefined) {
        console.info('[AI Agent] No threats found for initial assessment.');
        return;
      }

      this.handleThreatSafely(threat, 'initial assessment');
    }, delay);
    return true;
  }

  scheduleEmergency(emergencyId: string): boolean {
    if (
      !this.active ||
      !emergencyId ||
      this.scheduledEmergencyIds.has(emergencyId) ||
      this.handledEmergencyIds.has(emergencyId)
    ) {
      return false;
    }

    this.scheduledEmergencyIds.add(emergencyId);
    const delay = normalizeDelay(this.callbacks.getDelayMs(), 1500);
    this.scheduleEmergencyAttempt(emergencyId, 0, delay);
    return true;
  }

  dispose(): void {
    this.active = false;
    this.cancelPendingTimers();
  }

  private scheduleEmergencyAttempt(
    emergencyId: string,
    attemptIndex: number,
    delay: number,
  ): void {
    const timer = globalThis.setTimeout(() => {
      this.emergencyTimers.delete(emergencyId);
      if (!this.active) {
        this.scheduledEmergencyIds.delete(emergencyId);
        return;
      }

      const threat = this.getBestThreatSafely(`emergency ${emergencyId}`);
      if (threat !== null && threat !== undefined) {
        const handled = this.handleThreatSafely(threat, `emergency ${emergencyId}`);
        this.scheduledEmergencyIds.delete(emergencyId);
        if (handled) {
          this.handledEmergencyIds.add(emergencyId);
        }
        return;
      }

      const nextAttemptIndex = attemptIndex + 1;
      if (nextAttemptIndex < AI_THREAT_MAX_ATTEMPTS) {
        this.scheduleEmergencyAttempt(
          emergencyId,
          nextAttemptIndex,
          AI_THREAT_RETRY_DELAY_MS,
        );
        return;
      }

      this.scheduledEmergencyIds.delete(emergencyId);
      console.error(
        `[AI Agent] Emergency selection failed after ${AI_THREAT_MAX_ATTEMPTS} attempts: ${emergencyId}`,
      );
    }, normalizeDelay(delay, AI_THREAT_RETRY_DELAY_MS));

    this.emergencyTimers.set(emergencyId, timer);
  }

  private getBestThreatSafely(context: string): TThreat | null | undefined {
    try {
      return this.callbacks.getBestThreat();
    } catch (error) {
      console.error(`[AI Agent] Failed to evaluate threats for ${context}:`, error);
      return null;
    }
  }

  private handleThreatSafely(threat: TThreat, context: string): boolean {
    try {
      this.callbacks.onHandleEmergency(threat);
      return true;
    } catch (error) {
      console.error(`[AI Agent] Failed to handle ${context}:`, error);
      return false;
    }
  }

  private cancelPendingTimers(): void {
    if (this.initialAssessmentTimer !== null) {
      globalThis.clearTimeout(this.initialAssessmentTimer);
      this.initialAssessmentTimer = null;
    }

    this.emergencyTimers.forEach(timer => globalThis.clearTimeout(timer));
    this.emergencyTimers.clear();
    this.scheduledEmergencyIds.clear();
  }
}
