/** Stable internal identities; public display names never choose capabilities. */
export const assistantIds={general:'assistant_1',forms:'assistant_2'} as const;
export type AssistantId=typeof assistantIds[keyof typeof assistantIds];
