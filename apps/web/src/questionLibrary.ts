export interface QuestionExample {
  category: string
  short: string
  prompt: string
  accountId: string
  renewalId: string
}

export const questionCategories = [
  'All',
  'Understand',
] as const

export type QuestionCategory = (typeof questionCategories)[number]

export const questionLibrary: QuestionExample[] = [
  {
    category: 'Understand',
    short: 'Is Contoso at risk of churn?',
    accountId: 'ACC-1001',
    renewalId: 'REN-1001',
    prompt:
      'Is Contoso at risk of churn? Assess Contoso Unified School District using adoption, support health, contract obligations, customer sentiment, and public signals. Return a Yes, No, or Not yet verdict with confidence, evidence, missing evidence, and a draft next action.',
  },
]

export const defaultQuestion = questionLibrary[0].prompt
export const defaultQuestionExample = questionLibrary[0]
