# Microsoft IQ for ISVs

> **Synthetic demo data only. Human review is required.**

Microsoft IQ for ISVs demonstrates how software companies can combine four Microsoft IQ layers to
understand customer renewals, recover at-risk accounts, and identify responsible expansion motions.
The flagship scenario is **Customer Renewal and Expansion Intelligence** for the synthetic
Contoso Unified School District account, with Fabrikam Unified School District as a positive expansion
contrast in a five-school-district renewal portfolio.

![Why this matters: one renewal question, at least four sources](docs/images/isv-why-it-matters.png?v=4)

An [interactive version](docs/isv-why-it-matters.html) lists the specific data in each place.

The application combines:

- **Fabric IQ** for account, subscription, usage, support, invoice, renewal, and opportunity facts.
- **Foundry IQ** for contracts, support policies, pricing guidance, product briefs, and recovery
  playbooks.
- **Work IQ** for customer meetings, account-team plans, commitments, and workplace context.
- **Web IQ** for current public company, leadership, strategy, and competitive evidence.

It returns an evidence-backed assessment, structured risks, missing information, recommendations,
specialist findings, and a drafted next action for human review. No customer system or Microsoft 365
action is submitted automatically.

## Experience

The React application provides:

- a portfolio view with total ARR, forecast ARR, at-risk ARR, and expansion pipeline;
- prioritized renewal motions across five synthetic accounts;
- a detailed four-IQ assessment for Contoso Unified School District;
- commercial, adoption, support, relationship, and expansion specialists;
- REST and Server-Sent Events retrieval with source activity and evidence links;
- explicit missing-data, reviewer, and human-approval boundaries.

## Architecture

```text
React/Vite UI
    |
    +-- GET  /api/isv/portfolio
    +-- POST /api/isv/ask
    `-- POST /api/isv/ask/stream
                 |
                 v
         FastAPI orchestrator
          /      |      |      \
   Foundry IQ Fabric IQ Work IQ Web IQ
          \      |      |      /
        grounded ISV specialists
                 |
          human-reviewed result
```

Local mode is deterministic and reads only `data/isv/`. Connected providers are independently
gated and fail explicitly when required grounding is unavailable.

### Guided reconciliation

Sources are weighed by claim type using an authority map in `services/api/app/isv_reconcile.py`
(numbers: Fabric IQ first; rules: Foundry IQ; commitments: Work IQ; external: Web IQ). A Critic
applies the rules: records win on conflict, the worst status wins, and conflicts are logged.
Confidence is computed from conflicts and unavailable sources. Optional model narration
(`USE_LIVE_ISV_NARRATION`, `ISV_OPENAI_ENDPOINT`, `ISV_OPENAI_DEPLOYMENT`) rewrites the answer
over the established facts and is rejected if it changes the verdict or cites unknown evidence.

## Run locally

Prerequisites: Python 3.12+, Node.js 22+, npm, and PowerShell.

```powershell
.\scripts\dev.ps1
```

Open `http://localhost:5173`. The launcher forces every connected-provider flag off, requires no
Azure account, and does not modify Microsoft 365.

Manual validation:

```powershell
.\.venv\Scripts\python tools\validate_isv_consistency.py

Push-Location services\api
..\..\.venv\Scripts\python -m pytest
Pop-Location

npm --prefix apps\web test -- --run
npm --prefix apps\web run lint
npm --prefix apps\web run build
```

## Connected providers

Copy `services/api/.env.example` to a private environment file and supply only the providers you
intend to enable:

| Flag | Required coordinates |
|---|---|
| `USE_LIVE_ISV_FABRIC` | ISV Fabric workspace and Data Agent IDs |
| `USE_LIVE_ISV_FOUNDRY` | ISV Azure AI Search endpoint and Foundry knowledge-base name |
| `USE_LIVE_ISV_WEB` | Native Web IQ API key, or the isolated Search web knowledge base |
| `USE_LIVE_ISV_WORK` | Work IQ OBO app, delegated user token, and certificate configuration |

Connected mode requires Microsoft Entra bearer authentication. Work IQ remains delegated and
read-only. The included M365 seeder is optional and must be run explicitly.

## Synthetic data

`data/isv/registry.yaml` is the canonical detailed-account source. It drives:

- 15 deterministic Fabric CSV tables;
- a generation-2 Fabric ontology;
- the Contoso Unified School District and Fabrikam Unified School District assessments;
- Foundry and Work IQ evidence consistency;
- specialist and prompt contracts.

`data/isv/portfolio.yaml` adds four summary-level accounts for cross-account triage. All names,
records, amounts, URLs, and workplace artifacts are synthetic.

## Provisioning and deployment

`agent/provisioning/isv/` contains isolated provisioning and optional M365 seeding utilities. They
do not inherit the retired demo's workspace identifiers. Azure application deployment templates
remain under `infra/`.

Phase 8 will deploy the ISV application and provider resources into a new resource group. The
existing deployed environment is intentionally untouched.

## Documentation

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/configuration.md`](docs/configuration.md)
- [`docs/data-model.md`](docs/data-model.md)
- [`docs/security.md`](docs/security.md)
- [`docs/deployment.md`](docs/deployment.md)
- [`docs/phase-7.md`](docs/phase-7.md)

## License

Licensed under the [MIT License](LICENSE).
