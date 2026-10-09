from __future__ import annotations

from app.config import Settings
from app.isv_orchestrator import ISVOrchestrator, _account_operating_facts
from app.isv_reconcile import (
    AUTHORITY,
    computed_confidence,
    criticize,
    narrate,
    verdict_word,
)
from app.isv_schemas import BusinessSignalV1, ISVAskRequestV1


def _signal(category: str, status: str) -> BusinessSignalV1:
    return BusinessSignalV1(
        id=f"SIG-{category}",
        category=category,
        title=f"{category} signal",
        status=status,
        impact="impact",
    )


def _facts() -> dict:
    orchestrator = ISVOrchestrator()
    request = ISVAskRequestV1(question="Should we increase the renewal forecast?")
    return _account_operating_facts(orchestrator._context(request))


def test_critic_applies_ground_truth_and_records_the_conflict() -> None:
    facts = _facts()
    assert facts["open_p1"], "demo data should have open P1 cases"

    corrected, conflicts = criticize([_signal("support", "positive")], facts)

    assert corrected[0].status == "watch"
    assert len(conflicts) == 1
    assert "Ground truth applied" in conflicts[0]


def test_critic_never_improves_a_status() -> None:
    corrected, conflicts = criticize([_signal("support", "negative")], _facts())

    assert corrected[0].status == "negative"
    assert conflicts == []


def test_confidence_drops_for_conflicts_and_unavailable_sources() -> None:
    assert computed_confidence("high", [], []) == "high"
    assert computed_confidence("high", ["conflict"], []) == "medium"
    assert computed_confidence("high", [], ["web"]) == "medium"
    assert computed_confidence("high", ["conflict"], ["web", "work"]) == "low"
    assert computed_confidence("low", ["conflict"], ["web"]) == "low"


def test_every_claim_type_ranks_all_four_sources() -> None:
    for order in AUTHORITY.values():
        assert sorted(order) == ["fabric", "foundry", "web", "work"]


def test_result_carries_a_guided_reconciliation() -> None:
    result = ISVOrchestrator().answer(
        ISVAskRequestV1(question="Should we increase the renewal forecast?")
    )

    assert result.reconciliation is not None
    assert result.reconciliation.method == "guided"
    assert result.reconciliation.narration == "template"
    assert set(result.reconciliation.sourcesUsed) == {"fabric", "foundry", "work", "web"}
    assert result.assessment.confidence == result.reconciliation.confidence
    assert f"Confidence: {result.assessment.confidence}." in result.answer


def test_narration_is_skipped_unless_enabled() -> None:
    assert (
        narrate(
            Settings(),
            question="q",
            draft="Verdict: No.",
            verdict_word="No",
            evidence=[],
            conflicts=[],
            authority_note="",
        )
        is None
    )


def test_verdict_word_reads_the_decided_verdict() -> None:
    assert verdict_word("Verdict: Not yet. Confidence: high.") == "Not yet"
    assert verdict_word("Verdict: No — hold.") == "No"
    assert verdict_word("no verdict here") == ""
