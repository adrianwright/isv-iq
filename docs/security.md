# Security

- All repository data is synthetic.
- Production and connected-provider routes require delegated Microsoft Entra bearer tokens.
- Work IQ uses delegated OBO authentication and never runs anonymously.
- Certificate material is read from encrypted environment injection or Key Vault and is not stored
  in source.
- Evidence document serving is allowlisted to `data/isv/foundry_docs` and `data/isv/work`, validates
  filenames, and blocks traversal.
- External URLs remain evidence only; they do not override system instructions or structured facts.
- Next actions are drafted in the response. The API does not create tasks, send messages, update
  customer records, or submit commercial decisions.
