import { useEffect, useMemo, useRef } from 'react';
import { globalWS } from './useRadarData';
import type { TrustTrialSnapshot } from '../types/trustControl';

const AOI_NAMES = [
  'left_ai_target',
  'left_candidate_list',
  'right_ai_history_accuracy',
  'right_recommendation',
  'right_candidate_list',
  'right_detail',
  'right_comparison',
] as const;

type AoiName = typeof AOI_NAMES[number];
type ChangeReason =
  | 'trial_started'
  | 'geometry_changed'
  | 'visibility_changed'
  | 'semantic_binding_changed'
  | 'viewport_changed'
  | 'fullscreen_changed'
  | 'websocket_reconnected';

interface MeasuredSnapshot {
  canonical: string;
  display: Record<string, number | boolean>;
  regions: Array<Record<string, unknown>>;
}

const raf = () => new Promise<void>(resolve => window.requestAnimationFrame(() => resolve()));

const digestSha256 = async (value: string) => {
  if (window.crypto?.subtle) {
    const bytes = new TextEncoder().encode(value);
    const digest = await window.crypto.subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(digest))
      .map(byte => byte.toString(16).padStart(2, '0'))
      .join('');
  }
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `fnv1a32:${(hash >>> 0).toString(16).padStart(8, '0')}`;
};

const createClientSnapshotId = () => (
  window.crypto?.randomUUID?.()
  ?? `aoi-${Date.now()}-${Math.random().toString(16).slice(2)}`
);

const bindingFor = (name: AoiName, snapshot: TrustTrialSnapshot) => {
  const candidateIds = snapshot.candidates.map(candidate => String(candidate.id)).sort();
  const detailCandidate = snapshot.manualReviewActive
    ? snapshot.manualReviewCandidate
    : snapshot.focusedCandidate;
  switch (name) {
    case 'right_ai_history_accuracy':
      return { metric: 'ai_history_accuracy' };
    case 'left_ai_target':
    case 'right_recommendation':
      return { target_id: snapshot.aiRecommendation?.id ?? null };
    case 'left_candidate_list':
    case 'right_candidate_list':
      return { candidate_ids: candidateIds };
    case 'right_detail':
      return {
        mode: snapshot.manualReviewActive
          ? 'manual_review'
          : detailCandidate ? 'tdc_detail' : 'empty',
        target_id: detailCandidate?.id ?? null,
      };
    case 'right_comparison':
      return {
        mode: snapshot.comparisonVisible ? 'comparison' : 'hidden',
        ai_target_id: snapshot.aiRecommendation?.id ?? null,
        human_target_id: snapshot.humanSelection?.id ?? null,
      };
  }
};

const semanticKeyFor = (snapshot: TrustTrialSnapshot | null) => {
  if (!snapshot) return '';
  return JSON.stringify({
    ai: snapshot.aiRecommendation?.id ?? null,
    candidates: snapshot.candidates.map(candidate => String(candidate.id)).sort(),
    focused: snapshot.focusedCandidate?.id ?? null,
    human: snapshot.humanSelection?.id ?? null,
    manualReviewActive: snapshot.manualReviewActive,
    manualReviewTarget: snapshot.manualReviewCandidate?.id ?? null,
    comparisonVisible: snapshot.comparisonVisible,
  });
};

export function useTrustAoiSnapshot(snapshot: TrustTrialSnapshot | null) {
  const snapshotRef = useRef(snapshot);
  const scheduleRef = useRef<((reason: ChangeReason) => void) | null>(null);
  const semanticKey = useMemo(() => semanticKeyFor(snapshot), [snapshot]);
  snapshotRef.current = snapshot;

  useEffect(() => {
    scheduleRef.current?.('semantic_binding_changed');
  }, [semanticKey]);

  useEffect(() => {
    if (!snapshot?.taskId || !snapshot.control?.enabled) return;

    let disposed = false;
    let measuring = false;
    let throttleTimer: number | null = null;
    let retryTimer: number | null = null;
    let lastSentAt = 0;
    let lastSentCanonical = '';
    let pendingClientSnapshotId: string | null = null;
    let pendingCanonical = '';
    let consecutiveFailures = 0;
    let lastHandledAckSequence = 0;
    const pendingReasons = new Set<ChangeReason>();
    const resizeObserver = new ResizeObserver(() => schedule('geometry_changed'));
    const observedElements = new Set<Element>();

    const refreshObservedElements = () => {
      document.querySelectorAll('[data-gaze-aoi]').forEach(element => {
        if (observedElements.has(element)) return;
        observedElements.add(element);
        resizeObserver.observe(element);
      });
    };

    const measure = (): MeasuredSnapshot | null => {
      const current = snapshotRef.current;
      if (!current?.taskId || !current.control?.enabled) return null;
      const viewportWidth = Math.max(1, window.innerWidth || 1);
      const viewportHeight = Math.max(1, window.innerHeight || 1);
      const screenWidth = Math.max(1, window.screen?.width || viewportWidth);
      const screenHeight = Math.max(1, window.screen?.height || viewportHeight);
      const dpr = Math.max(0.1, window.devicePixelRatio || 1);
      const viewportScale = window.visualViewport?.scale ?? 1;
      const screenX = Number(window.screenX || 0);
      const screenY = Number(window.screenY || 0);
      const dimensionAligned = (
        Math.abs(viewportWidth - screenWidth) * dpr <= 2
        && Math.abs(viewportHeight - screenHeight) * dpr <= 2
      );
      const originAligned = Math.abs(screenX) * dpr <= 2 && Math.abs(screenY) * dpr <= 2;
      const scaleAligned = Math.abs(viewportScale - 1) <= 0.001;
      const alignmentValid = dimensionAligned && originAligned && scaleAligned;
      const fullscreen = Boolean(document.fullscreenElement) || (dimensionAligned && originAligned);
      const quantizeCss = (value: number) => Math.round(value * dpr) / dpr;

      const display = {
        fullscreen,
        alignment_valid: alignmentValid,
        viewport_width_css_px: viewportWidth,
        viewport_height_css_px: viewportHeight,
        screen_width_css_px: screenWidth,
        screen_height_css_px: screenHeight,
        screen_width_physical_px: Math.round(screenWidth * dpr),
        screen_height_physical_px: Math.round(screenHeight * dpr),
        screen_x_css_px: screenX,
        screen_y_css_px: screenY,
        device_pixel_ratio: dpr,
        visual_viewport_scale: viewportScale,
      };

      const regions = AOI_NAMES.map(name => {
        const elements = Array.from(
          document.querySelectorAll<HTMLElement>(`[data-gaze-aoi="${name}"]`),
        );
        const element = elements.find(candidate => candidate.dataset.visible !== 'false') ?? elements[0];
        const rect = element?.getBoundingClientRect();
        const style = element ? window.getComputedStyle(element) : null;
        const explicitlyHidden = element?.dataset.visible === 'false';
        const rendered = Boolean(
          element
          && rect
          && style?.display !== 'none'
          && style?.visibility !== 'hidden'
          && rect.width > 0
          && rect.height > 0,
        );
        const visible = rendered && !explicitlyHidden;
        const leftCss = rect ? Math.max(0, Math.min(viewportWidth, quantizeCss(rect.left))) : 0;
        const topCss = rect ? Math.max(0, Math.min(viewportHeight, quantizeCss(rect.top))) : 0;
        const rightCss = rect ? Math.max(0, Math.min(viewportWidth, quantizeCss(rect.right))) : 0;
        const bottomCss = rect ? Math.max(0, Math.min(viewportHeight, quantizeCss(rect.bottom))) : 0;
        return {
          id: name,
          shape: 'rect',
          visible,
          left: leftCss / viewportWidth,
          top: topCss / viewportHeight,
          right: rightCss / viewportWidth,
          bottom: bottomCss / viewportHeight,
          binding: bindingFor(name, current),
        };
      });
      const canonical = JSON.stringify({
        coordinate_space: 'display_area_normalized',
        display,
        regions,
      });
      return { canonical, display, regions };
    };

    const sendMeasured = async (measured: MeasuredSnapshot) => {
      const current = snapshotRef.current;
      if (!current?.taskId || !current.control?.enabled || disposed) return;
      if (measured.canonical === lastSentCanonical) {
        pendingReasons.clear();
        return;
      }
      const elapsed = Date.now() - lastSentAt;
      if (elapsed < 100) {
        if (throttleTimer === null) {
          throttleTimer = window.setTimeout(() => {
            throttleTimer = null;
            schedule('geometry_changed');
          }, 100 - elapsed);
        }
        return;
      }
      const reasons = Array.from(pendingReasons);
      pendingReasons.clear();
      const layoutSignature = await digestSha256(measured.canonical);
      if (disposed) return;
      const clientSnapshotId = createClientSnapshotId();
      const sent = globalWS.sendMessage({
        type: 'tobii_aoi_snapshot',
        task_id: String(current.taskId),
        trial_id: String(current.taskId),
        task_group_id: current.taskGroupId,
        task_type: current.taskType,
        client_snapshot_id: clientSnapshotId,
        captured_at_ms: Date.now(),
        change_reasons: reasons.length > 0 ? reasons : ['geometry_changed'],
        layout_signature: layoutSignature,
        coordinate_space: 'display_area_normalized',
        display: measured.display,
        regions: measured.regions,
      });
      if (sent) {
        lastSentCanonical = measured.canonical;
        pendingCanonical = measured.canonical;
        pendingClientSnapshotId = clientSnapshotId;
        lastSentAt = Date.now();
      } else {
        reasons.forEach(reason => pendingReasons.add(reason));
      }
    };

    const runMeasurement = async () => {
      if (measuring || disposed) return;
      measuring = true;
      const startedAt = performance.now();
      let previous: MeasuredSnapshot | null = null;
      try {
        while (!disposed) {
          await raf();
          refreshObservedElements();
          const current = measure();
          if (!current) return;
          if (previous?.canonical === current.canonical || performance.now() - startedAt >= 100) {
            await sendMeasured(current);
            return;
          }
          previous = current;
        }
      } finally {
        measuring = false;
        if (
          !disposed
          && globalWS.isOpen()
          && pendingReasons.size > 0
          && measure()?.canonical !== lastSentCanonical
        ) {
          window.requestAnimationFrame(() => void runMeasurement());
        }
      }
    };

    function schedule(reason: ChangeReason) {
      if (disposed) return;
      pendingReasons.add(reason);
      void runMeasurement();
    }

    scheduleRef.current = schedule;
    refreshObservedElements();

    const mutationObserver = new MutationObserver(mutations => {
      refreshObservedElements();
      const visibilityChanged = mutations.some(mutation => (
        mutation.type === 'attributes' && mutation.attributeName === 'data-visible'
      ));
      schedule(visibilityChanged ? 'visibility_changed' : 'geometry_changed');
    });
    mutationObserver.observe(document.body, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ['data-visible', 'class', 'style'],
    });

    const handleResize = () => schedule('viewport_changed');
    const handleFullscreen = () => schedule('fullscreen_changed');
    const handleScroll = () => schedule('geometry_changed');
    window.addEventListener('resize', handleResize);
    window.addEventListener('scroll', handleScroll, true);
    document.addEventListener('fullscreenchange', handleFullscreen);
    window.visualViewport?.addEventListener('resize', handleResize);
    window.visualViewport?.addEventListener('scroll', handleScroll);

    let wasConnected = globalWS.isOpen();
    const unsubscribe = globalWS.subscribe(state => {
      if (!wasConnected && state.connected) schedule('websocket_reconnected');
      wasConnected = state.connected;
      const response = globalWS.getLastMessage();
      const responseSequence = Number(response?.__message_seq || 0);
      if (
        response?.type === 'tobii_aoi_snapshot_result'
        && responseSequence > lastHandledAckSequence
      ) {
        lastHandledAckSequence = responseSequence;
        if (response.client_snapshot_id === pendingClientSnapshotId) {
          if (response.ok === false) {
            if (lastSentCanonical === pendingCanonical) lastSentCanonical = '';
            consecutiveFailures += 1;
            if (consecutiveFailures <= 10 && retryTimer === null) {
              retryTimer = window.setTimeout(() => {
                retryTimer = null;
                schedule('websocket_reconnected');
              }, 1000);
            }
          } else {
            consecutiveFailures = 0;
          }
          pendingClientSnapshotId = null;
          pendingCanonical = '';
        }
      }
    });
    schedule('trial_started');

    return () => {
      disposed = true;
      scheduleRef.current = null;
      mutationObserver.disconnect();
      resizeObserver.disconnect();
      unsubscribe();
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('scroll', handleScroll, true);
      document.removeEventListener('fullscreenchange', handleFullscreen);
      window.visualViewport?.removeEventListener('resize', handleResize);
      window.visualViewport?.removeEventListener('scroll', handleScroll);
      if (throttleTimer !== null) window.clearTimeout(throttleTimer);
      if (retryTimer !== null) window.clearTimeout(retryTimer);
    };
  }, [snapshot?.control?.enabled, snapshot?.taskId]);
}
