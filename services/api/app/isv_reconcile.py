"""Guided reconciliation: how sources are weighed and combined into one assessment.

Design (mirrors the proven "ground truth wins, agents narrate" pattern):

1. An authority map says which source is most trusted for each kind of claim.
2. A Critic cross-checks every business signal against structured ground truth (the Fabric
   records). Ground truth wins on any disagreement and the conflict is recorded, never dropped.
3. Confidence is computed from the evidence (conflicts, unavailable sources), not hard-coded.
4. An optional model step writes the prose. It narrates the decided verdict; it never decides it,
   and its output is rejected unless it keeps the verdict and cites only known evidence.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.config import Settings
from app.isv_schemas import (
    BusinessSignalV1,
    Confidence,
    ReconciliationV1,
    SignalStatus,
)
from app.schemas import Evidence

logger = logging.getLogger("isviq.reconcile")

# Most-trusted source first, per kind of claim. Edit this map to change which source wins a tie.
AUTHORITY: dict[str, tuple[str, ...]] = {
    "numbers": ("fabric", "work", "web", "foundry"),
    "rules": ("foundry", "fabric", "work", "web"),
    "commitments": ("work", "fabric", "foundry", "web"),
    "external": ("web", "work", "fabric", "foundry"),
}

# Which kind of claim each signal category makes.
CLAIM_TYPE = {
    "adoption": "numbers",
    "support": "numbers",
    "commercial": "rules",
    "relationship": "commitments",
    "expansion": "numbers",
}

# Worst status wins when findings disagree.
_STATUS_RANK: dict[str, int] = {"negative": 3, "watch": 2, "unknown": 1, "positive": 0}
_CONFIDENCE_ORDER: tuple[Confidence, ...] = ("low", "medium", "high")


def ground_truth_status(category: str, facts: dict[str, Any]) -> tuple[SignalStatus, str] | None:
    """The best status the structured records allow for a signal category, with the reason.

    Returns None when the records do not constrain the category.
    """
    if category == "support" and facts["open_p1"]:
        return "watch", f"{len(facts['open_p1'])} P1 cases are still open in the support records"
    if category == "adoption" and float(facts["analytics"].get("trend_percent", 0)) < 0:
        return "watch", "Analytics adoption is trending down in the usage records"
    if category == "commercial" and facts["overdue"]:
        return "watch", f"{len(facts['overdue'])} invoices are overdue in the billing records"
    return None


def criticize(
    signals: list[BusinessSignalV1],
    facts: dict[str, Any],
) -> tuple[list[BusinessSignalV1], list[str]]:
    """Apply ground truth to signals. Returns corrected signals and the recorded conflicts."""
    conflicts: list[str] = []
    corrected: list[BusinessSignalV1] = []
    for signal in signals:
        truth = ground_truth_status(signal.category, facts)
        if truth and _STATUS_RANK[truth[0]] > _STATUS_RANK[signal.status]:
            conflicts.append(
                f"'{signal.title}' was reported as {signal.status}; the records say {truth[0]} "
                f"({truth[1]}). Ground truth applied."
            )
            signal = signal.model_copy(update={"status": truth[0]})
        corrected.append(signal)
    return corrected, conflicts


def overall_status(signals: list[BusinessSignalV1]) -> SignalStatus:
    worst: SignalStatus = "positive"
    for signal in signals:
        if _STATUS_RANK[signal.status] > _STATUS_RANK[worst]:
            worst = signal.status
    return worst


def computed_confidence(
    declared: Confidence,
    conflicts: list[str],
    unavailable: list[str],
) -> Confidence:
    """Lower the declared confidence when the evidence is weaker than the template assumed."""
    index = _CONFIDENCE_ORDER.index(declared)
    if conflicts:
        index -= 1
    if unavailable:
        index -= 1 if len(unavailable) == 1 else 2
    return _CONFIDENCE_ORDER[max(index, 0)]


def build_reconciliation(
    signals: list[BusinessSignalV1],
    conflicts: list[str],
    sources_used: list[str],
    unavailable: list[str],
    declared_confidence: Confidence,
    narration: str,
) -> ReconciliationV1:
    return ReconciliationV1(
        authority={claim: list(order) for claim, order in AUTHORITY.items()},
        conflicts=conflicts,
        sourcesUsed=sources_used,
        sourcesUnavailable=unavailable,
        overallStatus=overall_status(signals),
        confidence=computed_confidence(declared_confidence, conflicts, unavailable),
        narration="model" if narration == "model" else "template",
    )


_REF = re.compile(r"\[(r\d+)\]")
_SYSTEM_PROMPT = (
    "You write the explanation for a sales renewal assessment. The verdict, criteria and "
    "evidence are already decided and are given to you. Rewrite the draft as a clear, concise "
    "briefing for an account executive. Rules: keep the verdict and confidence exactly as given; "
    "use only facts in the draft and evidence; cite evidence only as [r#] using ids provided; "
    "state conflicts and missing evidence plainly; do not promise credits, prices or dates; "
    "do not use em dashes."
)


def narrate(
    settings: Settings,
    *,
    question: str,
    draft: str,
    verdict_word: str,
    evidence: list[Evidence],
    conflicts: list[str],
    authority_note: str,
) -> str | None:
    """Ask the model to rewrite the draft. Returns None on any failure or rule violation."""
    if not (settings.USE_LIVE_ISV_NARRATION and settings.ISV_OPENAI_ENDPOINT):
        return None
    try:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import AzureOpenAI

        client = AzureOpenAI(
            azure_endpoint=settings.ISV_OPENAI_ENDPOINT,
            api_version=settings.ISV_OPENAI_API_VERSION,
            azure_ad_token_provider=get_bearer_token_provider(
                DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
            ),
            timeout=settings.ISV_NARRATION_TIMEOUT_SECONDS,
        )
        evidence_block = "\n".join(
            f"[{item.refId}] ({item.source.value}) {item.title}: {item.snippet}" for item in evidence
        )
        conflict_block = "\n".join(f"- {item}" for item in conflicts) or "- none"
        response = client.chat.completions.create(
            model=settings.ISV_OPENAI_DEPLOYMENT,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Question: {question}\n\nSource authority: {authority_note}\n\n"
                        f"Recorded conflicts:\n{conflict_block}\n\nEvidence:\n{evidence_block}\n\n"
                        f"Decided draft to rewrite:\n{draft}"
                    ),
                },
            ],
        )
        text = (response.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001 - narration is optional; fall back to the template
        logger.warning("ISV narration failed, using the template: %s", exc)
        return None

    known = {item.refId for item in evidence}
    cited = set(_REF.findall(text))
    if not text or verdict_word.casefold() not in text.casefold() or not cited <= known or not cited:
        logger.warning("ISV narration rejected: verdict or citations did not validate")
        return None
    return text


def authority_note() -> str:
    return "; ".join(f"{claim}: {' > '.join(order)}" for claim, order in AUTHORITY.items())


def verdict_word(answer: str) -> str:
    match = re.match(r"Verdict:\s*(Not yet|Yes|No)\b", answer)
    return match.group(1) if match else ""


def unavailable_sources(results: list[Any]) -> list[str]:
    return [result.source.value for result in results if not result.citations]
