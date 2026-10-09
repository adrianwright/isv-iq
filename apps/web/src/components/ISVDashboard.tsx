import { AlertTriangle, Building2, CalendarClock, CircleDollarSign, Lightbulb, TrendingDown } from 'lucide-react'
import { sourceClass, sourceLabels } from '../sourceMeta'
import type { BusinessSignal, Evidence, ISVAskResult, TraceStep } from '../types'
import { AssessmentSteps } from './AssessmentSteps'
import { BottomLineCard } from './BottomLineCard'
import { NextActionCard } from './NextActionCard'
import { evidenceHref, sourceTypeLabel } from './evidencePresentation'

function money(value: number, currency: string): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(value)
}

function signalClass(signal: BusinessSignal): string {
  return `isv-signal signal-${signal.status}`
}

function decisionLabel(intent: string): string {
  switch (intent) {
    case 'proposal_readiness':
      return 'Proposal readiness'
    case 'expansion_gate':
      return 'Expansion investment gate'
    case 'expansion_acceleration':
      return 'Expansion acceleration decision'
    case 'recovery_exit':
      return 'Recovery exit decision'
    default:
      return 'Renewal forecast decision'
  }
}

function refsForEvidence(result: ISVAskResult, item: Evidence): string {
  const signal = result.signals.find((candidate) => candidate.evidenceRefs.includes(item.refId))
  const risk = result.risks.find((candidate) => candidate.evidenceRefs.includes(item.refId))
  return signal?.title ?? risk?.title ?? 'Supporting business context'
}

export function ISVDashboard({ result, trace }: { result: ISVAskResult; trace: TraceStep[] }) {
  return (
    <>
      <section className="card isv-hero-card">
        <div>
          <span className="eyebrow">Strategic account</span>
          <h2>{result.account.name}</h2>
          <p className="muted">
            {result.account.segment} · {result.account.industry} · {result.account.region}
          </p>
        </div>
        <div className="isv-hero-metrics">
          <div>
            <span>Current ARR</span>
            <strong>{money(result.renewal.currentArr, result.renewal.currency)}</strong>
          </div>
          <div>
            <span>Renews in</span>
            <strong>{result.renewal.daysToRenewal} days</strong>
          </div>
          <div>
            <span>Outlook</span>
            <strong className="text-amber">{result.assessment.status.replace('_', ' ')}</strong>
          </div>
        </div>
      </section>

      <div className="assessment-zone">
        <div className="assessment-main">
          <section className="card" id="assessment">
            <div className="card-header">
              <span className="eyebrow">{decisionLabel(result.intent)}</span>
              <span className="mode-pill mock">{result.assessment.confidence} confidence</span>
            </div>
            <h2>{result.assessment.label}</h2>
            <p className="isv-answer">{result.answer}</p>
            <div className="isv-risk-grid">
              {result.risks.map((risk) => (
                <article key={risk.id} className={`isv-risk risk-${risk.severity}`}>
                  <AlertTriangle size={16} aria-hidden="true" />
                  <div>
                    <strong>{risk.title}</strong>
                    <p>{risk.impact}</p>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="card" id="account">
            <div className="card-header">
              <span className="eyebrow">Account and renewal</span>
              <span className="muted">{result.renewal.id}</span>
            </div>
            <div className="isv-summary-grid">
              <div><Building2 size={16} /><span>Primary contact</span><strong>{result.account.primaryContact}</strong></div>
              <div><CircleDollarSign size={16} /><span>Forecast ARR</span><strong>{money(result.renewal.forecastArr, result.renewal.currency)}</strong></div>
              <div><CalendarClock size={16} /><span>Renewal date</span><strong>{result.renewal.renewalDate}</strong></div>
              <div><TrendingDown size={16} /><span>Account health</span><strong>{result.account.health.replace('_', ' ')}</strong></div>
            </div>
          </section>

          <section className="card">
            <div className="card-header">
              <span className="eyebrow">Business signals</span>
              <span className="muted">{result.signals.length} assessed</span>
            </div>
            <div className="isv-signal-list">
              {result.signals.map((signal) => (
                <article key={signal.id} className={signalClass(signal)}>
                  <div className="isv-signal-head">
                    <span>{signal.category}</span>
                    <strong>{signal.title}</strong>
                    <em>{signal.status}</em>
                  </div>
                  <p>{signal.impact}</p>
                  {signal.remediation ? <small>Next: {signal.remediation}</small> : null}
                </article>
              ))}
            </div>
          </section>

          <section className="card" id="specialists">
            <div className="card-header">
              <span className="eyebrow">Specialist team</span>
              <span className="muted">{(result.specialists ?? []).length} grounded assessments</span>
            </div>
            <div className="specialist-grid">
              {(result.specialists ?? []).map((specialist) => (
                <article className={`specialist-card signal-${specialist.status}`} key={specialist.id}>
                  <div className="specialist-head">
                    <span>{specialist.label}</span>
                    <em>{specialist.status}</em>
                  </div>
                  <p>{specialist.summary}</p>
                  <strong>Recommendation</strong>
                  <p>{specialist.recommendation}</p>
                  {specialist.investigationLead ? (
                    <small>Investigate: {specialist.investigationLead}</small>
                  ) : null}
                </article>
              ))}
            </div>
          </section>

          {result.opportunities.length > 0 ? (
            <section className="card">
              <div className="card-header">
                <span className="eyebrow">Expansion opportunity</span>
                <span className="muted">{result.opportunities[0]?.confidence} confidence</span>
              </div>
              {result.opportunities.map((opportunity) => (
                <article key={opportunity.id} className="isv-opportunity">
                  <Lightbulb size={20} aria-hidden="true" />
                  <div>
                    <h3>{opportunity.product} · {money(opportunity.estimatedArr, opportunity.currency)}</h3>
                    <p>{opportunity.rationale}</p>
                    <p className="muted">Blockers: {opportunity.blockers.join(' · ')}</p>
                  </div>
                </article>
              ))}
            </section>
          ) : null}

          <section className="evidence-card card" id="evidence">
            <div className="card-header">
              <span className="eyebrow">Evidence packet</span>
              <span className="muted">{result.evidence.length} sources</span>
            </div>
            <div className="evidence-scroll">
              <table className="evidence-table">
                <thead><tr><th>Finding</th><th>Source</th><th>Evidence</th><th>Link</th></tr></thead>
                <tbody>
                  {result.evidence.map((item) => {
                    const href = evidenceHref(item.url)
                    return (
                      <tr key={item.refId}>
                        <td className="cell-finding">{refsForEvidence(result, item)}</td>
                        <td><span className={`source-tag ${sourceClass(item.source)}`}>{sourceLabels[item.source]}</span></td>
                        <td className="cell-evidence">
                          <span className="evidence-title">{item.title}</span>
                          <span className="evidence-source-type">{sourceTypeLabel(item.sourceType)}</span>
                        </td>
                        <td>{href ? <a href={href} target="_blank" rel="noreferrer" className="evidence-link">Open source</a> : <span className="muted">No direct link</span>}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </div>

        <aside className="action-rail" id="workflow">
          <BottomLineCard text={result.bottomLine} />
          <NextActionCard action={result.nextAction} />
          <section className="rail-card">
            <div className="rail-card-head">Reviewers</div>
            <ul className="rail-reviewers">
              {result.reviewers.map((reviewer) => (
                <li key={reviewer.owner.id}>
                  <div className="rail-reviewer-info">
                    <span className="rail-reviewer-role">{reviewer.role}</span>
                    <span className="rail-reviewer-name">{reviewer.owner.display}</span>
                  </div>
                  <span className={`rail-reviewer-state state-${reviewer.status}`}>{reviewer.status}</span>
                </li>
              ))}
            </ul>
          </section>
          <section className="rail-card">
            <div className="rail-card-head">Missing evidence</div>
            <ul className="rail-steps">
              {result.missingData.map((item) => <li key={item}><AlertTriangle size={14} /><span>{item}</span></li>)}
            </ul>
          </section>
          {result.reconciliation && (
            <section className="rail-card">
              <div className="rail-card-head">Guided reconciliation</div>
              <p className="muted">
                {result.reconciliation.sourcesUsed.length} sources weighed by claim type.
                Records win on conflict. Confidence: {result.reconciliation.confidence}.
                {result.reconciliation.narration === 'model' ? ' Narrated by a model.' : ''}
              </p>
              <ul className="rail-steps">
                {result.reconciliation.conflicts.length === 0
                  ? <li><span>No conflicts between sources and records.</span></li>
                  : result.reconciliation.conflicts.map((item) => <li key={item}><AlertTriangle size={14} /><span>{item}</span></li>)}
              </ul>
            </section>
          )}
          <AssessmentSteps trace={trace} />
          <section className="rail-card safety-notice">
            <div className="rail-card-head">Demo boundary</div>
            <p className="muted">{result.disclaimer} Human review is required.</p>
          </section>
        </aside>
      </div>
    </>
  )
}
