import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { ISVAskResult } from '../types'
import { ISVDashboard } from './ISVDashboard'

const result: ISVAskResult = {
  schemaVersion: 'isv.v1',
  question: 'Give me an executive renewal brief for Alder Creek Unified School District.',
  answer: 'Alder Creek Unified School District is at risk but recoverable.',
  answerRefs: ['r1'],
  intent: 'renewal_assessment',
  scope: 'Renewal risk and next actions.',
  bottomLine: 'Restore support confidence before positioning expansion.',
  account: {
    id: 'ACC-1001',
    name: 'Alder Creek Unified School District',
    industry: 'Education',
    segment: 'Strategic',
    region: 'North America',
    health: 'at_risk',
    annualRecurringRevenue: 2400000,
    currency: 'USD',
    primaryContact: 'Maya Chen',
    executiveSponsor: 'Alex Johnson',
  },
  renewal: {
    id: 'REN-1001',
    renewalDate: '2026-12-20',
    daysToRenewal: 75,
    currentArr: 2400000,
    forecastArr: 2200000,
    currency: 'USD',
    stage: 'evaluation',
    requestedTermMonths: 36,
  },
  assessment: {
    status: 'at_risk',
    label: 'Renewal at risk; recovery path is actionable',
    confidence: 'high',
  },
  signals: [{
    id: 'SIG-SUPPORT',
    category: 'support',
    title: 'Support confidence is impaired',
    status: 'negative',
    impact: 'Two P1 cases remain open.',
    evidenceRefs: ['r1'],
    remediation: 'Deliver the recovery package.',
  }],
  risks: [{
    id: 'RISK-SUPPORT',
    title: 'Unresolved support recovery',
    severity: 'critical',
    impact: 'A missed commitment could delay signature.',
    evidenceRefs: ['r1'],
  }],
  opportunities: [{
    id: 'EXP-1001',
    product: 'AI Automation',
    estimatedArr: 450000,
    currency: 'USD',
    fit: 'strong',
    confidence: 'medium',
    rationale: 'Customer strategy aligns.',
    blockers: ['Solution architect capacity'],
    evidenceRefs: ['r1'],
  }],
  specialists: [{
    id: 'support',
    label: 'Support Recovery Lead',
    domain: 'Priority incidents and customer recovery',
    status: 'negative',
    summary: 'Support confidence remains impaired.',
    recommendation: 'Deliver the incident recovery package first.',
    evidenceRefs: ['r1'],
    investigationLead: 'Confirm customer acceptance criteria.',
  }],
  evidence: [{
    refId: 'r1',
    source: 'fabric',
    title: 'Account and renewal record',
    snippet: 'USD 2.4M ARR and at-risk forecast.',
    url: null,
    sourceType: 'crm_record',
  }],
  missingData: ['Customer acceptance of the recovery plan'],
  nextAction: {
    text: 'Run the recovery plan.',
    steps: ['Deliver the support package.'],
    owner: { id: 'EMP-1001', display: 'Jordan Lee', role: 'Account Executive' },
    taskType: 'renewal_recovery',
    taskId: '',
    taskStatus: 'Drafted (not submitted)',
    due: '2026-10-13',
  },
  humanReview: {
    owner: { id: 'EMP-1004', display: 'Alex Johnson', role: 'Executive Sponsor' },
    reason: 'Approve the recovery posture.',
  },
  reviewers: [{
    role: 'Commercial owner',
    owner: { id: 'EMP-1001', display: 'Jordan Lee', role: 'Account Executive' },
    status: 'assigned',
  }],
  unavailableSources: [],
  sourceMap: [],
  trace: [],
  agentDriven: false,
  mode: 'mock',
  disclaimer: 'Synthetic demo data only.',
}

describe('ISVDashboard', () => {
  it('renders renewal risk, expansion, evidence, and human action', () => {
    const markup = renderToStaticMarkup(<ISVDashboard result={result} trace={[]} />)

    expect(markup).toContain('Alder Creek Unified School District')
    expect(markup).toContain('$2,400,000')
    expect(markup).toContain('Support confidence is impaired')
    expect(markup).toContain('AI Automation')
    expect(markup).toContain('Support Recovery Lead')
    expect(markup).toContain('Confirm customer acceptance criteria')
    expect(markup).toContain('Deliver the support package')
    expect(markup).toContain('Account and renewal record')
  })

  it('omits expansion content for non-expansion decisions', () => {
    const forecastResult: ISVAskResult = {
      ...result,
      intent: 'renewal_forecast',
      opportunities: [],
    }
    const markup = renderToStaticMarkup(<ISVDashboard result={forecastResult} trace={[]} />)

    expect(markup).toContain('Renewal forecast decision')
    expect(markup).not.toContain('Expansion opportunity')
    expect(markup).not.toContain('AI Automation')
  })
})
