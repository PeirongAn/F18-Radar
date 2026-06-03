import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

type Stage = 'idle' | 'sampling' | 'ready' | 'verify';

interface GazePoint {
  x: number;
  y: number;
}

interface CalibrationPoint {
  id: string;
  label: string;
  x: number;
  y: number;
}

interface SampleResult {
  target: CalibrationPoint;
  observed: GazePoint | null;
  count: number;
}

interface CalibrationParams {
  scaleX: number;
  scaleY: number;
  offsetX: number;
  offsetY: number;
  samples: number;
  updatedAt: number;
  method: 'linear' | 'local_weighted';
  controlPoints: CalibrationControlPoint[];
}

interface CalibrationControlPoint {
  observedX: number;
  observedY: number;
  targetX: number;
  targetY: number;
  deltaX: number;
  deltaY: number;
}

interface GazeResponse {
  ok?: boolean;
  gaze_point?: unknown;
}

const STORAGE_KEY = 'f18_gaze_calibration_v1';
const GAZE_PATH = '/tobii/gaze_point';
const POLL_MS = 80;
const SAMPLE_MS = 1600;
const TARGET_SIZE = 0.032;

const POINTS: CalibrationPoint[] = [
  { id: 'lt', label: '左上', x: 0.16, y: 0.18 },
  { id: 'ct', label: '上中', x: 0.5, y: 0.18 },
  { id: 'rt', label: '右上', x: 0.84, y: 0.18 },
  { id: 'lm', label: '左中', x: 0.16, y: 0.5 },
  { id: 'cm', label: '中心', x: 0.5, y: 0.5 },
  { id: 'rm', label: '右中', x: 0.84, y: 0.5 },
  { id: 'lb', label: '左下', x: 0.16, y: 0.82 },
  { id: 'cb', label: '下中', x: 0.5, y: 0.82 },
  { id: 'rb', label: '右下', x: 0.84, y: 0.82 },
];

const VERIFY_TARGETS: CalibrationPoint[] = [
  { id: 'v1', label: '验证 1', x: 0.28, y: 0.32 },
  { id: 'v2', label: '验证 2', x: 0.69, y: 0.38 },
  { id: 'v3', label: '验证 3', x: 0.42, y: 0.72 },
  { id: 'v4', label: '验证 4', x: 0.76, y: 0.75 },
];

const EMPTY_PARAMS: CalibrationParams = {
  scaleX: 1,
  scaleY: 1,
  offsetX: 0,
  offsetY: 0,
  samples: 0,
  updatedAt: 0,
  method: 'local_weighted',
  controlPoints: [],
};

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function parseGaze(data: GazeResponse): GazePoint | null {
  if (!data.ok || !Array.isArray(data.gaze_point) || data.gaze_point.length < 2) return null;
  const x = Number(data.gaze_point[0]);
  const y = Number(data.gaze_point[1]);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return { x: clamp01(x), y: clamp01(y) };
}

function median(values: number[]): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function fitAxis(observed: number[], expected: number[]): { scale: number; offset: number } {
  if (observed.length < 2) {
    const delta = expected.reduce((sum, value, index) => sum + value - observed[index], 0) / Math.max(1, observed.length);
    return { scale: 1, offset: Number.isFinite(delta) ? delta : 0 };
  }

  const meanObserved = observed.reduce((sum, value) => sum + value, 0) / observed.length;
  const meanExpected = expected.reduce((sum, value) => sum + value, 0) / expected.length;
  let numerator = 0;
  let denominator = 0;
  observed.forEach((value, index) => {
    numerator += (value - meanObserved) * (expected[index] - meanExpected);
    denominator += (value - meanObserved) ** 2;
  });
  const scale = denominator > 0.000001 ? numerator / denominator : 1;
  return {
    scale: Number.isFinite(scale) ? scale : 1,
    offset: meanExpected - (Number.isFinite(scale) ? scale : 1) * meanObserved,
  };
}

function buildParams(results: SampleResult[]): CalibrationParams {
  const valid = results.filter((result): result is SampleResult & { observed: GazePoint } => !!result.observed);
  const xFit = fitAxis(valid.map(result => result.observed.x), valid.map(result => result.target.x));
  const yFit = fitAxis(valid.map(result => result.observed.y), valid.map(result => result.target.y));
  const controlPoints = valid.map(result => ({
    observedX: result.observed.x,
    observedY: result.observed.y,
    targetX: result.target.x,
    targetY: result.target.y,
    deltaX: result.target.x - result.observed.x,
    deltaY: result.target.y - result.observed.y,
  }));
  return {
    scaleX: xFit.scale,
    scaleY: yFit.scale,
    offsetX: xFit.offset,
    offsetY: yFit.offset,
    samples: valid.length,
    updatedAt: Date.now(),
    method: valid.length >= 3 ? 'local_weighted' : 'linear',
    controlPoints,
  };
}

function applyCalibration(point: GazePoint | null, params: CalibrationParams): GazePoint | null {
  if (!point) return null;
  if (params.method === 'local_weighted' && params.controlPoints.length >= 3) {
    let weightSum = 0;
    let deltaX = 0;
    let deltaY = 0;

    for (const control of params.controlPoints) {
      const dx = point.x - control.observedX;
      const dy = point.y - control.observedY;
      const distanceSquared = dx * dx + dy * dy;
      if (distanceSquared < 0.000001) {
        return {
          x: clamp01(point.x + control.deltaX),
          y: clamp01(point.y + control.deltaY),
        };
      }
      const weight = 1 / Math.pow(distanceSquared, 1.2);
      weightSum += weight;
      deltaX += control.deltaX * weight;
      deltaY += control.deltaY * weight;
    }

    if (weightSum > 0) {
      return {
        x: clamp01(point.x + deltaX / weightSum),
        y: clamp01(point.y + deltaY / weightSum),
      };
    }
  }

  return {
    x: clamp01(point.x * params.scaleX + params.offsetX),
    y: clamp01(point.y * params.scaleY + params.offsetY),
  };
}

function inTarget(point: GazePoint | null, target: CalibrationPoint): boolean {
  if (!point) return false;
  const half = TARGET_SIZE / 2;
  return point.x >= target.x - half && point.x <= target.x + half && point.y >= target.y - half && point.y <= target.y + half;
}

function fmt(value: number | null | undefined, digits = 4): string {
  return Number.isFinite(value) ? Number(value).toFixed(digits) : '--';
}

const metricLabelStyle: React.CSSProperties = {
  color: '#5c8f6b',
  fontSize: '12px',
  letterSpacing: '0.14em',
};

const metricValueStyle: React.CSSProperties = {
  color: '#bfe9c8',
  fontFamily: "'Share Tech Mono', 'Consolas', monospace",
  fontSize: '13px',
  textAlign: 'right',
};

const buttonStyle: React.CSSProperties = {
  border: '1px solid #21492e',
  borderRadius: 4,
  background: 'rgba(6, 28, 12, 0.88)',
  color: '#bdeec8',
  padding: '9px 14px',
  cursor: 'pointer',
  fontFamily: "'SimHei', 'Microsoft YaHei', sans-serif",
  fontSize: 13,
  letterSpacing: '0.08em',
};

const primaryButtonStyle: React.CSSProperties = {
  ...buttonStyle,
  border: '1px solid #b17822',
  background: 'rgba(77, 44, 8, 0.86)',
  color: '#ffd68a',
};

const GazeCalibrationPage: React.FC = () => {
  const [stage, setStage] = useState<Stage>('idle');
  const [activeIndex, setActiveIndex] = useState(0);
  const [results, setResults] = useState<SampleResult[]>([]);
  const [rawGaze, setRawGaze] = useState<GazePoint | null>(null);
  const [params, setParams] = useState<CalibrationParams>(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      return saved ? { ...EMPTY_PARAMS, ...JSON.parse(saved) } : EMPTY_PARAMS;
    } catch {
      return EMPTY_PARAMS;
    }
  });
  const [sampleProgress, setSampleProgress] = useState(0);
  const [verifyIndex, setVerifyIndex] = useState(0);
  const [hitFrames, setHitFrames] = useState(0);
  const [missFrames, setMissFrames] = useState(0);
  const [statusText, setStatusText] = useState('等待开始');
  const sampleBufferRef = useRef<GazePoint[]>([]);
  const sampleStartRef = useRef(0);

  const activePoint = POINTS[activeIndex] ?? POINTS[0];
  const verifyTarget = VERIFY_TARGETS[verifyIndex] ?? VERIFY_TARGETS[0];
  const correctedGaze = useMemo(() => applyCalibration(rawGaze, params), [rawGaze, params]);
  const verifyHit = inTarget(correctedGaze, verifyTarget);

  useEffect(() => {
    let stopped = false;
    let controller: AbortController | null = null;

    const tick = async () => {
      if (controller) return;
      controller = new AbortController();
      try {
        const response = await fetch(GAZE_PATH, { cache: 'no-store', signal: controller.signal });
        const data = await response.json() as GazeResponse;
        const point = parseGaze(data);
        if (!stopped) {
          setRawGaze(point);
          if (stage === 'sampling' && point) {
            sampleBufferRef.current.push(point);
          }
        }
      } catch {
        if (!stopped) setRawGaze(null);
      } finally {
        controller = null;
      }
    };

    tick();
    const timer = window.setInterval(tick, POLL_MS);
    return () => {
      stopped = true;
      window.clearInterval(timer);
      controller?.abort();
    };
  }, [stage]);

  useEffect(() => {
    if (stage !== 'sampling') return;
    const timer = window.setInterval(() => {
      const elapsed = Date.now() - sampleStartRef.current;
      setSampleProgress(Math.min(1, elapsed / SAMPLE_MS));
    }, 50);
    return () => window.clearInterval(timer);
  }, [stage]);

  useEffect(() => {
    if (stage !== 'verify') return;
    if (verifyHit) {
      setHitFrames(prev => prev + 1);
      setMissFrames(0);
    } else {
      setMissFrames(prev => prev + 1);
      setHitFrames(0);
    }
  }, [stage, verifyHit, correctedGaze?.x, correctedGaze?.y]);

  const finishSample = useCallback((target: CalibrationPoint, index: number) => {
    const samples = sampleBufferRef.current;
    const observed = samples.length
      ? { x: median(samples.map(point => point.x)), y: median(samples.map(point => point.y)) }
      : null;
    setResults(prev => {
      const next = [...prev];
      next[index] = { target, observed, count: samples.length };
      const complete = next.filter(Boolean).length >= POINTS.length;
      if (complete) {
        const nextParams = buildParams(next);
        setParams(nextParams);
        setStage('ready');
        setStatusText('校准完成，进入验证或保存参数');
      } else {
        setActiveIndex(Math.min(index + 1, POINTS.length - 1));
        setStage('idle');
        setStatusText('当前点采样完成');
      }
      return next;
    });
  }, []);

  const startSample = useCallback(() => {
    sampleBufferRef.current = [];
    sampleStartRef.current = Date.now();
    setSampleProgress(0);
    setStage('sampling');
    setStatusText(`正在采样：${activePoint.label}`);
    window.setTimeout(() => finishSample(activePoint, activeIndex), SAMPLE_MS);
  }, [activeIndex, activePoint, finishSample]);

  const resetAll = useCallback(() => {
    setStage('idle');
    setActiveIndex(0);
    setResults([]);
    setParams(EMPTY_PARAMS);
    setSampleProgress(0);
    setHitFrames(0);
    setMissFrames(0);
    setStatusText('已重置');
    window.localStorage.removeItem(STORAGE_KEY);
  }, []);

  const saveParams = useCallback(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(params));
    setStatusText('校准参数已保存到本机');
  }, [params]);

  const startVerify = useCallback(() => {
    setStage('verify');
    setHitFrames(0);
    setMissFrames(0);
    setStatusText('验证模式：请注视黄色目标框');
  }, []);

  const nextVerifyTarget = useCallback(() => {
    setVerifyIndex(prev => (prev + 1) % VERIFY_TARGETS.length);
    setHitFrames(0);
    setMissFrames(0);
  }, []);

  const activeMarker = stage === 'verify' ? verifyTarget : activePoint;
  const markerHit = stage === 'verify' ? verifyHit : inTarget(correctedGaze, activePoint);
  const currentResult = results[activeIndex];
  const validSamples = results.filter(result => result?.observed).length;

  return (
    <div
      style={{
        height: '100vh',
        background: '#030706',
        color: '#bfe9c8',
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 1fr) 360px',
        gridTemplateRows: '54px minmax(0, 1fr) 74px',
        fontFamily: "'SimHei', 'Microsoft YaHei', sans-serif",
        overflow: 'hidden',
      }}
    >
      <header
        style={{
          gridColumn: '1 / 3',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 20px',
          borderBottom: '1px solid #12341d',
          background: '#07100a',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14 }}>
          <h1 style={{ margin: 0, color: '#e8f3dc', fontSize: 20, letterSpacing: '0.18em' }}>眼动校准</h1>
          <span style={{ color: '#608d6b', fontSize: 12, letterSpacing: '0.12em' }}>GAZE POINT CORRECTION</span>
        </div>
        <div style={{ color: markerHit ? '#71ff9b' : '#ff695d', fontFamily: "'Share Tech Mono', monospace", fontSize: 14 }}>
          {markerHit ? 'HIT' : 'MISS'} / {statusText}
        </div>
      </header>

      <main
        style={{
          position: 'relative',
          overflow: 'hidden',
          borderRight: '1px solid #12341d',
          background:
            'linear-gradient(rgba(20, 78, 37, 0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(20, 78, 37, 0.08) 1px, transparent 1px), #020504',
          backgroundSize: '42px 42px',
        }}
      >
        {POINTS.map((point, index) => {
          const result = results[index];
          const isActive = point.id === activeMarker.id && stage !== 'verify';
          return (
            <div
              key={point.id}
              style={{
                position: 'absolute',
                left: `${point.x * 100}%`,
                top: `${point.y * 100}%`,
                transform: 'translate(-50%, -50%)',
                width: isActive ? 34 : 18,
                height: isActive ? 34 : 18,
                borderRadius: '50%',
                border: `1px solid ${isActive ? '#ffbf4a' : result?.observed ? '#5dd989' : '#254932'}`,
                boxShadow: isActive ? '0 0 24px rgba(255, 178, 52, 0.55)' : 'none',
                background: isActive ? 'rgba(255, 177, 44, 0.18)' : 'rgba(11, 44, 20, 0.38)',
              }}
            />
          );
        })}

        <div
          style={{
            position: 'absolute',
            left: `${activeMarker.x * 100}%`,
            top: `${activeMarker.y * 100}%`,
            width: `${TARGET_SIZE * 100}%`,
            height: `${TARGET_SIZE * 100}%`,
            transform: 'translate(-50%, -50%)',
            border: `2px solid ${markerHit ? '#59ff86' : '#ffbc45'}`,
            boxShadow: markerHit ? '0 0 24px rgba(89,255,134,0.35)' : '0 0 26px rgba(255,188,69,0.45)',
            background: markerHit ? 'rgba(44, 150, 67, 0.12)' : 'rgba(99, 58, 8, 0.16)',
          }}
        />

        {correctedGaze && (
          <div
            style={{
              position: 'absolute',
              left: `${correctedGaze.x * 100}%`,
              top: `${correctedGaze.y * 100}%`,
              width: 28,
              height: 28,
              transform: 'translate(-50%, -50%)',
              border: '2px solid #ff3e2e',
              borderRadius: '50%',
              boxShadow: '0 0 18px rgba(255, 62, 46, 0.75)',
              pointerEvents: 'none',
            }}
          >
            <span style={{ position: 'absolute', left: '50%', top: -8, width: 1, height: 44, background: '#ffd15e' }} />
            <span style={{ position: 'absolute', top: '50%', left: -8, width: 44, height: 1, background: '#ffd15e' }} />
          </div>
        )}

        {rawGaze && correctedGaze && (
          <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
            <line
              x1={`${rawGaze.x * 100}%`}
              y1={`${rawGaze.y * 100}%`}
              x2={`${correctedGaze.x * 100}%`}
              y2={`${correctedGaze.y * 100}%`}
              stroke="rgba(255, 207, 93, 0.42)"
              strokeDasharray="4 5"
            />
          </svg>
        )}
      </main>

      <aside style={{ padding: 16, overflow: 'auto', background: '#07100a' }}>
        <Panel title="实时注视">
          <Metric label="raw x/y" value={`${fmt(rawGaze?.x)} / ${fmt(rawGaze?.y)}`} />
          <Metric label="corrected x/y" value={`${fmt(correctedGaze?.x)} / ${fmt(correctedGaze?.y)}`} />
          <Metric label="状态" value={rawGaze ? '有效' : '无信号'} color={rawGaze ? '#7dffa3' : '#ff6a58'} />
        </Panel>
        <Panel title="当前目标">
          <Metric label="目标" value={activeMarker.label} />
          <Metric label="target x/y" value={`${fmt(activeMarker.x)} / ${fmt(activeMarker.y)}`} />
          <Metric label="hit frames" value={String(hitFrames)} color="#7dffa3" />
          <Metric label="miss frames" value={String(missFrames)} color="#ff836e" />
        </Panel>
        <Panel title="校准参数">
          <Metric label="method" value={params.method === 'local_weighted' ? '局部加权' : '线性'} />
          <Metric label="控制点" value={String(params.controlPoints.length)} />
          <Metric label="scaleX" value={fmt(params.scaleX, 5)} />
          <Metric label="scaleY" value={fmt(params.scaleY, 5)} />
          <Metric label="offsetX" value={fmt(params.offsetX, 5)} />
          <Metric label="offsetY" value={fmt(params.offsetY, 5)} />
          <Metric label="有效点" value={`${validSamples}/${POINTS.length}`} />
        </Panel>
        <Panel title="当前采样">
          <Metric label="样本数" value={String(currentResult?.count ?? sampleBufferRef.current.length)} />
          <Metric label="observed" value={currentResult?.observed ? `${fmt(currentResult.observed.x)} / ${fmt(currentResult.observed.y)}` : '--'} />
          <div style={{ height: 6, background: '#102217', border: '1px solid #1d4a2b', marginTop: 10 }}>
            <div style={{ width: `${sampleProgress * 100}%`, height: '100%', background: '#d6942f' }} />
          </div>
        </Panel>
      </aside>

      <footer
        style={{
          gridColumn: '1 / 3',
          display: 'grid',
          gridTemplateColumns: '1fr auto',
          gap: 16,
          alignItems: 'center',
          padding: '12px 16px',
          borderTop: '1px solid #12341d',
          background: '#07100a',
        }}
      >
        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${POINTS.length}, 1fr)`, gap: 6 }}>
          {POINTS.map((point, index) => (
            <div
              key={point.id}
              style={{
                height: 8,
                background: results[index]?.observed ? '#5dd989' : index === activeIndex ? '#d6942f' : '#183423',
                border: '1px solid #244a30',
              }}
              title={point.label}
            />
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" style={primaryButtonStyle} onClick={startSample} disabled={stage === 'sampling'}>
            {results.length ? '采样当前点' : '开始校准'}
          </button>
          <button type="button" style={buttonStyle} onClick={startVerify} disabled={params.samples < 2}>
            验证
          </button>
          <button type="button" style={buttonStyle} onClick={nextVerifyTarget} disabled={stage !== 'verify'}>
            下一目标
          </button>
          <button type="button" style={buttonStyle} onClick={saveParams} disabled={params.samples < 2}>
            保存校准
          </button>
          <button type="button" style={buttonStyle} onClick={resetAll}>
            重置
          </button>
        </div>
      </footer>
    </div>
  );
};

const Panel: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <section style={{ border: '1px solid #153722', borderRadius: 4, padding: 12, marginBottom: 12, background: 'rgba(4, 19, 9, 0.78)' }}>
    <div style={{ color: '#8fc996', fontSize: 12, letterSpacing: '0.2em', marginBottom: 10 }}>{title}</div>
    <div style={{ display: 'grid', gap: 7 }}>{children}</div>
  </section>
);

const Metric: React.FC<{ label: string; value: string; color?: string }> = ({ label, value, color }) => (
  <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 10 }}>
    <span style={metricLabelStyle}>{label}</span>
    <span style={{ ...metricValueStyle, color: color ?? metricValueStyle.color }}>{value}</span>
  </div>
);

export default GazeCalibrationPage;
