---
title: Premium Support Incident Recovery and Service Credit Policy
doc_type: support_policy
account_id: ACC-1001
synthetic: true
---

# Premium Support Incident Recovery and Service Credit Policy

Owner: Support Operations. Applies to all Premium Support customers. This is a synthetic demo
document, written for illustration only.

## 1. Purpose

This policy defines how the service team recovers from a priority-one (P1) incident, how it
communicates recovery to the customer, and how it decides whether a service credit or commercial
concession is appropriate. It exists so that customers receive a consistent, honest recovery
experience and so that commercial concessions are never made informally.

## 2. Severity definitions

| Severity | Definition | Initial response target |
| --- | --- | --- |
| P1 | Production service is unavailable or a core workflow is materially impaired for many users, with no acceptable workaround. | 30 minutes, 24x7 |
| P2 | Production service is degraded or a workflow is impaired for some users, and a workaround exists. | 4 business hours |
| P3 | Minor defect, question, or request with no material business impact. | 1 business day |

A P1 is declared by the support escalation manager or the on-call incident commander. A customer may
request a P1 declaration; the incident commander confirms against the definition above.

## 3. Obligations during a P1 incident

For every P1 incident, the service team must:

1. Assign an accountable incident owner and name them to the customer.
2. Document customer impact in plain language, including which users and workflows are affected.
3. Provide a recovery timeline and update it at least once every business day until closure.
4. Record whether an uptime or response commitment was missed, using system timestamps.
5. Issue a closure summary within five business days of closing the incident.

An incident is not considered closed until the customer has confirmed the workaround or fix, or
fourteen days have passed without objection after the closure summary.

## 4. Incident states

- **Investigating:** the cause is not yet known.
- **Mitigation provided:** a workaround or temporary fix is in place, but the underlying defect
  remains. A mitigated incident is still open for renewal-risk purposes.
- **Engineering investigation:** the defect is confirmed and is being fixed. The customer must
  have a committed remediation date or an explicit statement that no date can yet be given.
- **Resolved:** the fix is deployed and confirmed.
- **Closed:** the closure summary has been issued.

## 5. Customer-facing recovery packages

A recovery package must distinguish four categories, and must not blur them:

1. Confirmed root cause.
2. Temporary mitigation currently in place.
3. Committed remediation, with an owner and a date.
4. Items still under engineering investigation.

The package must not describe an item as resolved while it is mitigated or under investigation. It
must not promise a fix date that engineering has not committed to.

## 6. Service credits

If an uptime or response commitment was missed, the support escalation manager prepares a
service-credit recommendation supported by incident records.

### 6.1 Eligibility

A credit may be considered when all of the following are true:

- the contract states the customer is service-credit eligible;
- the breach is substantiated by incident system timestamps;
- the cause was within the Provider's control.

### 6.2 Approval

A service-credit recommendation requires validation by Support Operations, Finance, and the account
owner before it is presented to the customer. The account executive and the support leader must
approve any commercial concession, including a credit, a discount, or contract flexibility.

### 6.3 What credits are

A service credit is applied against a future invoice. It is not a refund. Credits do not change the
contract value or the recorded ARR.

## 7. Rules for automated assistants

No automated assistant may promise a credit, a resolution date, or a contractual remedy. An
assistant may summarize policy, cite the incident record, and draft a recommendation for a human to
review. All drafts must be labeled as drafts.

## 8. Relationship to renewals

An open P1 incident is a material renewal risk. A missed commitment on an open P1 incident is
treated as a higher risk because it affects customer trust independently of the technical fix.
The account team must be informed of every P1 incident on a renewing account within one business
day, and the recovery summary must be available to the renewal proposal team before a proposal is
released.

## 9. Worked example

A customer reports intermittent analytics refresh failures that affect executive dashboards. The
incident is declared P1. Engineering confirms a defect and the incident moves to engineering
investigation. The 99.9% uptime objective was missed for the affected month.

- The incident owner documents impact and posts a daily update.
- The escalation manager prepares a service-credit recommendation citing the incident timestamps.
- Support Operations, Finance, and the account owner validate it. The account executive and support
  leader approve any concession.
- The recovery package states the confirmed root cause (if known), the mitigation, the committed
  remediation date, and what is still under investigation.
- No one tells the customer that a credit is approved until the approval chain is complete.

## 10. Records

Incident records, recovery summaries, and credit decisions are retained for seven years in the
Provider's incident and finance systems.
