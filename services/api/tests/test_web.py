from __future__ import annotations

import httpx

from app.config import Settings
from app.sources.base import QueryContext
from app.sources.web import LiveWebIQ


def _context() -> QueryContext:
    return QueryContext(
        question="What external evidence is available?",
        patient_id="PT-1042",
        trial_id="NCT99004324",
        registry={
            "patients": [
                {
                    "id": "PT-1042",
                    "diagnosis": "metastatic NSCLC",
                    "biomarkers": ["EGFR exon 20 insertion"],
                }
            ]
        },
    )


def test_live_web_does_not_invent_citation_without_references(monkeypatch) -> None:
    class StubResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "response": [
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": "No grounded external sources were returned.",
                            }
                        ]
                    }
                ],
                "references": [],
            }

    class StubClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
            return None

        def post(self, url, *, json, headers):  # noqa: ANN001, ARG002
            return StubResponse()

    source = LiveWebIQ(
        Settings(
            _env_file=None,
            SEARCH_ENDPOINT="https://search.example.test",
            WEB_KB_NAME="web-kb",
        )
    )
    monkeypatch.setattr(source, "_token", lambda: "token")
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: StubClient())

    result = source.query(_context())

    assert result.citations == []
    assert result.facts["reference_count"] == 0


def test_native_web_iq_uses_api_key_and_returns_citations(monkeypatch) -> None:
    calls: list[dict] = []

    class StubResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "webResults": [
                    {
                        "title": "Current oncology evidence",
                        "url": "https://example.test/evidence",
                        "content": "Fresh passage-level grounding.",
                    }
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

    source = LiveWebIQ(
        Settings(
            _env_file=None,
            WEB_IQ_ENDPOINT="https://api.microsoft.ai/v3/search/web",
            WEB_IQ_API_KEY="secret",
        )
    )
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: StubClient())

    result = source.query(_context())

    assert calls[0]["headers"]["x-apikey"] == "secret"
    assert calls[0]["json"]["contentFormat"] == "passage"
    assert result.citations[0].url == "https://example.test/evidence"
    assert result.facts["external_context"] == "Fresh passage-level grounding."
