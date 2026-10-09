# Microsoft IQ for ISVs API

FastAPI backend for customer renewal and expansion intelligence.

```powershell
$env:APP_ENVIRONMENT = "development"
$env:USE_LIVE_ISV_FABRIC = "false"
$env:USE_LIVE_ISV_FOUNDRY = "false"
$env:USE_LIVE_ISV_WEB = "false"
$env:USE_LIVE_ISV_WORK = "false"

Push-Location services\api
..\..\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
Pop-Location
```

Primary endpoints:

- `GET /api/isv/portfolio`
- `POST /api/isv/ask`
- `POST /api/isv/ask/stream`

Run tests from this directory with `..\..\.venv\Scripts\python -m pytest`.
