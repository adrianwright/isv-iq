from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yaml
from pydantic import TypeAdapter

from app.isv_schemas import (
    BusinessSignalV1,
    ExpansionOpportunityV1,
    SpecialistId,
    SpecialistInsightV1,
)

_SPECIALIST_ID = TypeAdapter(SpecialistId)


def _load_specs(path: Path) -> list[dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("specialists"), list):
        raise ValueError(f"{path} must define a specialists list")
    return payload["specialists"]


def run_isv_specialists(
    *,
    specialists_path: Path,
    signals: list[BusinessSignalV1],
    opportunities: list[ExpansionOpportunityV1],
) -> list[SpecialistInsightV1]:
    specs = _load_specs(specialists_path)
    signal_by_category = {signal.category: signal for signal in signals}
    specs = [
        spec
        for spec in specs
        if str(spec["signal_category"]) in signal_by_category
    ]
    opportunity = opportunities[0] if opportunities else None

    def run(spec: dict[str, Any]) -> SpecialistInsightV1:
        specialist_id = _SPECIALIST_ID.validate_python(spec["id"])
        category = str(spec["signal_category"])
        signal = signal_by_category[category]
        recommendation, lead = _recommendation(specialist_id, signal, opportunity)
        return SpecialistInsightV1(
            id=specialist_id,
            label=str(spec["label"]),
            domain=str(spec["domain"]),
            status=signal.status,
            summary=signal.impact,
            recommendation=recommendation,
            evidenceRefs=signal.evidenceRefs,
            investigationLead=lead,
        )

    with ThreadPoolExecutor(max_workers=len(specs)) as executor:
        return list(executor.map(run, specs))


def _recommendation(
    specialist_id: str,
    signal: BusinessSignalV1,
    opportunity: ExpansionOpportunityV1 | None,
) -> tuple[str, str | None]:
    if signal.status == "positive":
        if specialist_id == "commercial":
            return (
                "Advance the approved commercial package with explicit rollout and value controls.",
                "Confirm the final release date and executive checkpoint.",
            )
        if specialist_id == "adoption":
            return (
                "Use the strong active-user base to sequence expansion and measure incremental value.",
                "Define the first post-launch adoption and value checkpoint.",
            )
        if specialist_id == "support":
            return (
                "Maintain the current service-health cadence while the expansion enters execution.",
                "Confirm that no new priority incident changes rollout readiness.",
            )
        if specialist_id == "relationship":
            return (
                "Activate the executive sponsor around the approved business case and rollout plan.",
                "Confirm sponsor attendance at the first value checkpoint.",
            )
        if specialist_id == "expansion" and opportunity:
            return (
                f"Advance the {opportunity.product} opportunity through a phased rollout "
                f"for its {opportunity.currency} {opportunity.estimatedArr:,} potential.",
                "Confirm rollout sequence, change management, and measurable value checkpoints.",
            )
    if specialist_id == "commercial":
        return (
            "Confirm invoice timing and route the three-year proposal through Finance and executive approval.",
            "Determine whether payment timing changes the proposal approval path.",
        )
    if specialist_id == "adoption":
        return (
            "Set a measured Analytics recovery milestone with an executive-dashboard adoption target.",
            "Validate which user cohorts account for the 14% decline.",
        )
    if specialist_id == "support":
        return (
            "Deliver the incident summary, committed remediation, and service-credit recommendation first.",
            "Confirm customer acceptance criteria for closing the recovery plan.",
        )
    if specialist_id == "relationship":
        return (
            "Prepare executive outreach that acknowledges the breach and connects recovery to customer priorities.",
            "Test whether the new CIO will sponsor the three-year path after recovery evidence is presented.",
        )
    if specialist_id == "expansion" and opportunity:
        return (
            f"Reserve architecture capacity and qualify the {opportunity.product} "
            f"opportunity before positioning its {opportunity.currency} "
            f"{opportunity.estimatedArr:,} potential.",
            "Confirm workshop scope, technical feasibility, and executive sponsorship.",
        )
    return (signal.remediation or "Review the signal with the accountable owner.", None)
