import { BrainCircuit, Database, Globe, Users, type LucideIcon } from 'lucide-react'
import type { IQSource, SourceStatus } from './types'

export const sourceLabels: Record<IQSource, string> = {
  foundry: 'Foundry IQ',
  fabric: 'Fabric IQ',
  work: 'Work IQ',
  web: 'Web IQ',
}

export const sourceIcon: Record<IQSource, LucideIcon> = {
  foundry: BrainCircuit,
  fabric: Database,
  work: Users,
  web: Globe,
}

export const sourceOrder: IQSource[] = ['foundry', 'fabric', 'work', 'web']

export const sourceTagline: Record<IQSource, string> = {
  foundry: 'Business knowledge',
  fabric: 'Operational account data',
  work: 'Customer and team activity',
  web: 'External market context',
}

export const sourceRetrieving: Record<IQSource, string> = {
  foundry: 'Contract terms, support policy, pricing guidance, product roadmap',
  fabric: 'Renewal, adoption, support, invoices, account ownership',
  work: 'Customer sentiment, meetings, commitments, account-team decisions',
  web: 'Leadership changes, company strategy, market and competitor signals',
}

export function sourceClass(source: IQSource): string {
  return `source-${source}`
}

export const statusLabels: Record<SourceStatus, string> = {
  idle: 'Idle',
  queued: 'Queued',
  searching: 'Searching',
  retrieved: 'Retrieved',
  needs_review: 'Needs review',
  complete: 'Complete',
  failed: 'Failed',
}

export function statusLabel(status: SourceStatus): string {
  return statusLabels[status] ?? status
}
