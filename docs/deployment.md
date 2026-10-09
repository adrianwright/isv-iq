# Deployment

The ISV application has not yet been deployed from this branch. Phase 8 will create isolated Azure
and Fabric resources in a new resource group rather than modifying the existing demonstration
environment.

Deployment inputs must include explicit ISV resource names and IDs. Provisioning utilities under
`agent/provisioning/isv/` have no fallback to retired workspace coordinates.

The existing Fabric capacity may be reused, but the ISV workspace, Lakehouse, ontology, Data Agent,
Search resources, application resources, and Entra configuration should remain isolated.
