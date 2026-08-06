import { describe, expect, it } from 'vitest';
import { canShowFormalQuestionnaire } from './questionnairePolicy';

describe('questionnaire eligibility by control mode', () => {
  it.each(['0', '1', '2'])('shows the questionnaire for formal control mode %s', controlMode => {
    expect(canShowFormalQuestionnaire({
      enabled: true,
      isPractice: false,
      controlMode,
    })).toBe(true);
  });

  it('does not show the questionnaire for practice tasks', () => {
    expect(canShowFormalQuestionnaire({
      enabled: true,
      isPractice: true,
      controlMode: '0',
    })).toBe(false);
  });

  it('honors the questionnaire popup switch', () => {
    expect(canShowFormalQuestionnaire({
      enabled: false,
      isPractice: false,
      controlMode: '1',
    })).toBe(false);
  });
});
