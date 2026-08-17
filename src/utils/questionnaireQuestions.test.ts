import { describe, expect, it } from 'vitest';
import {
  isQuestionnaireAnswerValid,
  resolveQuestionnaireQuestions,
  type ManualQuestionnaireConfig,
  type QuestionnaireQuestion,
} from './questionnaireQuestions';

const questions: QuestionnaireQuestion[] = [
  ...[1, 2, 3, 4, 5, 6].map(id => ({
    id,
    text: `Question ${id}`,
  })),
  {
    id: 8,
    text: 'System accuracy',
    type: 'number',
    min: 0,
    max: 100,
  },
];

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
    ['RADAR_TARGETING', '1'],
    ['RADAR_TARGETING', '2'],
    ['SA_THREAT_RESPONSE', '1'],
    ['SA_THREAT_RESPONSE', '2'],
    ['PLATFORM_CONTROL', '1'],
    ['PLATFORM_CONTROL', '2'],
    ['WEAPON_FIRING', '1'],
    ['WEAPON_FIRING', '2'],
  ])('adds the system accuracy question for %s mode %s', (taskType, controlMode) => {
    expect(resolveQuestionnaireQuestions(questions, manualQuestionnaire, controlMode, taskType).map(q => q.id))
      .toEqual([1, 2, 3, 4, 5, 6, 8]);
  });

  it('keeps the system accuracy question out of manual mode', () => {
    expect(resolveQuestionnaireQuestions(questions, manualQuestionnaire, '0', 'RADAR_TARGETING').map(q => q.id))
      .toEqual([4, 5, 6, 7]);
  });

  it('does not apply the manual questionnaire to an unlisted task type', () => {
    expect(resolveQuestionnaireQuestions(questions, manualQuestionnaire, '0', 'UNKNOWN_TASK').map(q => q.id))
      .toEqual([1, 2, 3, 4, 5, 6, 8]);
  });

  it('validates the manual accuracy as a percentage', () => {
    const accuracyQuestion = manualQuestionnaire.additionalQuestions![0];
    expect(isQuestionnaireAnswerValid(accuracyQuestion, 0)).toBe(true);
    expect(isQuestionnaireAnswerValid(accuracyQuestion, 100)).toBe(true);
    expect(isQuestionnaireAnswerValid(accuracyQuestion, -1)).toBe(false);
    expect(isQuestionnaireAnswerValid(accuracyQuestion, 101)).toBe(false);
    expect(isQuestionnaireAnswerValid(accuracyQuestion, undefined)).toBe(false);
  });

  it('validates the system accuracy as a percentage', () => {
    const accuracyQuestion = questions.find(question => question.id === 8)!;
    expect(isQuestionnaireAnswerValid(accuracyQuestion, 0)).toBe(true);
    expect(isQuestionnaireAnswerValid(accuracyQuestion, 100)).toBe(true);
    expect(isQuestionnaireAnswerValid(accuracyQuestion, -1)).toBe(false);
    expect(isQuestionnaireAnswerValid(accuracyQuestion, 101)).toBe(false);
  });
});
