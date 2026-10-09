# Synthetic ISV data

All records in `data/isv/` are fictional and were created for this demonstration. They are not
copied from customer systems, Microsoft 365 tenants, production telemetry, contracts, or licensed
content.

## Contents

- `registry.yaml`: canonical detailed Alder Creek Unified School District and Fabrikam scenarios.
- `ontology.yaml`: Fabric entity and relationship contract.
- `fabric/`: 15 deterministic Lakehouse-ready CSV tables and manifest.
- `foundry_docs/`: synthetic contract, policy, product, pricing, and recovery guidance.
- `work/`: synthetic customer meetings, internal plan, and commitments.
- `portfolio.yaml`: five-account renewal and expansion triage.
- `specialists.yaml`: grounded specialist role contract.
- `prompts.yaml`: demonstration prompt catalog.

Regenerate the Fabric package:

```powershell
.\.venv\Scripts\python data\isv\generate_fabric.py
```

Validate the full package:

```powershell
.\.venv\Scripts\python tools\validate_isv_consistency.py
```
