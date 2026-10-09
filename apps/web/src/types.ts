export type IQSource = 'foundry' | 'fabric' | 'work' | 'web'
export type SourceStatus =
  | 'idle'
  | 'queued'
  | 'searching'
  | 'retrieved'
  | 'needs_review'
  | 'complete'
  | 'failed'
export type Confidence = 'low' | 'medium' | 'high'
export type TraceStatus = 'completed' | 'in_progress' | 'pending' | 'queued'
export type ReviewerStatus = 'assigned' | 'pending' | 'complete'
export type RenewalStatus = 'on_track' | 'at_risk' | 'critical' | 'indeterminate'
export type SignalStatus = 'positive' | 'watch' | 'negative' | 'unknown'

export interface ISVAskRequest {
  question: string
  accountId?: string
  renewalId?: string
}

export interface Person {
  id: string
  display: string
  role: string
}

export interface Evidence {
  refId: string
  source: IQSource
  title: string
  snippet: string
  url: string | null
  sourceType: string
}

export interface NextAction {
  text: string
  steps?: string[]
  owner: Person
  taskType: string
  taskId: string
  taskStatus: string
  due: string
}

export interface HumanReview {
  owner: Person
  reason: string
}

export interface Reviewer {
  role: string
  owner: Person
  status: ReviewerStatus
}

export interface SourceMapEntry {
  source: IQSource
  label: string
  status: SourceStatus
  queries: string[]
  citations: string[]
  durationMs?: number
  summary?: string
  retrieving?: string
  evidenceCount?: number
  evidenceNoun?: string
}

export interface TraceStep {
  step: string
  source?: IQSource
  detail: string
  ts: number
  status?: TraceStatus
}

export interface AccountSnapshot {
  id: string
  name: string
  industry: string
  segment: string
  region: string
  health: string
  annualRecurringRevenue: number
  currency: string
  primaryContact: string
  executiveSponsor: string
}

export interface RenewalSummary {
  id: string
  renewalDate: string
  daysToRenewal: number
  currentArr: number
  forecastArr: number
  currency: string
  stage: string
  requestedTermMonths: number
}

export interface RenewalAssessment {
  status: RenewalStatus
  label: string
  confidence: Confidence
}

export interface BusinessSignal {
  id: string
  category: 'adoption' | 'support' | 'commercial' | 'relationship' | 'expansion'
  title: string
  status: SignalStatus
  impact: string
  evidenceRefs: string[]
  owner?: string | null
  remediation?: string | null
}

export interface BusinessRisk {
  id: string
  title: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  impact: string
  evidenceRefs: string[]
}

export interface ExpansionOpportunity {
  id: string
  product: string
  estimatedArr: number
  currency: string
  fit: 'weak' | 'moderate' | 'strong'
  confidence: Confidence
  rationale: string
  blockers: string[]
  evidenceRefs: string[]
}

export interface SpecialistInsight {
  id: 'commercial' | 'adoption' | 'support' | 'relationship' | 'expansion'
  label: string
  domain: string
  status: SignalStatus
  summary: string
  recommendation: string
  evidenceRefs: string[]
  investigationLead?: string | null
}

export interface PortfolioAccount {
  id: string
  name: string
  industry: string
  segment: string
  region: string
  renewalId: string
  renewalDate: string
  daysToRenewal: number
  currentArr: number
  forecastArr: number
  currency: string
  status: RenewalStatus
  confidence: Confidence
  expansionArr: number
  priority: number
  primaryDriver: string
  recommendedMotion: string
  hero: boolean
}

export interface ISVPortfolio {
  schemaVersion: 'isv.portfolio.v1'
  asOf: string
  totalArr: number
  forecastArr: number
  expansionPipeline: number
  atRiskArr: number
  accounts: PortfolioAccount[]
  disclaimer: string
}

export interface ISVAskResult {
  schemaVersion: 'isv.v1'
  question: string
  answer: string
  answerRefs: string[]
  intent: string
  scope: string
  bottomLine: string
  account: AccountSnapshot
  renewal: RenewalSummary
  assessment: RenewalAssessment
  signals: BusinessSignal[]
  risks: BusinessRisk[]
  opportunities: ExpansionOpportunity[]
  specialists?: SpecialistInsight[]
  evidence: Evidence[]
  missingData: string[]
  nextAction: NextAction
  humanReview: HumanReview
  reviewers: Reviewer[]
  unavailableSources: string[]
  sourceMap: SourceMapEntry[]
  trace: TraceStep[]
  agentDriven: boolean
  mode: 'mock' | 'live'
  disclaimer: string
}

export type FabricState = 'Active' | 'Paused' | 'Pausing' | 'Resuming' | 'Unknown'

export interface FabricStatus {
  state: FabricState
  capacityName: string
  portalUrl: string
  detail?: string | null
}

export interface PlanEvent {
  steps: string[]
}

export interface SourceQueryEvent {
  source: IQSource
  label: string
  query: string
  retrieving?: string
  status: 'searching'
}

export interface SourceResultEvent {
  source: IQSource
  status: SourceStatus
  summary?: string
  citations: string[]
  durationMs?: number
  retrieving?: string
  evidenceCount?: number
  evidenceNoun?: string
}

export interface AgentActivityEvent {
  phase: 'tool_start' | 'tool_done' | 'answer_delta'
  source?: IQSource
  query?: string
  text?: string
}

export interface ErrorEventPayload {
  message: string
}

export type ISVStreamEvent =
  | { type: 'plan'; data: PlanEvent }
  | { type: 'source_query'; data: SourceQueryEvent }
  | { type: 'source_result'; data: SourceResultEvent }
  | { type: 'agent_activity'; data: AgentActivityEvent }
  | { type: 'final'; data: { result: ISVAskResult } }
  | { type: 'error'; data: ErrorEventPayload }
