from __future__ import annotations

import httpx

from app.config import Settings
from app.sources.base import QueryContext
from app.sources.web import LiveWebIQ


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

    result = source.query(
        QueryContext(
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
    )

    assert result.citations == []
    assert result.facts["reference_count"] == 0
