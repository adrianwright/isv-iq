from __future__ import annotations

from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from app.isv_schemas import (
    AccountSnapshotV1,
    BusinessRiskV1,
    BusinessSignalV1,
    ExpansionOpportunityV1,
    ISVAskRequestV1,
    RenewalAssessmentV1,
    RenewalSummaryV1,
)
from tools.validate_isv_consistency import validate


def test_isv_request_contract_is_additive_and_version_ready() -> None:
    request = ISVAskRequestV1(
        question="Give me an executive renewal brief for Contoso Unified School District.",
        accountId="ACC-1001",
        renewalId="REN-1001",
    )

    assert request.accountId == "ACC-1001"
    assert request.renewalId == "REN-1001"


def test_isv_domain_models_accept_the_hero_scenario() -> None:
    registry = yaml.safe_load(
        (ROOT / "data" / "isv" / "registry.yaml").read_text(encoding="utf-8")
    )
    account = registry["accounts"][0]
    renewal = registry["renewals"][0]

    snapshot = AccountSnapshotV1(
        id=account["id"],
        name=account["name"],
        industry=account["industry"],
        segment=account["segment"],
        region=account["region"],
        health=account["health"],
        annualRecurringRevenue=account["annual_recurring_revenue"],
        currency=account["currency"],
        primaryContact="Maya Chen",
        executiveSponsor="Alex Johnson",
    )
    summary = RenewalSummaryV1(
        id=renewal["id"],
        renewalDate=renewal["renewal_date"],
        daysToRenewal=renewal["days_to_renewal"],
        currentArr=renewal["current_arr"],
        forecastArr=renewal["forecast_arr"],
        currency=renewal["currency"],
        stage=renewal["stage"],
        requestedTermMonths=renewal["requested_term_months"],
    )
    assessment = RenewalAssessmentV1(
        status="at_risk",
        label="Renewal at risk",
        confidence="high",
    )
    signal = BusinessSignalV1(
        id="SIG-SUPPORT",
        category="support",
        title="Support recovery is incomplete",
        status="negative",
        impact="Two open P1 cases and one SLA breach reduce renewal confidence.",
        evidenceRefs=["r1", "r2"],
    )
    risk = BusinessRiskV1(
        id="RISK-1001",
        title="Customer confidence",
        severity="high",
        impact="Unresolved reliability concerns may reduce scope or delay signature.",
        evidenceRefs=["r1"],
    )
    opportunity = ExpansionOpportunityV1(
        id="EXP-1001",
        product="AI Automation",
        estimatedArr=450000,
        currency="USD",
        fit="strong",
        confidence="medium",
        rationale="The customer's public strategy and internal request align.",
        blockers=["Solution architect capacity"],
        evidenceRefs=["r3", "r4"],
    )

    assert snapshot.id == "ACC-1001"
    assert summary.id == "REN-1001"
    assert assessment.status == "at_risk"
    assert signal.status == "negative"
    assert risk.severity == "high"
    assert opportunity.fit == "strong"


def test_prompt_catalog_contains_all_four_iq_demo_prompts() -> None:
    catalog = yaml.safe_load(
        (ROOT / "data" / "isv" / "prompts.yaml").read_text(encoding="utf-8")
    )

    all_iqs = {"fabric", "foundry", "work", "web"}
    prompts = catalog["prompts"]

    assert len(prompts) == 4
    assert all(set(prompt["required_iqs"]) == all_iqs for prompt in prompts)
    assert {prompt["intent"] for prompt in prompts} == {
        "renewal_forecast",
        "proposal_readiness",
        "expansion_gate",
        "expansion_acceleration",
    }
    assert {prompt["category"] for prompt in prompts} == {
        "understand",
        "prepare",
        "expand",
        "act",
    }
    assert all(len(prompt["text"]) >= 200 for prompt in prompts)


def test_isv_scenario_consistency_validator_passes() -> None:
    assert validate() == []
