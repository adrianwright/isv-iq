import { describe, expect, it } from 'vitest'
import { defaultQuestionExample, questionCategories, questionLibrary } from './questionLibrary'

describe('question library', () => {
  it('offers only the churn question shown in the graphic', () => {
    expect(questionCategories).toEqual(['All', 'Understand'])
    expect(questionLibrary).toHaveLength(1)
    expect(defaultQuestionExample).toBe(questionLibrary[0])
    expect(defaultQuestionExample.short).toBe('Is Contoso at risk of churn?')
    expect(defaultQuestionExample.prompt).toContain('Is Contoso at risk of churn?')
    expect(defaultQuestionExample.accountId).toBe('ACC-1001')
  })
})
