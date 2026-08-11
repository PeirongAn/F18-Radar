export interface QuestionnaireQuestion {
  id: number;
  text: string;
  type?: 'scale' | 'number';
  options?: string[];
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
  placeholder?: string;
}

export interface ManualQuestionnaireConfig {
  taskTypes?: string[];
  questionIds: number[];
  additionalQuestions?: QuestionnaireQuestion[];
}

export const resolveQuestionnaireQuestions = (
  questions: QuestionnaireQuestion[],
  manualQuestionnaire: ManualQuestionnaireConfig | undefined,
  controlMode: string | undefined,
  taskType?: string,
): QuestionnaireQuestion[] => {
  if (String(controlMode ?? '').trim() !== '0' || !manualQuestionnaire) {
    return questions;
  }
  if (
    manualQuestionnaire.taskTypes?.length
    && (!taskType || !manualQuestionnaire.taskTypes.includes(taskType))
  ) {
    return questions;
  }

  const includedIds = new Set(manualQuestionnaire.questionIds);
  return [
    ...questions.filter(question => includedIds.has(question.id)),
    ...(manualQuestionnaire.additionalQuestions ?? []),
  ];
};

export const isQuestionnaireAnswerValid = (
  question: QuestionnaireQuestion,
  answer: number | undefined,
): boolean => {
  if (answer === undefined || !Number.isFinite(answer)) return false;
  if (question.type !== 'number') return true;
  if (question.min !== undefined && answer < question.min) return false;
  if (question.max !== undefined && answer > question.max) return false;
  return true;
};
