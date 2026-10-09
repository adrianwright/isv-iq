# Data model

The detailed synthetic scenario contains 15 entity collections:

accounts, contacts, employees, account team, renewals, contracts, subscriptions, product usage,
support cases, invoices, success milestones, commitments, expansion candidates, interactions, and
external signals.

`data/isv/registry.yaml` is canonical. `data/isv/generate_fabric.py` exports deterministic CSVs and
`manifest.json`. `data/isv/ontology.yaml` defines the generation-2 Direct Lake entity and
relationship model.

The portfolio contract is intentionally separate. `data/isv/portfolio.yaml` contains summary-level
triage records for five accounts, while Alder Creek Unified School District is the complete hero
account and Fabrikam Unified School District provides a complete positive expansion contrast.
All five portfolio accounts are school districts in the Education industry.
