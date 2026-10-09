from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.isv_orchestrator import ISVOrchestrator
from app.isv_runtime import load_isv_registry, resolve_isv_context
from app.isv_schemas import ISVAskRequestV1
from app.isv_sources import ISVLiveFabricIQ, ISVQueryContext
from app.main import app


def test_isv_orchestrator_returns_all_four_iqs_and_business_assessment() -> None:
    result = ISVOrchestrator().answer(
        ISVAskRequestV1(
            question="Give me an executive renewal brief for Contoso Unified School District.",
            accountId="ACC-1001",
            renewalId="REN-1001",
        )
    )

    assert result.schemaVersion == "isv.v1"
    assert result.account.id == "ACC-1001"
    assert result.renewal.id == "REN-1001"
    assert result.assessment.status == "at_risk"
    assert {entry.source.value for entry in result.sourceMap} == {
        "fabric",
        "foundry",
        "work",
        "web",
    }
    assert [signal.category for signal in result.signals] == [
        "commercial",
        "adoption",
        "support",
        "relationship",
    ]
    assert result.opportunities == []
    assert result.mode == "mock"


def test_churn_question_returns_churn_assessment() -> None:
    result = ISVOrchestrator().answer(
        ISVAskRequestV1(
            question="Is Contoso at risk of churn?",
            accountId="ACC-1001",
            renewalId="REN-1001",
        )
    )

    assert result.intent == "churn_risk"
    assert result.assessment.status == "at_risk"
    assert result.assessment.label == "Contoso is at risk of churn"
    assert "Verdict: Yes — Contoso is at risk of churn" in result.answer
    assert "P1 cases" in result.answer
    assert "churn risk" in result.nextAction.text
    assert set(result.answerRefs) <= {item.refId for item in result.evidence}


def test_isv_prompt_intent_changes_the_narrative_and_action() -> None:
    result = ISVOrchestrator().answer(
        ISVAskRequestV1(
            question=(
                "Should we advance the $450K AI Automation opportunity to a funded "
                "architecture workshop now?"
            )
        )
    )

    assert result.intent == "expansion_gate"
    assert "funding the architecture workshop" in result.nextAction.text
    assert "Verdict: Not yet" in result.answer
    assert "[r3]" in result.answer


@pytest.mark.parametrize(
    ("question", "account_id", "renewal_id", "expected_intent", "answer_marker"),
    [
        (
            "Should we increase the renewal forecast from $2.2M to the full $2.4M?",
            "ACC-1001",
            "REN-1001",
            "renewal_forecast",
            "Verdict: No",
        ),
        (
            "Are we ready to send the three-year price-protected proposal by October 13?",
            "ACC-1001",
            "REN-1001",
            "proposal_readiness",
            "Verdict: Yes",
        ),
        (
            "Should we advance the $450K AI Automation opportunity to a funded architecture workshop?",
            "ACC-1001",
            "REN-1001",
            "expansion_gate",
            "Verdict: Not yet",
        ),
        (
            "Should we accelerate the $300K Fabrikam Unified School District AI Automation expansion now?",
            "ACC-1002",
            "REN-1002",
            "expansion_acceleration",
            "Verdict: Yes",
        ),
    ],
)
def test_isv_grounded_synthesis_covers_four_demo_scenarios(
    question: str,
    account_id: str,
    renewal_id: str,
    expected_intent: str,
    answer_marker: str,
) -> None:
    result = ISVOrchestrator().answer(
        ISVAskRequestV1(
            question=question,
            accountId=account_id,
            renewalId=renewal_id,
        )
    )
    evidence_refs = {item.refId for item in result.evidence}

    assert result.intent == expected_intent
    assert answer_marker in result.answer
    assert len(result.answerRefs) >= 7
    assert set(result.answerRefs) <= evidence_refs
    assert all(f"[{ref}]" in result.answer for ref in result.answerRefs)


def test_isv_api_and_stream_return_versioned_result() -> None:
    client = TestClient(app)
    payload = {
        "question": "What has changed since the last QBR?",
        "accountId": "ACC-1001",
        "renewalId": "REN-1001",
    }

    response = client.post("/api/isv/ask", json=payload)
    stream = client.post("/api/isv/ask/stream", json=payload)

    assert response.status_code == 200
    assert response.json()["schemaVersion"] == "isv.v1"
    assert len(response.json()["specialists"]) == 4
    assert stream.status_code == 200
    assert "event: final" in stream.text
    assert '"schemaVersion":"isv.v1"' in stream.text
    assert '"specialists":[' in stream.text


def test_isv_live_fabric_uses_isolated_data_agent(
    monkeypatch,
) -> None:
    settings = Settings(
        _env_file=None,
        APP_ENVIRONMENT="development",
        USE_LIVE_ISV_FABRIC=True,
        ISV_FABRIC_WORKSPACE_ID="isv-workspace",
        ISV_FABRIC_DATA_AGENT_ID="isv-agent",
    )
    registry = load_isv_registry(str(settings.DATA_DIR / "isv" / "registry.yaml"))
    account, renewal = resolve_isv_context(registry, "ACC-1001", "REN-1001")
    captured: dict[str, str] = {}

    async def fake_call(url: str, scope: str, question: str) -> str:
        captured.update(url=url, scope=scope, question=question)
        return (
            "Contoso Unified School District has USD 2,400,000 ARR. Renewal REN-1001 is due "
            "2026-12-20 with 75 days remaining. Analytics adoption is 53%."
        )

    monkeypatch.setattr("app.isv_sources.call_fabric_mcp", fake_call)
    monkeypatch.setattr(
        "app.isv_sources.run_coro_blocking",
        lambda make_coro: asyncio.run(make_coro()),
    )

    result = ISVLiveFabricIQ(settings).query(
        ISVQueryContext(
            question="Give me the renewal facts.",
            account=account,
            renewal=renewal,
            registry=registry,
        )
    )

    assert "/workspaces/isv-workspace/dataagents/isv-agent/" in captured["url"]
    assert "ACC-1001" in captured["question"]
    assert result.facts["fabric_live"] is True
    assert {citation.refId for citation in result.citations} == {"r4", "r5", "r6"}


def test_isv_orchestrator_times_sources_that_report_no_duration() -> None:
    orchestrator = ISVOrchestrator()
    results = orchestrator._query_all(
        orchestrator._context(
            ISVAskRequestV1(question="Forecast?", accountId="ACC-1001", renewalId="REN-1001")
        )
    )

    assert all(result.duration_ms > 0 for result in results)


def test_isv_decisions_have_distinct_result_shapes() -> None:
    scenarios = {
        "renewal_forecast": "Should we increase the renewal forecast to the full $2.4M?",
        "proposal_readiness": "Are we ready to send the price-protected proposal by October 13?",
        "expansion_gate": "Should we fund the $450K architecture workshop?",
        "expansion_acceleration": (
            "Should we accelerate the $300K Fabrikam Unified School District AI Automation expansion now?"
        ),
    }

    results = {
        intent: ISVOrchestrator().answer(
            ISVAskRequestV1(
                question=question,
                accountId="ACC-1002" if intent == "expansion_acceleration" else "ACC-1001",
                renewalId="REN-1002" if intent == "expansion_acceleration" else "REN-1001",
            )
        )
        for intent, question in scenarios.items()
    }

    assert {intent: len(result.signals) for intent, result in results.items()} == {
        "renewal_forecast": 4,
        "proposal_readiness": 3,
        "expansion_gate": 4,
        "expansion_acceleration": 5,
    }
    assert {intent: len(result.risks) for intent, result in results.items()} == {
        "renewal_forecast": 3,
        "proposal_readiness": 1,
        "expansion_gate": 2,
        "expansion_acceleration": 1,
    }
    assert results["expansion_gate"].opportunities[0].product == "AI Automation"
    assert results["expansion_acceleration"].opportunities[0].product == "AI Automation"
    assert all(
        not result.opportunities
        for intent, result in results.items()
        if intent not in {"expansion_gate", "expansion_acceleration"}
    )
    assert len({result.assessment.label for result in results.values()}) == 4
    assert len({tuple(result.missingData) for result in results.values()}) == 4
    assert len({tuple(step.step for step in result.trace[:5]) for result in results.values()}) == 4
