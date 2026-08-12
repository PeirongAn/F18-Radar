import { describe, expect, it } from 'vitest';
import {
  isPersistentRadarAiHighlight,
  resolveRadarTargetMarkerStyle,
} from './radarTargetMarker';

describe('resolveRadarTargetMarkerStyle', () => {
  it('attaches the blue AI highlight to the selected target glyph', () => {
    expect(resolveRadarTargetMarkerStyle('#00ff00', true, true)).toEqual({
      fill: 'white',
      stroke: '#69d8ff',
      strokeWidth: 3,
      shadowColor: '#69d8ff',
      shadowBlur: 14,
    });
  });

  it('keeps the normal target style when AI highlighting is inactive', () => {
    expect(resolveRadarTargetMarkerStyle('#00ff00', false, false)).toEqual({
      fill: '#00ff00',
      stroke: '#00ff00',
      strokeWidth: 1,
      shadowColor: 'transparent',
      shadowBlur: 0,
    });
  });

  it('keeps the AI recommendation highlighted after another target is selected', () => {
    const aiRecommendationId = 'target-ai';

    expect(isPersistentRadarAiHighlight('target-ai', aiRecommendationId)).toBe(true);
    expect(isPersistentRadarAiHighlight('target-human', aiRecommendationId)).toBe(false);
    expect(resolveRadarTargetMarkerStyle('#00ff00', false, true)).toMatchObject({
      stroke: '#69d8ff',
      strokeWidth: 3,
      shadowColor: '#69d8ff',
      shadowBlur: 14,
    });
  });
});
