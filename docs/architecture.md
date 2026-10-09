# Architecture

Microsoft IQ for ISVs is a read-oriented intelligence layer for customer renewal and expansion
decisions. The backend fans a question out to four independently gated providers, preserves their
citations, and composes a deterministic business assessment.

## Runtime flow

1. The UI loads `GET /api/isv/portfolio` for cross-account triage.
2. A user submits an account question through REST or Server-Sent Events.
3. The orchestrator resolves the account and renewal from the canonical registry.
4. Foundry, Fabric, Work, and Web IQ adapters run in parallel.
5. The orchestrator constructs signals, risks, expansion opportunities, missing data, and actions.
6. Five grounded specialists analyze the same assembled evidence without repeating provider calls.
7. The response keeps recommendations drafted and assigns human reviewers.

## Provider boundaries

| Provider | Structured responsibility | Minimum connected grounding |
|---|---|---|
| Fabric IQ | Account, ARR, renewal, usage, support, invoices, commitments, opportunities | Non-empty Data Agent response |
| Foundry IQ | Private policies, contracts, product and recovery guidance | Three document references |
| Work IQ | Customer-facing and internal workplace evidence | Two M365 attributions |
| Web IQ | Public leadership, strategy, and competitive context | Two public references |

Provider failures surface explicitly. Connected adapters do not manufacture citation-shaped
fallbacks.

## Specialist boundary

The Commercial, Adoption, Support Recovery, Relationship, and Expansion specialists consume the
already-grounded business signals. They return structured findings and investigation leads but do
not call external providers independently.
