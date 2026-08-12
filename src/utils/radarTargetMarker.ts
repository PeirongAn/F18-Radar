export interface RadarTargetMarkerStyle {
  fill: string;
  stroke: string;
  strokeWidth: number;
  shadowColor: string;
  shadowBlur: number;
}

export const isPersistentRadarAiHighlight = (
  targetId: string,
  aiRecommendationId?: string,
): boolean => Boolean(aiRecommendationId) && targetId === aiRecommendationId;

/** Keep the AI marker attached to the target glyph instead of drawing a large
 * bounding box that can visually contain nearby targets. */
export const resolveRadarTargetMarkerStyle = (
  targetColor: string,
  selected: boolean,
  aiHighlighted: boolean,
): RadarTargetMarkerStyle => ({
  fill: selected ? 'white' : targetColor,
  stroke: aiHighlighted ? '#69d8ff' : targetColor,
  strokeWidth: aiHighlighted ? 3 : 1,
  shadowColor: aiHighlighted ? '#69d8ff' : selected ? 'cyan' : 'transparent',
  shadowBlur: aiHighlighted ? 14 : selected ? 10 : 0,
});
