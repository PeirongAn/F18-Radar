import React, { useEffect, useRef, useState } from 'react';

interface GazePointOverlayProps {
  enabled: boolean;
  onGazePointChange?: (point: GazePointDebug | null) => void;
}

interface GazeDataResponse {
  ok?: boolean;
  gaze_point?: unknown;
}

interface ViewportSize {
  width: number;
  height: number;
}

interface NormalizedGazePoint {
  x: number;
  y: number;
}

export interface GazePointDebug {
  normalizedX: number;
  normalizedY: number;
  pixelX: number;
  pixelY: number;
  viewportWidth: number;
  viewportHeight: number;
}

const POLL_INTERVAL_MS = 100;
const GAZE_POINT_PATH = '/tobii/gaze_point';
const GAZE_OVERLAY_Z_INDEX = 12000;

function resolveGazePointUrl(): string {
  return GAZE_POINT_PATH;
}

function clampNormalized(value: number): number {
  if (value < 0) return 0;
  if (value > 1) return 1;
  return value;
}

function parseGazePoint(data: GazeDataResponse): NormalizedGazePoint | null {
  if (!data.ok || !Array.isArray(data.gaze_point) || data.gaze_point.length < 2) {
    return null;
  }

  const [rawX, rawY] = data.gaze_point;
  const x = Number(rawX);
  const y = Number(rawY);

  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    return null;
  }

  return {
    x: clampNormalized(x),
    y: clampNormalized(y),
  };
}

function toDebugPoint(point: NormalizedGazePoint, viewport: ViewportSize): GazePointDebug {
  return {
    normalizedX: point.x,
    normalizedY: point.y,
    pixelX: point.x * viewport.width,
    pixelY: point.y * viewport.height,
    viewportWidth: viewport.width,
    viewportHeight: viewport.height,
  };
}

const GazePointOverlay: React.FC<GazePointOverlayProps> = ({ enabled, onGazePointChange }) => {
  const [gazePoint, setGazePoint] = useState<NormalizedGazePoint | null>(null);
  const [viewport, setViewport] = useState<ViewportSize>(() => ({
    width: window.innerWidth,
    height: window.innerHeight,
  }));
  const requestRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const updateViewport = () => {
      setViewport({
        width: window.innerWidth,
        height: window.innerHeight,
      });
    };

    window.addEventListener('resize', updateViewport);
    return () => window.removeEventListener('resize', updateViewport);
  }, []);

  useEffect(() => {
    if (!enabled) {
      requestRef.current?.abort();
      requestRef.current = null;
      setGazePoint(null);
      onGazePointChange?.(null);
      return;
    }

    let stopped = false;

    const fetchGazePoint = async () => {
      if (requestRef.current) {
        return;
      }

      const controller = new AbortController();
      requestRef.current = controller;

      try {
        const response = await fetch(resolveGazePointUrl(), {
          cache: 'no-store',
          signal: controller.signal,
        });

        if (!response.ok) {
          if (!stopped) {
            setGazePoint(null);
            onGazePointChange?.(null);
          }
          return;
        }

        const data = await response.json() as GazeDataResponse;
        const nextGazePoint = parseGazePoint(data);

        if (!stopped) {
          setGazePoint(nextGazePoint);
          onGazePointChange?.(nextGazePoint ? toDebugPoint(nextGazePoint, viewport) : null);
        }
      } catch (error) {
        if (!stopped && !(error instanceof DOMException && error.name === 'AbortError')) {
          setGazePoint(null);
          onGazePointChange?.(null);
        }
      } finally {
        if (requestRef.current === controller) {
          requestRef.current = null;
        }
      }
    };

    fetchGazePoint();
    const intervalId = window.setInterval(fetchGazePoint, POLL_INTERVAL_MS);

    return () => {
      stopped = true;
      window.clearInterval(intervalId);
      requestRef.current?.abort();
      requestRef.current = null;
      setGazePoint(null);
      onGazePointChange?.(null);
    };
  }, [enabled, onGazePointChange, viewport]);

  if (!enabled || !gazePoint) {
    return null;
  }

  const left = gazePoint.x * viewport.width;
  const top = gazePoint.y * viewport.height;

  return (
    <div
      aria-hidden="true"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: GAZE_OVERLAY_Z_INDEX,
        pointerEvents: 'none',
      }}
    >
      <div
        style={{
          position: 'absolute',
          left,
          top,
          width: '28px',
          height: '28px',
          transform: 'translate(-50%, -50%)',
          border: '2px solid rgba(255, 68, 36, 0.98)',
          borderRadius: '50%',
          boxShadow: '0 0 18px rgba(255, 68, 36, 0.85), 0 0 4px rgba(255, 245, 190, 0.9), inset 0 0 10px rgba(255, 190, 40, 0.22)',
          animation: 'pulse-dot 1s ease-in-out infinite',
        }}
      >
        <span
          style={{
            position: 'absolute',
            left: '50%',
            top: '-7px',
            width: '1px',
            height: '42px',
            transform: 'translateX(-50%)',
            background: 'rgba(255, 230, 72, 0.92)',
          }}
        />
        <span
          style={{
            position: 'absolute',
            left: '-7px',
            top: '50%',
            width: '42px',
            height: '1px',
            transform: 'translateY(-50%)',
            background: 'rgba(255, 230, 72, 0.92)',
          }}
        />
        <span
          style={{
            position: 'absolute',
            left: '50%',
            top: '50%',
            width: '5px',
            height: '5px',
            transform: 'translate(-50%, -50%)',
            borderRadius: '50%',
            background: '#fff2a6',
            boxShadow: '0 0 10px rgba(255, 242, 166, 1)',
          }}
        />
      </div>
    </div>
  );
};

export default GazePointOverlay;
