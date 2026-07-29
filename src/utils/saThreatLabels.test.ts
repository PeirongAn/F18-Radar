import { describe, expect, it } from 'vitest';
import {
  buildSaThreatDisplayLabels,
  createSaThreatLabelOrderState,
} from './saThreatLabels';

describe('buildSaThreatDisplayLabels', () => {
  it('does not add brackets to unique labels', () => {
    const labels = buildSaThreatDisplayLabels([
      { id: 'f16-a', label: 'F-16' },
      { id: 'mig-a', label: 'MiG-29' },
    ], createSaThreatLabelOrderState());

    expect(labels.get('f16-a')).toBe('F-16');
    expect(labels.get('mig-a')).toBe('MiG-29');
  });

  it('numbers only duplicate labels from one', () => {
    const labels = buildSaThreatDisplayLabels([
      { id: 'f16-a', label: 'F-16' },
      { id: 'f16-b', label: 'F-16' },
      { id: 'mig-a', label: 'MiG-29' },
    ], createSaThreatLabelOrderState());

    expect(labels.get('f16-a')).toBe('F-16 [1]');
    expect(labels.get('f16-b')).toBe('F-16 [2]');
    expect(labels.get('mig-a')).toBe('MiG-29');
  });

  it('keeps duplicate numbers stable when the display array is reordered', () => {
    const orderState = createSaThreatLabelOrderState();
    buildSaThreatDisplayLabels([
      { id: 'f16-a', label: 'F-16' },
      { id: 'f16-b', label: 'F-16' },
    ], orderState);

    const labels = buildSaThreatDisplayLabels([
      { id: 'f16-b', label: 'F-16' },
      { id: 'f16-a', label: 'F-16' },
    ], orderState);

    expect(labels.get('f16-a')).toBe('F-16 [1]');
    expect(labels.get('f16-b')).toBe('F-16 [2]');
  });

  it('deduplicates the same target id before counting repeated labels', () => {
    const labels = buildSaThreatDisplayLabels([
      { id: 'missile-a', label: '上升导弹', type: 'MissileUp' },
      { id: 'missile-a', label: '上升导弹', type: 'MissileUp' },
    ], createSaThreatLabelOrderState());

    expect(labels.get('missile-a')).toBe('上升导弹');
  });
});
