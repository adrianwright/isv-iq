# Configuration

Local development uses `scripts/dev.ps1`, which sets `APP_ENVIRONMENT=development`, disables all
connected providers, and clears frontend Entra settings.

## Provider flags

- `USE_LIVE_ISV_FABRIC`
- `USE_LIVE_ISV_FOUNDRY`
- `USE_LIVE_ISV_WEB`
- `USE_LIVE_ISV_WORK`

Each flag controls only its matching ISV adapter. See `services/api/.env.example` for coordinates.

## Authentication

Any production process or process with a connected provider enabled requires:

- `AZURE_TENANT_ID`
- `API_AUDIENCE`
- `API_REQUIRED_SCOPE`

Anonymous requests are permitted only in development, local, or test environments when every
connected-provider flag is off.

## Work IQ certificates

Production can receive `WORK_IQ_CLIENT_CERTIFICATE_PFX` as an encrypted application secret. When it
is absent, the runtime uses the configured managed identity and Key Vault secret. Local connected
testing uses the PEM certificate and thumbprint settings.

Work IQ requests use a bounded `WORK_IQ_TIMEOUT_SECONDS` value. The deployment sets 240 seconds for
the multi-part renewal prompts while still surfacing an explicit provider timeout when exceeded.
