from __future__ import annotations

import inspect

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.isv_runtime import load_isv_registry, resolve_isv_context
from app.isv_sources import (
    ISVLiveFoundryIQ,
    ISVLiveWorkIQ,
    ISVLiveWebIQ,
    ISVMockFoundryIQ,
    ISVMockWorkIQ,
    ISVQueryContext,
)
from app.main import app
from app.workiq import WorkIQAnswer, WorkIQAttribution
from app.fabric_client import call_fabric_mcp


def _context(settings: Settings) -> ISVQueryContext:
    registry = load_isv_registry(str(settings.DATA_DIR / "isv" / "registry.yaml"))
    account, renewal = resolve_isv_context(registry, "ACC-1001", "REN-1001")
    return ISVQueryContext(
        question="Give me a renewal and expansion brief.",
        account=account,
        renewal=renewal,
        registry=registry,
    )


def test_fabric_client_sends_bearer_token() -> None:
    source = inspect.getsource(call_fabric_mcp)

    assert 'f"Bearer {token}"' in source
    assert 'f"******"' not in source


def test_mock_foundry_reads_isv_corpus_and_serves_citations() -> None:
    settings = Settings(_env_file=None, APP_ENVIRONMENT="test")
    result = ISVMockFoundryIQ(settings).query(_context(settings))

    assert {citation.refId for citation in result.citations} == {"r1", "r2", "r3"}
    assert all(citation.url for citation in result.citations)
    response = TestClient(app).get(result.citations[0].url)
    assert response.status_code == 200
    assert "Microsoft IQ for ISVs synthetic source document" in response.text
    assert "Premium Support Incident Recovery" in response.text


def test_live_foundry_uses_isolated_knowledge_base(monkeypatch) -> None:
    settings = Settings(
        _env_file=None,
        USE_LIVE_ISV_FOUNDRY=True,
        ISV_SEARCH_ENDPOINT="https://isv-search.search.windows.net",
        ISV_FOUNDRY_KB_NAME="isv-renewal-kb",
    )
    captured: dict[str, str] = {}

    def fake_retrieve(**kwargs):
        captured.update(kwargs)
        return (
            "Premium support permits service-credit review. Three-year pricing requires "
            "approval. AI Automation requires an architecture workshop.",
            [
                {"blobUrl": "https://blob/premium_support_policy.md"},
                {"blobUrl": "https://blob/strategic_renewal_pricing_policy.md"},
                {"blobUrl": "https://blob/ai_automation_product_brief.md"},
            ],
        )

    monkeypatch.setattr("app.isv_sources._retrieve_search_knowledge_base", fake_retrieve)
    result = ISVLiveFoundryIQ(settings).query(_context(settings))

    assert captured["endpoint"] == "https://isv-search.search.windows.net"
    assert captured["knowledge_base"] == "isv-renewal-kb"
    assert result.facts["foundry_live"] is True
    assert {citation.refId for citation in result.citations} == {"r1", "r2", "r3"}


def test_live_web_search_fallback_uses_isolated_knowledge_base(monkeypatch) -> None:
    settings = Settings(
        _env_file=None,
        USE_LIVE_ISV_WEB=True,
        ISV_SEARCH_ENDPOINT="https://isv-search.search.windows.net",
        ISV_WEB_KB_NAME="isv-web-kb",
    )
    captured: dict[str, str] = {}

    def fake_retrieve(**kwargs):
        captured.update(kwargs)
        return (
            "Education organizations are increasing responsible AI investment.",
            [
                {"title": "Leadership update", "url": "https://example.test/leadership"},
                {"title": "AI investment", "url": "https://example.test/strategy"},
            ],
        )

    monkeypatch.setattr("app.isv_sources._retrieve_search_knowledge_base", fake_retrieve)
    result = ISVLiveWebIQ(settings).query(_context(settings))

    assert captured["knowledge_base"] == "isv-web-kb"
    assert result.facts["web_live"] is True
    assert {citation.refId for citation in result.citations} == {"r9", "r10"}


def test_live_native_web_uses_isv_api_key(monkeypatch) -> None:
    calls: list[dict] = []

    class StubResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "webResults": [
                    {
                        "title": "Leadership update",
                        "url": "https://example.test/leadership",
                        "content": "Education organizations are appointing AI governance leaders.",
                    },
                    {
                        "title": "Automation market",
                        "url": "https://example.test/automation",
                        "content": "Education workflow automation investment is increasing.",
                    },
                ]
            }

    class StubClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
            return None

        def post(self, url, *, json, headers):  # noqa: ANN001
            calls.append({"url": url, "json": json, "headers": headers})
            return StubResponse()

    settings = Settings(
        _env_file=None,
        USE_LIVE_ISV_WEB=True,
        ISV_WEB_IQ_ENDPOINT="https://api.microsoft.ai/v3/search/web",
        ISV_WEB_IQ_API_KEY="isv-test-key",
    )
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: StubClient())

    result = ISVLiveWebIQ(settings).query(_context(settings))

    assert calls[0]["headers"]["x-apikey"] == "isv-test-key"
    assert "executive leadership" in calls[0]["json"]["query"]
    assert len(result.citations) == 2


def test_mock_work_reads_isv_workplace_corpus() -> None:
    settings = Settings(_env_file=None, APP_ENVIRONMENT="test")
    result = ISVMockWorkIQ(settings).query(_context(settings))

    assert {citation.refId for citation in result.citations} == {"r7", "r8"}
    assert result.facts["open_commitment_count"] == 0
    response = TestClient(app).get(result.citations[0].url)
    assert response.status_code == 200
    assert "Contoso Unified School District Renewal QBR Summary" in response.text


def test_live_work_requires_customer_and_internal_attributions(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class StubClient:
        def __init__(self, settings):  # noqa: ANN001
            return None

        def ask(self, *, user_assertion: str, question: str) -> WorkIQAnswer:
            captured.update(user_assertion=user_assertion, question=question)
            return WorkIQAnswer(
                text="The QBR requested a three-year proposal. The internal team has three commitments.",
                task_id="task-1",
                context_id="context-1",
                duration_ms=25,
                attributions=(
                    WorkIQAttribution(
                        title="Contoso Unified School District Renewal QBR",
                        url="https://example.test/qbr",
                    ),
                    WorkIQAttribution(
                        title="Internal Renewal Plan",
                        url="https://example.test/plan",
                    ),
                ),
            )

    monkeypatch.setattr("app.isv_sources.WorkIQClient", StubClient)
    settings = Settings(_env_file=None, USE_LIVE_ISV_WORK=True)
    context = _context(settings)
    result = ISVLiveWorkIQ(settings).query(
        ISVQueryContext(
            question=context.question,
            account=context.account,
            renewal=context.renewal,
            registry=context.registry,
            user_access_token="delegated-token",
        )
    )

    assert captured["user_assertion"] == "delegated-token"
    assert "[Microsoft IQ for ISVs Demo v1]" in captured["question"]
    assert "up to six item titles" in captured["question"]
    assert "Do not provide an assessment" in captured["question"]
    assert result.facts["work_live"] is True
    assert {citation.refId for citation in result.citations} == {"r7", "r8"}
