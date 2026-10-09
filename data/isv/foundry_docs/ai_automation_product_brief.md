---
title: AI Automation Product Brief and Qualification Guide
doc_type: product_brief
account_id: ACC-1001
renewal_id: REN-1001
synthetic: true
---

# AI Automation Product Brief and Qualification Guide

Owner: Product Management. For account teams and solution architects. This is a synthetic demo
document, written for illustration only.

## 1. What AI Automation is

AI Automation is designed for high-volume service workflows that combine intake, classification,
knowledge retrieval, human approval, and downstream system actions. It is an add-on to Core
Platform and is sold as an annual subscription with an implementation engagement.

Typical use cases in a school district include:

- student and family service requests (enrollment, transport, records);
- staff helpdesk and onboarding requests;
- procurement and vendor intake;
- facilities and maintenance work orders.

## 2. How it works

1. **Intake:** requests arrive from forms, email, or chat.
2. **Classification:** the system categorizes the request and extracts key fields.
3. **Knowledge retrieval:** it retrieves relevant policy and prior case information.
4. **Human approval:** a person approves any action that changes a record or sends a message,
   unless a workflow has been explicitly approved to run unattended.
5. **Downstream action:** the system updates the system of record and logs the action.

Every action is logged with the source request, the retrieved evidence, and the approver.

## 3. Qualification criteria

Strong candidates have:

- an executive sponsor who funds the work;
- measurable workflow volume (for example, requests per month);
- accessible integration points (APIs or supported connectors) for the systems involved;
- a defined value baseline (handle time, backlog, or cost per request).

Weak candidates have no sponsor, low volume, closed systems with no integration path, or no
baseline against which to measure benefit.

## 4. Architecture and value workshop

Before a commercial commitment, the account team must complete an architecture and value workshop.
The workshop confirms:

1. priority workflows;
2. data boundaries and where data is stored and processed;
3. integration feasibility;
4. governance, including approval steps and audit;
5. expected benefits against the baseline;
6. required specialist capacity.

A workshop is led by a solution architect and typically takes one to two days with the customer.
Outputs are a workshop summary, a feasibility rating per workflow, and a draft value case.

## 5. Specialist capacity

Implementation requires solution architect and implementation engineer capacity. Capacity is
constrained and allocated by quarter. The account team must confirm capacity before signing a
delivery date. Where capacity is constrained, the workshop should still be scheduled, and the
proposal should state the dependency.

## 6. Sizing and pricing guidance

| Scope | Indicative annual recurring revenue (USD) |
| --- | --- |
| Single workflow pilot | 100,000 to 200,000 |
| Multi-workflow rollout | 250,000 to 450,000 |
| Enterprise rollout | 450,000 and above |

Figures are indicative planning ranges and not quotes. Final pricing follows the Strategic Renewal
Pricing and Approval Policy and requires the approvals in the Renewal Approval Matrix.

## 7. Product fit and customer trust

Product fit does not override unresolved customer trust or support concerns. If a customer has an
open P1 incident, a blocked adoption milestone, or a missed commitment, the account team should
resolve or substantially mitigate those concerns, or have an agreed recovery plan, before pushing a
commercial commitment for AI Automation. A customer may still fund discovery or the workshop in
parallel.

## 8. Governance and responsible use

- A person approves any action that changes a student, staff, or financial record.
- Personal data is minimized; student data is processed only within the customer's tenant.
- Every automated action is auditable.
- Customers can disable or roll back a workflow at any time.

## 9. Expansion forecasting

AI Automation expansion is forecast separately from the renewal. Do not add expected expansion
revenue to a renewal forecast to offset renewal risk. Expansion confidence depends on a sponsor,
a completed architecture review, and confirmed specialist capacity.

## 10. Frequently asked questions

**Does it replace staff?** No. It reduces repetitive intake and classification work and routes
decisions to people.

**Can it send messages automatically?** Only for workflows the customer has explicitly approved to
run unattended. The default is human approval.

**What does a pilot require?** A sponsor, one workflow with measurable volume, and an integration
point.
