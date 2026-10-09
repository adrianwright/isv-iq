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
  'Prepare',
  'Expand',
  'Act',
] as const

export type QuestionCategory = (typeof questionCategories)[number]

export const questionLibrary: QuestionExample[] = [
  {
    category: 'Understand',
    short: 'Should we increase the renewal forecast?',
    accountId: 'ACC-1001',
    renewalId: 'REN-1001',
    prompt:
      'Should we increase the Contoso Unified School District renewal forecast from $2.2M to the full $2.4M ARR? Return a Yes, No, or Not yet verdict with confidence, criteria met, criteria not met, contradictory evidence, missing evidence, and the next forecast action.',
  },
  {
    category: 'Prepare',
    short: 'Are we ready to send the proposal?',
    accountId: 'ACC-1001',
    renewalId: 'REN-1001',
    prompt:
      'Are we ready to send Contoso Unified School District the three-year price-protected renewal proposal by October 13? Return a Yes, No, or Not yet verdict based on pricing approval, payment status, support recovery, customer requirements, and open commitments; identify every remaining condition and its owner.',
  },
  {
    category: 'Expand',
    short: 'Should we fund the architecture workshop?',
    accountId: 'ACC-1001',
    renewalId: 'REN-1001',
    prompt:
      'Should we advance the $450K Contoso Unified School District AI Automation opportunity to a funded architecture workshop now? Return a Yes, No, or Not yet verdict based on district demand, sponsor strength, product fit, technical prerequisites, architect capacity, support trust, and measurable expansion value.',
  },
  {
    category: 'Act',
    short: 'Should we accelerate Fabrikam expansion?',
    accountId: 'ACC-1002',
    renewalId: 'REN-1002',
    prompt:
      'Should we accelerate the $300K Fabrikam Unified School District AI Automation expansion now? Return a Yes, No, or Not yet verdict based on executive sponsorship, adoption strength, customer demand, architecture and security readiness, specialist capacity, support health, payment status, and measurable value criteria.',
  },
]

export const defaultQuestion = questionLibrary[0].prompt
export const defaultQuestionExample = questionLibrary[0]
