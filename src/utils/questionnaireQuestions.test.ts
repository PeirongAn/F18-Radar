import { describe, expect, it } from 'vitest';
import {
  isQuestionnaireAnswerValid,
  resolveQuestionnaireQuestions,
  type ManualQuestionnaireConfig,
  type QuestionnaireQuestion,
} from './questionnaireQuestions';

const questions: QuestionnaireQuestion[] = [1, 2, 3, 4, 5, 6].map(id => ({
  id,
  text: `Question ${id}`,
}));

const manualQuestionnaire: ManualQuestionnaireConfig = {
  taskTypes: [
    'RADAR_TARGETING',
    'SA_THREAT_RESPONSE',
    'PLATFORM_CONTROL',
    'WEAPON_FIRING',
  ],
  questionIds: [4, 5, 6],
  additionalQuestions: [{
    id: 7,
    text: 'Accuracy',
    type: 'number',
    min: 0,
    max: 100,
  }],
};

describe('questionnaire questions by control mode', () => {
  it.each([
    'RADAR_TARGETING',
    'SA_THREAT_RESPONSE',
    'PLATFORM_CONTROL',
    'WEAPON_FIRING',
  ])('uses the manual questionnaire for %s', taskType => {
    expect(resolveQuestionnaireQuestions(questions, manualQuestionnaire, '0', taskType).map(q => q.id))
      .toEqual([4, 5, 6, 7]);
  });

  it.each([
    ['PLATFORM_CONTROL', '1'],
    ['PLATFORM_CONTROL', '2'],
    ['WEAPON_FIRING', '1'],
    ['WEAPON_FIRING', '2'],
  ])('keeps the original questionnaire for %s mode %s', (taskType, controlMode) => {
    expect(resolveQuestionnaireQuestions(questions, manualQuestionnaire, controlMode, taskType).map(q => q.id))
      .toEqual([1, 2, 3, 4, 5, 6]);
  });

  it('does not apply the manual questionnaire to an unlisted task type', () => {
    expect(resolveQuestionnaireQuestions(questions, manualQuestionnaire, '0', 'UNKNOWN_TASK').map(q => q.id))
      .toEqual([1, 2, 3, 4, 5, 6]);
  });

  it('validates the manual accuracy as a percentage', () => {
    const accuracyQuestion = manualQuestionnaire.additionalQuestions![0];
    expect(isQuestionnaireAnswerValid(accuracyQuestion, 0)).toBe(true);
    expect(isQuestionnaireAnswerValid(accuracyQuestion, 100)).toBe(true);
    expect(isQuestionnaireAnswerValid(accuracyQuestion, -1)).toBe(false);
    expect(isQuestionnaireAnswerValid(accuracyQuestion, 101)).toBe(false);
    expect(isQuestionnaireAnswerValid(accuracyQuestion, undefined)).toBe(false);
  });
});
