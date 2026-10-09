from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

from app.config import Settings, get_settings
from app.isv_runtime import find_isv_record, load_isv_registry, related, resolve_isv_context
from app.isv_reconcile import (
    authority_note,
    build_reconciliation,
    computed_confidence,
    criticize,
    narrate,
    unavailable_sources,
    verdict_word,
)
from app.isv_schemas import (
    AccountSnapshotV1,
    BusinessRiskV1,
    BusinessSignalV1,
    ExpansionOpportunityV1,
    ISVAskRequestV1,
    ISVAskResultV1,
    RenewalAssessmentV1,
    RenewalSummaryV1,
    SpecialistInsightV1,
)
from app.isv_specialists import run_isv_specialists
from app.isv_sources import (
    ISVQueryContext,
    ISVSource,
    ISVSourceResult,
    ISV_RETRIEVING,
    create_isv_sources,
)
from app.schemas import (
    HumanReview,
    NextAction,
    Owner,
    PlanEventPayload,
    Reviewer,
    SourceQueryEventPayload,
    SourceResultEventPayload,
    TraceStep,
)


class ISVOrchestrator:
    def __init__(
        self,
        settings: Settings | None = None,
        sources: list[ISVSource] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.registry = load_isv_registry(str(self.settings.DATA_DIR / "isv" / "registry.yaml"))
        self.sources = sources or create_isv_sources(self.settings)

    @staticmethod
    def plan_steps() -> list[str]:
        return [
            "Reviewing account and renewal economics",
            "Checking adoption, support, and payment signals",
            "Reading contract, pricing, and product guidance",
            "Reviewing customer sentiment and open commitments",
            "Checking company and competitive developments",
            "Composing a governed renewal recommendation",
        ]

    def _context(
        self,
        request: ISVAskRequestV1,
        user_access_token: str | None = None,
    ) -> ISVQueryContext:
        account, renewal = resolve_isv_context(
            self.registry, request.accountId, request.renewalId
        )
        return ISVQueryContext(
            question=request.question,
            account=account,
            renewal=renewal,
            registry=self.registry,
            user_access_token=user_access_token,
        )

    def _timed_query(self, source: ISVSource, context: ISVQueryContext) -> ISVSourceResult:
        started = time.perf_counter()
        result = source.query(context)
        if not result.duration_ms:
            result.duration_ms = round((time.perf_counter() - started) * 1000)
        return result

    def _query_all(self, context: ISVQueryContext) -> list[ISVSourceResult]:
        with ThreadPoolExecutor(max_workers=len(self.sources)) as executor:
            return list(
                executor.map(lambda source: self._timed_query(source, context), self.sources)
            )

    def answer(
        self,
        request: ISVAskRequestV1,
        user_access_token: str | None = None,
    ) -> ISVAskResultV1:
        context = self._context(request, user_access_token)
        return self._assemble(context, self._query_all(context))

    async def stream(
        self,
        request: ISVAskRequestV1,
        user_access_token: str | None = None,
    ) -> AsyncIterator[tuple[str, str]]:
        context = self._context(request, user_access_token)
        yield "plan", PlanEventPayload(steps=self.plan_steps()).model_dump_json()
        for source in self.sources:
            yield "source_query", SourceQueryEventPayload(
                source=source.name,
                label=source.label,
                query=f"{source.label} context for {context.account['name']}",
                retrieving=ISV_RETRIEVING[source.name],
            ).model_dump_json()

        async def run_source(source: ISVSource) -> ISVSourceResult:
            return await asyncio.to_thread(self._timed_query, source, context)

        tasks = [asyncio.create_task(run_source(source)) for source in self.sources]
        results: list[ISVSourceResult] = []
        for task in asyncio.as_completed(tasks):
            result = await task
            results.append(result)
            yield "source_result", SourceResultEventPayload(
                source=result.source,
                status="complete",
                summary=result.summary,
                citations=[citation.refId for citation in result.citations],
                durationMs=result.duration_ms,
                retrieving=ISV_RETRIEVING[result.source],
                evidenceCount=len(result.citations),
                evidenceNoun="sources",
            ).model_dump_json()

        ordered = sorted(
            results,
            key=lambda item: [source.name for source in self.sources].index(item.source),
        )
        final = await asyncio.to_thread(self._assemble, context, ordered)
        yield "final", f'{{"result":{final.model_dump_json()}}}'

    def _assemble(
        self,
        context: ISVQueryContext,
        results: list[ISVSourceResult],
    ) -> ISVAskResultV1:
        registry = context.registry
        account = context.account
        renewal = context.renewal
        intent = _intent(context.question)
        primary_contact = find_isv_record(
            registry, "contacts", account["primary_contact_id"]
        )
        executive_sponsor = find_isv_record(
            registry, "employees", account["executive_sponsor_id"]
        )
        owner = find_isv_record(registry, "employees", renewal["owner_id"])
        success_manager = _account_team_employee(
            registry, account["id"], "customer_success_manager"
        )
        support_manager = _account_team_employee(
            registry, account["id"], "support_escalation_manager"
        )
        expansion_architect = _account_team_employee(
            registry, account["id"], "solution_architect"
        )
        expansion = related(registry, "expansion_candidates", "renewal_id", renewal["id"])[0]
        evidence = [citation for result in results for citation in result.citations]

        signals = _decision_business_signals(
            intent,
            context,
            owner=owner,
            success_manager=success_manager,
            support_manager=support_manager,
            executive_sponsor=executive_sponsor,
            expansion_architect=expansion_architect,
            expansion=expansion,
        )
        risks = _decision_business_risks(intent, context)
        signals, conflicts = criticize(signals, _account_operating_facts(context))
        opportunities = [
            ExpansionOpportunityV1(
                id=expansion["id"],
                product=expansion["product"],
                estimatedArr=expansion["estimated_arr"],
                currency=expansion["currency"],
                fit=expansion["fit"],
                confidence=expansion["confidence"],
                rationale=expansion["rationale"],
                blockers=(
                    []
                    if str(expansion["blocker"]).casefold() == "none"
                    else [expansion["blocker"]]
                ),
                evidenceRefs=["r3", "r8", "r9", "r10"],
            )
        ]
        opportunities = (
            opportunities
            if intent in {"expansion_gate", "expansion_acceleration"}
            else []
        )
        specialists = run_isv_specialists(
            specialists_path=self.settings.DATA_DIR / "isv" / "specialists.yaml",
            signals=signals,
            opportunities=opportunities,
        )
        next_action = _next_action(intent, owner, support_manager, success_manager)
        trace = _trace(intent, results, specialists)
        answer, bottom_line, scope, requested_answer_refs = _grounded_narrative(
            intent,
            context,
        )
        available_refs = {item.refId for item in evidence}
        answer_refs = [ref for ref in requested_answer_refs if ref in available_refs]
        if not answer_refs:
            raise RuntimeError("Grounded synthesis produced no valid evidence references.")
        evidence = [item for item in evidence if item.refId in answer_refs]
        unavailable = unavailable_sources(results)
        assessment = _decision_assessment(intent)
        confidence = computed_confidence(assessment.confidence, conflicts, unavailable)
        answer = re.sub(r"Confidence: \w+\.", f"Confidence: {confidence}.", answer, count=1)
        narrated = narrate(
            self.settings,
            question=context.question,
            draft=answer,
            verdict_word=verdict_word(answer),
            evidence=evidence,
            conflicts=conflicts,
            authority_note=authority_note(),
        )
        if narrated:
            answer = narrated
        reconciliation = build_reconciliation(
            signals,
            conflicts,
            [result.source.value for result in results if result.citations],
            unavailable,
            assessment.confidence,
            "model" if narrated else "template",
        )
        assessment = assessment.model_copy(update={"confidence": reconciliation.confidence})
        source_map = _decision_source_map(results, set(answer_refs))
        missing_data = _decision_missing_data(intent)
        reviewers = _decision_reviewers(
            intent,
            owner=owner,
            support_manager=support_manager,
            success_manager=success_manager,
            executive_sponsor=executive_sponsor,
            expansion_architect=expansion_architect,
        )

        return ISVAskResultV1(
            question=context.question,
            answer=answer,
            answerRefs=answer_refs,
            intent=intent,
            scope=scope,
            bottomLine=bottom_line,
            account=AccountSnapshotV1(
                id=account["id"],
                name=account["name"],
                industry=account["industry"],
                segment=account["segment"],
                region=account["region"],
                health=account["health"],
                annualRecurringRevenue=account["annual_recurring_revenue"],
                currency=account["currency"],
                primaryContact=primary_contact["display_name"],
                executiveSponsor=executive_sponsor["display_name"],
            ),
            renewal=RenewalSummaryV1(
                id=renewal["id"],
                renewalDate=renewal["renewal_date"],
                daysToRenewal=renewal["days_to_renewal"],
                currentArr=renewal["current_arr"],
                forecastArr=renewal["forecast_arr"],
                currency=renewal["currency"],
                stage=renewal["stage"],
                requestedTermMonths=renewal["requested_term_months"],
            ),
            assessment=assessment,
            signals=signals,
            risks=risks,
            opportunities=opportunities,
            specialists=specialists,
            reconciliation=reconciliation,
            unavailableSources=unavailable,
            agentDriven=bool(narrated),
            evidence=evidence,
            missingData=missing_data,
            nextAction=next_action,
            humanReview=HumanReview(
                owner=Owner(
                    id=executive_sponsor["id"],
                    display=executive_sponsor["display_name"],
                    role=executive_sponsor["title"],
                ),
                reason=_decision_human_review_reason(intent),
            ),
            reviewers=reviewers,
            sourceMap=source_map,
            trace=trace,
            mode=(
                "live"
                if any(
                    (
                        self.settings.USE_LIVE_ISV_FABRIC,
                        self.settings.USE_LIVE_ISV_FOUNDRY,
                        self.settings.USE_LIVE_ISV_WEB,
                        self.settings.USE_LIVE_ISV_WORK,
                    )
                )
                else "mock"
            ),
            disclaimer=registry["meta"]["disclaimer"],
        )


def _intent(question: str) -> str:
    normalized = question.casefold()
    if "accelerate" in normalized and ("$300k" in normalized or "fabrikam" in normalized):
        return "expansion_acceleration"
    if "price-protected" in normalized or "october 13" in normalized:
        return "proposal_readiness"
    if "funded architecture workshop" in normalized or "$450k" in normalized:
        return "expansion_gate"
    if "exit renewal recovery" in normalized or "exit criteria" in normalized:
        return "recovery_exit"
    return "renewal_forecast"


def _account_team_employee(
    registry: dict[str, Any],
    account_id: str,
    role: str,
) -> dict[str, Any]:
    team_member = next(
        item
        for item in related(registry, "account_team", "account_id", account_id)
        if item["role"] == role
    )
    return find_isv_record(registry, "employees", team_member["employee_id"])


def _account_operating_facts(context: ISVQueryContext) -> dict[str, Any]:
    registry = context.registry
    account_id = context.account["id"]
    subscriptions = related(registry, "subscriptions", "account_id", account_id)
    analytics_subscription = next(
        item for item in subscriptions if item["product"] == "Analytics"
    )
    analytics = next(
        item
        for item in related(registry, "product_usage", "account_id", account_id)
        if item["subscription_id"] == analytics_subscription["id"]
    )
    cases = related(registry, "support_cases", "account_id", account_id)
    open_p1 = [
        item
        for item in cases
        if item["priority"] == "P1" and item["status"] != "resolved"
    ]
    breached_p1 = [item for item in open_p1 if item.get("sla_breached") is True]
    invoices = related(registry, "invoices", "account_id", account_id)
    overdue = [item for item in invoices if item["status"] == "overdue"]
    commitments = related(
        registry, "commitments", "renewal_id", context.renewal["id"]
    )
    completed_commitments = [
        item for item in commitments if item["status"] == "completed"
    ]
    return {
        "analytics": analytics,
        "open_p1": open_p1,
        "breached_p1": breached_p1,
        "overdue": overdue,
        "commitments": commitments,
        "completed_commitments": completed_commitments,
    }


def _decision_business_signals(
    intent: str,
    context: ISVQueryContext,
    *,
    owner: dict[str, Any],
    success_manager: dict[str, Any],
    support_manager: dict[str, Any],
    executive_sponsor: dict[str, Any],
    expansion_architect: dict[str, Any],
    expansion: dict[str, Any],
) -> list[BusinessSignalV1]:
    facts = _account_operating_facts(context)
    analytics = facts["analytics"]
    open_p1 = facts["open_p1"]
    completed = facts["completed_commitments"]
    commitments = facts["commitments"]

    if intent == "proposal_readiness":
        return [
            BusinessSignalV1(
                id="SIG-PROPOSAL-APPROVAL",
                category="commercial",
                title="Proposal release approvals are complete",
                status="positive",
                impact=(
                    "Pricing, Finance, payment, roadmap, and recovery-package gates "
                    "are complete for the October 13 release."
                ),
                evidenceRefs=["r2", "r4", "r6", "r7", "r8"],
                owner=owner["display_name"],
                remediation="Release the approved proposal and track customer response.",
            ),
            BusinessSignalV1(
                id="SIG-RECOVERY-PACKAGE",
                category="support",
                title="Recovery evidence is approved for proposal release",
                status="watch",
                impact=(
                    "The district accepted the recovery package, although "
                    f"{len(open_p1)} P1 cases still require operational monitoring."
                ),
                evidenceRefs=["r1", "r6", "r7"],
                owner=support_manager["display_name"],
                remediation="Keep operational reporting attached to the proposal follow-up.",
            ),
            BusinessSignalV1(
                id="SIG-CUSTOMER-REQUEST",
                category="relationship",
                title="District leaders requested the three-year proposal",
                status="positive",
                impact=(
                    "The executive buyer requested the proposal and the account team "
                    "recorded a controlled release decision."
                ),
                evidenceRefs=["r7", "r8", "r9"],
                owner=executive_sponsor["display_name"],
                remediation="Send the proposal and schedule executive follow-up.",
            ),
        ]

    if intent == "expansion_gate":
        return [
            BusinessSignalV1(
                id="SIG-DISTRICT-DEMAND",
                category="expansion",
                title="Administrative automation demand is credible",
                status="positive",
                impact=(
                    f"District strategy and account-team evidence support a "
                    f"USD {int(expansion['estimated_arr']):,} AI Automation opportunity."
                ),
                evidenceRefs=["r3", "r8", "r9", "r10"],
                owner=expansion_architect["display_name"],
                remediation="Preserve the opportunity while completing workshop entry gates.",
            ),
            BusinessSignalV1(
                id="SIG-WORKSHOP-SPONSOR",
                category="relationship",
                title="Interest exists but workshop sponsorship is not confirmed",
                status="watch",
                impact=(
                    "District leaders support responsible AI, but no funded workshop "
                    "sponsor and scope are recorded."
                ),
                evidenceRefs=["r7", "r8", "r9"],
                owner=executive_sponsor["display_name"],
                remediation="Confirm sponsor, scope, and measurable value criteria.",
            ),
            BusinessSignalV1(
                id="SIG-EXPANSION-ADOPTION",
                category="adoption",
                title="Analytics adoption weakens expansion readiness",
                status="negative",
                impact=(
                    f"Analytics adoption is {analytics['adoption_percent']}% with a "
                    f"{analytics['trend_percent']}% trend."
                ),
                evidenceRefs=["r5"],
                owner=success_manager["display_name"],
                remediation="Demonstrate adoption recovery before funding the workshop.",
            ),
            BusinessSignalV1(
                id="SIG-EXPANSION-CAPACITY",
                category="support",
                title="Operational trust and architect capacity remain constrained",
                status="negative",
                impact=(
                    f"{len(open_p1)} P1 cases remain open and the assigned architect "
                    "is capacity constrained."
                ),
                evidenceRefs=["r1", "r6", "r7"],
                owner=support_manager["display_name"],
                remediation="Stabilize support and reserve architecture capacity.",
            ),
        ]

    if intent == "expansion_acceleration":
        return [
            BusinessSignalV1(
                id="SIG-ACCELERATION-DEMAND",
                category="expansion",
                title="Customer demand and value fit are confirmed",
                status="positive",
                impact=(
                    f"Fabrikam requested an accelerated rollout for a "
                    f"USD {int(expansion['estimated_arr']):,} opportunity."
                ),
                evidenceRefs=["r3", "r7", "r8", "r9", "r10"],
                owner=expansion_architect["display_name"],
                remediation="Advance the expansion into execution planning.",
            ),
            BusinessSignalV1(
                id="SIG-ACCELERATION-ADOPTION",
                category="adoption",
                title="Adoption supports expansion",
                status="positive",
                impact=(
                    f"Analytics adoption is {analytics['adoption_percent']}% and "
                    f"improved {analytics['trend_percent']}% in the latest period."
                ),
                evidenceRefs=["r5"],
                owner=success_manager["display_name"],
                remediation="Use the active user base to anchor rollout sequencing.",
            ),
            BusinessSignalV1(
                id="SIG-ACCELERATION-SUPPORT",
                category="support",
                title="Support health presents no release blocker",
                status="positive",
                impact="No P1 case, SLA breach, or overdue invoice blocks expansion.",
                evidenceRefs=["r1", "r6"],
                owner=support_manager["display_name"],
                remediation="Maintain the current support-health review cadence.",
            ),
            BusinessSignalV1(
                id="SIG-ACCELERATION-SPONSOR",
                category="relationship",
                title="Executive sponsorship is active",
                status="positive",
                impact="The executive buyer approved the business case and requested acceleration.",
                evidenceRefs=["r7", "r8", "r9"],
                owner=executive_sponsor["display_name"],
                remediation="Confirm the executive rollout checkpoint.",
            ),
            BusinessSignalV1(
                id="SIG-ACCELERATION-COMMERCIAL",
                category="commercial",
                title="Commercial and architecture gates are complete",
                status="positive",
                impact=(
                    f"All {len(completed)} recorded commitments are complete, "
                    "invoices are current, and specialist capacity is reserved."
                ),
                evidenceRefs=["r2", "r4", "r6", "r8"],
                owner=owner["display_name"],
                remediation="Issue the expansion execution plan and commercial package.",
            ),
        ]

    return [
        BusinessSignalV1(
            id="SIG-FORECAST-COMMERCIAL",
            category="commercial",
            title="Proposal readiness supports the current forecast",
            status="positive",
            impact=(
                f"All {len(completed)} of {len(commitments)} commitments are complete, "
                "payment is current, and the proposal is ready to send."
            ),
            evidenceRefs=["r2", "r4", "r6", "r7", "r8"],
            owner=owner["display_name"],
            remediation="Track customer response before increasing forecast value.",
        ),
        BusinessSignalV1(
            id="SIG-FORECAST-ADOPTION",
            category="adoption",
            title="Adoption trajectory does not support full value",
            status="negative",
            impact=(
                f"Analytics adoption is {analytics['adoption_percent']}% with a "
                f"{analytics['trend_percent']}% trend."
            ),
            evidenceRefs=["r5"],
            owner=success_manager["display_name"],
            remediation="Require measured adoption improvement before restoring full value.",
        ),
        BusinessSignalV1(
            id="SIG-FORECAST-SUPPORT",
            category="support",
            title="Open incidents keep downside exposure active",
            status="negative",
            impact=(
                f"{len(open_p1)} P1 cases remain open despite approval of the "
                "customer recovery package."
            ),
            evidenceRefs=["r1", "r6", "r7"],
            owner=support_manager["display_name"],
            remediation="Verify sustained resolution and customer acceptance.",
        ),
        BusinessSignalV1(
            id="SIG-FORECAST-EXECUTIVE",
            category="relationship",
            title="Executive response remains the final forecast uncertainty",
            status="watch",
            impact=(
                "The new CIO requested the proposal but has not accepted the full "
                "renewal value."
            ),
            evidenceRefs=["r7", "r8", "r9"],
            owner=executive_sponsor["display_name"],
            remediation="Obtain the CIO's response before changing forecast value.",
        ),
    ]


def _decision_business_risks(
    intent: str,
    context: ISVQueryContext,
) -> list[BusinessRiskV1]:
    if intent == "proposal_readiness":
        return [
            BusinessRiskV1(
                id="RISK-PROPOSAL-FOLLOWUP",
                title="Operational follow-through after release",
                severity="medium",
                impact="Open incidents still require visible reporting after the proposal is sent.",
                evidenceRefs=["r1", "r6", "r7"],
            )
        ]
    if intent == "expansion_gate":
        return [
            BusinessRiskV1(
                id="RISK-WORKSHOP-CAPACITY",
                title="Workshop capacity is not protected",
                severity="high",
                impact="Funding before architect capacity is reserved risks a failed start.",
                evidenceRefs=["r3", "r8"],
            ),
            BusinessRiskV1(
                id="RISK-WORKSHOP-TRUST",
                title="Operational trust is not sufficient for expansion",
                severity="high",
                impact="Open support and adoption issues could undermine workshop sponsorship.",
                evidenceRefs=["r1", "r5", "r6", "r7"],
            ),
        ]
    if intent == "expansion_acceleration":
        return [
            BusinessRiskV1(
                id="RISK-ROLLOUT-GOVERNANCE",
                title="Acceleration requires controlled rollout governance",
                severity="low",
                impact="A phased rollout and value checkpoints should preserve the positive case.",
                evidenceRefs=["r3", "r8", "r10"],
            )
        ]
    return [
        BusinessRiskV1(
            id="RISK-FORECAST-ADOPTION",
            title="Full-value adoption case is unproven",
            severity="high",
            impact="Declining Analytics usage does not support restoring the USD 200,000 gap.",
            evidenceRefs=["r5", "r7"],
        ),
        BusinessRiskV1(
            id="RISK-FORECAST-SUPPORT",
            title="Incident resolution is not yet sustained",
            severity="high",
            impact="Open P1 cases could weaken customer acceptance after proposal release.",
            evidenceRefs=["r1", "r6", "r7"],
        ),
        BusinessRiskV1(
            id="RISK-FORECAST-EXECUTIVE",
            title="CIO response is not recorded",
            severity="medium",
            impact="Proposal readiness does not equal acceptance of the full renewal value.",
            evidenceRefs=["r8", "r9", "r10"],
        ),
    ]


def _decision_source_map(
    results: list[ISVSourceResult],
    answer_refs: set[str],
) -> list[Any]:
    source_map = []
    for result in results:
        selected_refs = [
            citation.refId
            for citation in result.citations
            if citation.refId in answer_refs
        ]
        source_map.append(
            result.to_source_map_item().model_copy(
                update={
                    "citations": selected_refs,
                    "evidenceCount": len(selected_refs),
                }
            )
        )
    return source_map


def _decision_missing_data(intent: str) -> list[str]:
    return {
        "renewal_forecast": [
            "Measured Analytics adoption improvement",
            "Sustained closure evidence for the two open P1 cases",
            "New CIO response to the three-year proposal",
            "Customer confirmation of the full renewal value",
        ],
        "proposal_readiness": [
            "Customer response after proposal delivery",
            "Ongoing incident-monitoring results",
            "Final signature timing",
        ],
        "expansion_gate": [
            "Confirmed executive sponsor for AI Automation",
            "Protected solution-architect capacity",
            "Agreed workshop scope and measurable value criteria",
            "Security, data, and integration prerequisite validation",
            "Customer acceptance of the support recovery package",
        ],
        "expansion_acceleration": [
            "Final phased-rollout start date",
            "Regional deployment sequence",
            "First value-realization checkpoint date",
        ],
        "recovery_exit": [
            "Customer acceptance of the incident recovery package",
            "Closure evidence for the premium-support SLA breach",
            "Measured Analytics adoption improvement",
            "Completion evidence for all three customer commitments",
            "Payment confirmation and updated executive sentiment",
        ],
    }[intent]


def _decision_assessment(intent: str) -> RenewalAssessmentV1:
    if intent == "proposal_readiness":
        return RenewalAssessmentV1(
            status="on_track",
            label="Proposal is ready for controlled release on October 13",
            confidence="high",
        )
    if intent == "expansion_gate":
        return RenewalAssessmentV1(
            status="at_risk",
            label="Workshop funding not ready; qualification should continue",
            confidence="medium",
        )
    if intent == "expansion_acceleration":
        return RenewalAssessmentV1(
            status="on_track",
            label="Expansion acceleration is supported by the evidence",
            confidence="high",
        )
    if intent == "recovery_exit":
        return RenewalAssessmentV1(
            status="at_risk",
            label="Recovery exit criteria are not yet met",
            confidence="high",
        )
    return RenewalAssessmentV1(
        status="at_risk",
        label="Full-value forecast unsupported; hold at USD 2.2M",
        confidence="high",
    )


def _decision_human_review_reason(intent: str) -> str:
    return {
        "renewal_forecast": (
            "Approve the forecast hold and the evidence triggers for restoring or reducing value."
        ),
        "proposal_readiness": (
            "Confirm the approved commercial release and monitor customer response and open incidents."
        ),
        "expansion_gate": (
            "Approve workshop funding only after sponsorship, capacity, and technical entry criteria."
        ),
        "expansion_acceleration": (
            "Approve the phased expansion plan and preserve value and governance checkpoints."
        ),
        "recovery_exit": (
            "Approve exit from recovery only after customer acceptance and closure evidence."
        ),
    }[intent]


def _reviewer(
    role: str,
    person: dict[str, Any],
    status: Literal["assigned", "pending", "complete"],
) -> Reviewer:
    return Reviewer(
        role=role,
        owner=Owner(
            id=person["id"],
            display=person["display_name"],
            role=person["title"],
        ),
        status=status,
    )


def _decision_reviewers(
    intent: str,
    *,
    owner: dict[str, Any],
    support_manager: dict[str, Any],
    success_manager: dict[str, Any],
    executive_sponsor: dict[str, Any],
    expansion_architect: dict[str, Any],
) -> list[Reviewer]:
    if intent == "proposal_readiness":
        return [
            _reviewer("Commercial release owner", owner, "complete"),
            _reviewer("Support recovery approval", support_manager, "complete"),
            _reviewer("Executive pricing approval", executive_sponsor, "complete"),
        ]
    if intent == "expansion_gate":
        return [
            _reviewer("Architecture gate owner", expansion_architect, "assigned"),
            _reviewer("Executive sponsor", executive_sponsor, "pending"),
            _reviewer("Recovery dependency", support_manager, "pending"),
        ]
    if intent == "expansion_acceleration":
        return [
            _reviewer("Commercial expansion owner", owner, "complete"),
            _reviewer("Architecture readiness", expansion_architect, "complete"),
            _reviewer("Executive sponsor", executive_sponsor, "complete"),
        ]
    if intent == "recovery_exit":
        return [
            _reviewer("Recovery acceptance owner", support_manager, "assigned"),
            _reviewer("Adoption recovery", success_manager, "pending"),
            _reviewer("Commercial closure", owner, "pending"),
        ]
    return [
        _reviewer("Forecast owner", owner, "assigned"),
        _reviewer("Adoption validation", success_manager, "pending"),
        _reviewer("Executive forecast review", executive_sponsor, "pending"),
    ]


def _grounded_narrative(
    intent: str,
    context: ISVQueryContext,
) -> tuple[str, str, str, list[str]]:
    registry = context.registry
    renewal = context.renewal
    currency = renewal["currency"]
    current_arr = int(renewal["current_arr"])
    forecast_arr = int(renewal["forecast_arr"])
    contraction_risk = current_arr - forecast_arr
    operating_facts = _account_operating_facts(context)
    analytics = operating_facts["analytics"]
    open_p1 = operating_facts["open_p1"]
    overdue_invoices = operating_facts["overdue"]
    expansion = related(registry, "expansion_candidates", "renewal_id", renewal["id"])[0]
    commitments = operating_facts["commitments"]
    completed_commitments = operating_facts["completed_commitments"]
    commitment_details = []
    for commitment in sorted(commitments, key=lambda item: item["due_date"]):
        owner = find_isv_record(registry, "employees", commitment["owner_id"])
        commitment_details.append(
            f"{commitment['id']} ({owner['display_name']}, due {commitment['due_date']}): "
            f"{commitment['text']}"
        )
    commitment_text = " ".join(commitment_details)

    if intent == "proposal_readiness":
        return (
            "Verdict: Yes. Confidence: high. Criteria met — district leaders requested the "
            "three-year price-protected proposal, strategic-pricing and Finance approvals are "
            f"recorded, payment is current, and all {len(completed_commitments)} commitments are "
            "complete [r2][r4][r6][r7][r8]. The district accepted the incident recovery package "
            "and committed Analytics roadmap date, satisfying the controlled-release requirements "
            "[r1][r7]. Remaining condition — open P1 cases still require monitoring, but they are "
            "not a proposal-release blocker because the approved recovery evidence accompanies "
            "the package [r6][r7]. Contradictory evidence — operational reliability remains a "
            "forecast risk, while the proposal decision itself has complete approvals and an "
            "explicit customer request [r7][r9]. Execution controls — send on October 13, attach "
            "the recovery and roadmap evidence, and schedule executive follow-up. "
            f"Completed owners and commitments — {commitment_text}",
            "Send the approved three-year proposal on October 13 and monitor customer response and "
            "incident follow-through.",
            "Three-year proposal release decision, completed approvals, execution controls, owners, and due dates.",
            ["r1", "r2", "r4", "r6", "r7", "r8", "r9"],
        )

    if intent == "expansion_acceleration":
        return (
            "Verdict: Yes. Confidence: high. Criteria met — Fabrikam has active executive "
            f"sponsorship, {analytics['adoption_percent']}% Analytics adoption with a positive "
            f"{analytics['trend_percent']}% trend, no open P1 cases or SLA breach, current payment "
            f"status, and {len(completed_commitments)} completed commercial and architecture "
            f"commitments [r1][r4][r5][r6][r7][r8]. The USD "
            f"{int(expansion['estimated_arr']):,} AI Automation opportunity has strong fit, "
            "completed security and integration validation, reserved specialist capacity, and "
            "customer-approved measurable value criteria [r2][r3][r7][r8]. External retail "
            "strategy and market signals reinforce the timing without replacing the internal "
            "readiness evidence [r9][r10]. Remaining controls — confirm the phased start date, "
            "regional rollout sequence, and first value checkpoint. No evidence-backed blocker "
            "requires delaying the expansion.",
            f"Accelerate the USD {int(expansion['estimated_arr']):,} AI Automation expansion with "
            "a phased rollout and explicit value checkpoints.",
            "Expansion acceleration decision based on demand, adoption, architecture, capacity, support, and commercial readiness.",
            ["r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8", "r9", "r10"],
        )

    if intent == "expansion_gate":
        return (
            "Verdict: Not yet. Confidence: medium. Criteria met — AI Automation has "
            f"{currency} {int(expansion['estimated_arr']):,} of modeled expansion value, documented "
            "customer and account-team interest, relevant product guidance, and public strategic "
            "alignment [r3][r8][r9][r10]. Criteria not met — no completed architecture validation "
            "or funded workshop outcome is recorded, solution-architect capacity is constrained, "
            f"Analytics adoption is only {analytics['adoption_percent']}%, and {len(open_p1)} P1 "
            "cases continue to impair trust [r5][r6][r7]. Contradictory evidence — strategic fit and "
            "customer interest are positive, but technical readiness and operational credibility are "
            "not yet demonstrated. Missing evidence — confirmed executive sponsorship, protected "
            "architect capacity, agreed workshop scope, measurable value criteria, security and "
            "integration prerequisites, and customer acceptance of the recovery package [r1]. "
            "Next gate — reserve capacity and complete a no-cost qualification session before "
            "approving a funded architecture workshop.",
            "Keep the opportunity active, but do not fund the architecture workshop until recovery "
            "acceptance, sponsorship, capacity, and technical entry criteria are confirmed.",
            "AI Automation workshop funding decision, criteria met and unmet, contradictions, and next gate.",
            ["r1", "r3", "r5", "r6", "r7", "r8", "r9", "r10"],
        )

    if intent == "recovery_exit":
        open_commitments = [
            item for item in commitments if item["status"] != "completed"
        ]
        payment_state = (
            f"invoice {overdue_invoices[0]['id']} remains overdue"
            if overdue_invoices
            else "payment is current"
        )
        return (
            "Verdict: No. Confidence: high. Criteria met — a recovery process, accountable owners, "
            "premium-support remedies, and dated commitments exist [r1][r7][r8]. Criteria not met — "
            f"{len(open_p1)} P1 cases remain open, one SLA breach is unresolved, Analytics adoption "
            f"is {analytics['adoption_percent']}% after a "
            f"{abs(float(analytics['trend_percent'])):g}% decline, {payment_state}, and "
            f"{len(open_commitments)} customer commitments remain open [r4][r5][r6][r7]. "
            "Contradictory evidence — the customer remains commercially "
            "engaged and AI strategy is favorable, but neither proves recovery acceptance or restored "
            "operational trust [r7][r9][r10]. Missing evidence — customer acceptance of the incident "
            "package, SLA recovery confirmation, a measured adoption improvement, payment "
            "confirmation, completed commitments, and the new CIO's response to the proposal. "
            f"Remaining exit criteria and owners — {commitment_text}",
            "Keep the account in renewal recovery until the customer accepts the support package and "
            "the operational, commercial, and sentiment exit criteria are evidenced.",
            "Recovery-exit decision against explicit operational, commercial, and customer criteria.",
            ["r1", "r4", "r5", "r6", "r7", "r8", "r9", "r10"],
        )

    return (
        "Verdict: No — do not forecast the full renewal value today. Confidence: high. Criteria "
        f"met for retaining the current {currency} {forecast_arr:,} forecast — the customer remains "
        "engaged, requested a three-year proposal, and has a credible conditional expansion path "
        "[r7][r8][r9]. Criteria not met for the full "
        f"{currency} {current_arr:,} forecast — the model already carries "
        f"{currency} {contraction_risk:,} of contraction exposure, Analytics adoption is "
        f"{analytics['adoption_percent']}% after a "
        f"{abs(float(analytics['trend_percent'])):g}% decline, {len(open_p1)} P1 cases remain open, "
        f"{len(operating_facts['breached_p1'])} SLA breach remains under monitoring, and "
        "payment is current [r4][r5][r6]. "
        "Contradictory evidence — commercial engagement and public AI strategy support recovery, "
        "while unresolved operational trust and a new-CIO vendor review weaken confidence [r7][r9][r10]. "
        "Proposal readiness, completed commitments, and current payment support retaining the "
        "existing forecast, but they do not establish acceptance of the full renewal value [r1][r2]. "
        "Missing evidence — sustained P1 closure, measured adoption improvement, the CIO's response "
        "to the proposal, and customer confirmation of full value. Next forecast action — hold at "
        "the current forecast and define evidence-based triggers for restoring or reducing it.",
        f"Hold the forecast at {currency} {forecast_arr:,}; do not restore the full "
        f"{currency} {current_arr:,} until support stability, adoption recovery, and executive "
        "acceptance are evidenced.",
        "Full-value renewal forecast decision with criteria, contradictions, missing evidence, and triggers.",
        ["r1", "r2", "r4", "r5", "r6", "r7", "r8", "r9", "r10"],
    )


def _next_action(
    intent: str,
    owner: dict[str, Any],
    support_manager: dict[str, Any],
    success_manager: dict[str, Any],
) -> NextAction:
    if intent == "proposal_readiness":
        text = "Send the approved proposal on October 13 with its recovery evidence."
        steps = [
            "Release the approved three-year price-protected proposal.",
            "Attach the recovery summary and committed Analytics roadmap date.",
            "Schedule executive follow-up and continue incident monitoring.",
        ]
    elif intent == "expansion_gate":
        text = "Complete qualification before funding the architecture workshop."
        steps = [
            "Reserve solution-architect capacity.",
            "Confirm executive sponsorship and the priority workflow.",
            "Define security, integration, and measurable value entry criteria.",
        ]
    elif intent == "recovery_exit":
        text = "Keep the account in recovery until every exit criterion has evidence."
        steps = [
            f"{support_manager['display_name']}: obtain customer acceptance of the recovery package.",
            f"{success_manager['display_name']}: demonstrate measured adoption improvement.",
            f"{owner['display_name']}: close commitments and confirm payment timing.",
        ]
    elif intent == "expansion_acceleration":
        text = "Launch the approved AI Automation expansion through a phased rollout."
        steps = [
            "Confirm the rollout start date and regional sequence.",
            "Publish the architecture and change-management plan.",
            "Measure the first value checkpoint with the executive sponsor.",
        ]
    else:
        text = "Hold the current forecast and define evidence-based adjustment triggers."
        steps = [
            "Restore full value only after recovery acceptance and commitment closure.",
            "Reduce further if another commitment is missed or customer sentiment weakens.",
            "Review the forecast when payment and adoption evidence changes.",
        ]
    return NextAction(
        text=text,
        steps=steps,
        owner=Owner(id=owner["id"], display=owner["display_name"], role=owner["title"]),
        taskType="renewal_recovery",
        due="2026-10-13",
    )


def _trace(
    intent: str,
    results: list[ISVSourceResult],
    specialists: list[SpecialistInsightV1],
) -> list[TraceStep]:
    steps_by_intent = {
        "renewal_forecast": [
            ("Quantified renewal exposure", "Compared current ARR, forecast ARR, and contraction exposure."),
            ("Tested operational downside", "Applied adoption, support, SLA, and payment evidence."),
            ("Reconciled buying signals", "Compared proposal engagement with customer and CIO sentiment."),
            ("Defined forecast triggers", "Specified evidence for restoring or reducing forecast value."),
            ("Validated forecast decision", "Checked citations, uncertainty, owner, and executive review."),
        ],
        "proposal_readiness": [
            ("Validated pricing policy", "Checked strategic-pricing and approval requirements."),
            ("Built the commitment critical path", "Ordered incident, roadmap, and proposal obligations by due date."),
            ("Checked release blockers", "Tested payment, recovery acceptance, and customer requirements."),
            ("Assigned blocker owners", "Mapped each unresolved gate to its accountable owner."),
            ("Validated proposal decision", "Checked citations, target date, and required approvals."),
        ],
        "expansion_gate": [
            ("Validated customer demand", "Checked account-team interest, sponsor evidence, and public strategy."),
            ("Tested product and value fit", "Reviewed product guidance and modeled expansion value."),
            ("Tested technical readiness", "Checked architecture, security, integration, and capacity prerequisites."),
            ("Applied recovery dependency", "Evaluated whether support trust permits workshop funding."),
            ("Validated investment gate", "Checked citations, entry criteria, and accountable reviewers."),
        ],
        "expansion_acceleration": [
            ("Validated customer demand", "Confirmed the funded automation priority and executive request."),
            ("Tested adoption strength", "Verified positive Analytics adoption and value realization."),
            ("Confirmed technical readiness", "Checked security, integration, architecture, and capacity gates."),
            ("Cleared operational blockers", "Verified support health, payment status, and completed commitments."),
            ("Validated acceleration decision", "Checked citations, rollout controls, and accountable reviewers."),
        ],
        "recovery_exit": [
            ("Tested support exit criteria", "Checked case closure, SLA recovery, and customer acceptance."),
            ("Tested adoption recovery", "Compared current adoption with the required improvement evidence."),
            ("Tested commercial closure", "Checked commitments, payment, and proposal response."),
            ("Reconciled executive sentiment", "Compared engagement with the new CIO's vendor review."),
            ("Validated recovery status", "Checked citations, remaining owners, and exit evidence."),
        ],
    }
    steps = steps_by_intent[intent]
    source_order = [result.source for result in results]
    trace = [
        TraceStep(
            step=step,
            source=source_order[min(index, len(source_order) - 1)]
            if index < len(source_order)
            else None,
            detail=detail,
            ts=index,
        )
        for index, (step, detail) in enumerate(steps)
    ]
    trace.extend(
        TraceStep(
            step=f"{specialist.label} assessment",
            detail=specialist.summary,
            ts=len(trace) + index,
        )
        for index, specialist in enumerate(specialists)
    )
    return trace
