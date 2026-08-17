export const canShowFormalQuestionnaire = (input: {
  enabled: boolean;
  isPractice: boolean | undefined;
  controlMode?: string;
}): boolean => input.enabled && input.isPractice === false;
