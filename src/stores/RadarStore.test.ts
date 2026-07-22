import { describe, expect, it } from 'vitest';
import {
  RadarStore,
  targetDisplayPositionsEqual,
} from './RadarStore';

describe('RadarStore target display positions', () => {
  it('treats separately-created maps with the same coordinates as equal', () => {
    const current = new Map([
      ['enemy-1', { x: 120, y: 240 }],
      ['friend-1', { x: 360, y: 180 }],
    ]);
    const next = new Map([
      ['enemy-1', { x: 120, y: 240 }],
      ['friend-1', { x: 360, y: 180 }],
    ]);

    expect(targetDisplayPositionsEqual(current, next)).toBe(true);
  });

  it('does not mutate the observable map when coordinates are unchanged', () => {
    const store = new RadarStore();
    store.setTargetDisplayPositions(new Map([
      ['enemy-1', { x: 120, y: 240 }],
    ]));
    const originalPosition = store.targetDisplayPositions.get('enemy-1');

    store.setTargetDisplayPositions(new Map([
      ['enemy-1', { x: 120, y: 240 }],
    ]));

    expect(store.targetDisplayPositions.get('enemy-1')).toBe(originalPosition);
  });

  it('updates the observable map when a coordinate changes', () => {
    const store = new RadarStore();
    store.setTargetDisplayPositions(new Map([
      ['enemy-1', { x: 120, y: 240 }],
    ]));

    store.setTargetDisplayPositions(new Map([
      ['enemy-1', { x: 121, y: 240 }],
    ]));

    expect(store.targetDisplayPositions.get('enemy-1')?.x).toBe(121);
  });
});
