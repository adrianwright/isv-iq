# ISV Customer Intelligence Scenario

This package defines the repository's Customer Renewal and Expansion Intelligence scenario.

All accounts, people, contracts, support records, financial records, communications, and external
signals are fictional. **Synthetic demo data only. Not a production forecast or system of record.**

## Hero scenario

Alder Creek Unified School District is a strategic education customer with a USD 2.4M renewal due
in 75 days. The account has declining Analytics adoption, two unresolved P1 cases, one SLA breach,
a new CIO, a proposal ready for controlled release, and a possible AI Automation expansion.

The scenario is intentionally mixed:

- meaningful renewal risk is supported by structured and unstructured evidence;
- the district's proposal is ready even though full-value forecast evidence remains incomplete;
- the expansion opportunity is credible but requires technical validation;
- Fabrikam Unified School District provides a separate evidence-supported positive expansion decision;
- the final recommendation requires human review.

## Files

| File | Purpose |
|---|---|
| `registry.yaml` | Canonical synthetic entities and relationships |
| `ontology.yaml` | Target Fabric IQ entity and relationship contract |
| `prompts.yaml` | Categorized demo prompt catalog and expected IQ participation |
| `fabric/*.csv` | Generated Lakehouse-ready tables for the ISV Fabric workspace |
| `foundry_docs/*.md` | Synthetic contract, policy, product, and renewal knowledge for Foundry IQ |
| `work/*` | Synthetic QBR, customer follow-up, internal plan, and commitments for Work IQ |
| `portfolio.yaml` | Synthetic cross-account renewal and expansion triage |
| `specialists.yaml` | Grounded ISV specialist-role contract |

Regenerate the Fabric tables from the canonical registry with:

```powershell
.\.venv\Scripts\python data\isv\generate_fabric.py
```

Validate this package with:

```powershell
.\.venv\Scripts\python tools\validate_isv_consistency.py
```
