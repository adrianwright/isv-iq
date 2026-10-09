from __future__ import annotations

import html as _html
import re
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse

from app.auth import AuthenticatedUser, require_api_user
from app.config import get_settings
from app.fabric_status import get_fabric_status
from app.isv_orchestrator import ISVOrchestrator
from app.isv_portfolio import build_isv_portfolio
from app.isv_schemas import ISVAskRequestV1, ISVAskResultV1, ISVPortfolioV1
from app.schemas import ErrorEventPayload

settings = get_settings()
orchestrator = ISVOrchestrator(settings=settings)

_ALLOWED_DOC_DIRS = {
    "isv_foundry_docs": ("isv", "foundry_docs"),
    "isv_work": ("isv", "work"),
}
_DOC_NAME = re.compile(r"[A-Za-z0-9._-]+\.(md|json)$")

app = FastAPI(title="Microsoft IQ for ISVs API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type"],
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "mode": settings.mode}


@app.get("/api/fabric/status")
def fabric_status() -> dict[str, str | None]:
    return get_fabric_status(settings).to_dict()


@app.get("/api/evidence/doc", response_class=HTMLResponse)
def evidence_doc(path: str) -> HTMLResponse:
    parts = path.split("/")
    if len(parts) != 2 or parts[0] not in _ALLOWED_DOC_DIRS or not _DOC_NAME.fullmatch(parts[1]):
        raise HTTPException(status_code=404, detail="Document not found")
    subdir, name = parts
    base = settings.DATA_DIR.joinpath(*_ALLOWED_DOC_DIRS[subdir]).resolve()
    target = (base / name).resolve()
    if base not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="Document not found")

    body = _html.escape(target.read_text(encoding="utf-8"))
    title = _html.escape(name)
    page = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title><style>"
        "body{font:14px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;max-width:820px;"
        "margin:2rem auto;padding:0 1.25rem;color:#16213e;background:#fafafa}"
        "pre{white-space:pre-wrap;word-wrap:break-word;background:#fff;border:1px solid #e6e6ef;"
        "border-radius:8px;padding:1.25rem}"
        ".src{color:#6b7280;font-size:12px;margin-bottom:1rem;text-transform:uppercase;"
        "letter-spacing:.05em}</style></head>"
        f"<body><div class='src'>Microsoft IQ for ISVs synthetic source document &middot; {title}</div>"
        f"<pre>{body}</pre></body></html>"
    )
    return HTMLResponse(page)


@app.get("/api/isv/portfolio", response_model=ISVPortfolioV1)
def portfolio(
    user: AuthenticatedUser | None = Depends(require_api_user),
) -> ISVPortfolioV1:
    return build_isv_portfolio(settings.DATA_DIR / "isv" / "portfolio.yaml")


@app.post("/api/isv/ask", response_model=ISVAskResultV1)
def ask(
    request: ISVAskRequestV1,
    user: AuthenticatedUser | None = Depends(require_api_user),
) -> ISVAskResultV1:
    try:
        return orchestrator.answer(request, user.access_token if user else None)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/isv/ask/stream")
def ask_stream(
    request: ISVAskRequestV1,
    user: AuthenticatedUser | None = Depends(require_api_user),
) -> EventSourceResponse:
    async def generate() -> AsyncIterator[dict[str, str]]:
        try:
            async for event, data in orchestrator.stream(
                request, user.access_token if user else None
            ):
                yield {"event": event, "data": data}
        except Exception as exc:  # pragma: no cover
            yield {
                "event": "error",
                "data": ErrorEventPayload(message=str(exc)).model_dump_json(),
            }

    return EventSourceResponse(generate())
