from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

from app.schemas import Evidence, Source, SourceMapItem
from app.config import Settings
from app.isv_runtime import related
from app.evidence import evidence_doc_url
from app.fabric_client import call_fabric_mcp, run_coro_blocking
from app.workiq import WorkIQClient


@dataclass(frozen=True)
class ISVQueryContext:
    question: str
    account: dict[str, Any]
    renewal: dict[str, Any]
    registry: dict[str, Any]
    user_access_token: str | None = None


@dataclass
class ISVSourceResult:
    source: Source
    label: str
    queries: list[str]
    summary: str
    citations: list[Evidence]
    facts: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0

    def to_source_map_item(self) -> SourceMapItem:
        return SourceMapItem(
            source=self.source,
            label=self.label,
            status="complete",
            queries=self.queries,
            citations=[citation.refId for citation in self.citations],
            durationMs=self.duration_ms,
            retrieving=ISV_RETRIEVING[self.source],
            evidenceCount=len(self.citations),
            evidenceNoun="sources",
        )


class ISVSource(Protocol):
    name: Source
    label: str

    def query(self, context: ISVQueryContext) -> ISVSourceResult:
        ...


ISV_RETRIEVING = {
    Source.FOUNDRY: "contract terms, support policy, pricing guidance, product roadmap",
    Source.FABRIC: "renewal, adoption, support, invoices, account ownership",
    Source.WORK: "customer sentiment, meetings, commitments, account-team decisions",
    Source.WEB: "leadership changes, company strategy, market and competitor signals",
}


class ISVMockFoundryIQ:
    name = Source.FOUNDRY
    label = "Foundry IQ"

    def __init__(self, settings: Settings) -> None:
        self.docs_dir = settings.DATA_DIR / "isv" / "foundry_docs"

    def query(self, context: ISVQueryContext) -> ISVSourceResult:
        contract = related(context.registry, "contracts", "renewal_id", context.renewal["id"])[0]
        documents = {
            metadata["doc_type"]: (path, metadata, body)
            for path, metadata, body in _read_isv_documents(self.docs_dir)
        }
        support_path, support_metadata, support_body = documents["support_policy"]
        pricing_path, pricing_metadata, pricing_body = documents["pricing_policy"]
        product_path, product_metadata, product_body = documents["product_brief"]
        citations = [
            Evidence(
                refId="r1",
                source=self.name,
                title=str(support_metadata["title"]),
                snippet=(
                    f"The {contract['support_tier']} support agreement provides a "
                    f"{contract['uptime_sla_percent']}% uptime SLA. "
                    f"{_isv_snippet(support_body, ('service-credit', 'priority-one'))}"
                ),
                url=evidence_doc_url("isv_foundry_docs", support_path.name),
                sourceType="support_policy",
            ),
            Evidence(
                refId="r2",
                source=self.name,
                title=str(pricing_metadata["title"]),
                snippet=_isv_snippet(pricing_body, ("three-year", "price protection")),
                url=evidence_doc_url("isv_foundry_docs", pricing_path.name),
                sourceType="pricing_policy",
            ),
            Evidence(
                refId="r3",
                source=self.name,
                title=str(product_metadata["title"]),
                snippet=_isv_snippet(product_body, ("architecture and value workshop", "workflow")),
                url=evidence_doc_url("isv_foundry_docs", product_path.name),
                sourceType="product_documentation",
            ),
        ]
        return ISVSourceResult(
            source=self.name,
            label=self.label,
            queries=[
                f"{context.account['name']} renewal contract and SLA obligations",
                "three-year pricing and AI Automation qualification policy",
            ],
            summary=(
                "The contract supports a service-credit review, while pricing and expansion "
                "require cross-functional approval and technical validation."
            ),
            citations=citations,
            facts={"service_credit_eligible": contract["service_credit_eligible"]},
            duration_ms=120,
        )


class ISVLiveFoundryIQ:
    name = Source.FOUNDRY
    label = "Foundry IQ"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def query(self, context: ISVQueryContext) -> ISVSourceResult:
        question = (
            f"Support this renewal scenario: {_isv_scenario_focus(context.question)}\n"
            f"For account {context.account['name']} ({context.account['id']}) and renewal "
            f"{context.renewal['id']}, retrieve the contract and premium-support obligations, "
            "strategic renewal pricing approvals, AI Automation qualification guidance, and the "
            "at-risk renewal recovery playbook. Distinguish policy from recorded customer facts "
            "and cite every document used."
        )
        answer, references = _retrieve_search_knowledge_base(
            endpoint=self.settings.ISV_SEARCH_ENDPOINT,
            knowledge_base=self.settings.ISV_FOUNDRY_KB_NAME,
            api_version=self.settings.ISV_SEARCH_API_VERSION,
            question=question,
        )
        if len(references) < 3:
            raise RuntimeError(
                "ISV Foundry IQ returned fewer than three grounded document references."
            )
        citation_specs = (
            (
                "r1",
                ("support", "contract", "recovery"),
                ("support", "service credit", "incident"),
                "support_policy",
            ),
            (
                "r2",
                ("pricing", "renewal"),
                ("three-year", "pricing", "price protection"),
                "pricing_policy",
            ),
            (
                "r3",
                ("automation", "product"),
                ("AI Automation", "architecture", "workshop"),
                "product_documentation",
            ),
        )
        used_references: set[int] = set()
        citations: list[Evidence] = []
        for ref_id, reference_terms, answer_terms, source_type in citation_specs:
            reference = _select_reference(references, used_references, reference_terms)
            citations.append(
                Evidence(
                    refId=ref_id,
                    source=self.name,
                    title=_reference_title(reference, f"Foundry policy document {ref_id}"),
                    snippet=_isv_answer_sentence(answer, answer_terms),
                    url=_isv_reference_link(reference),
                    sourceType=source_type,
                )
            )
        return ISVSourceResult(
            source=self.name,
            label=self.label,
            queries=[question],
            summary=answer.strip()[:700],
            citations=citations,
            facts={
                "foundry_live": True,
                "answer": answer,
                "reference_count": len(references),
            },
            duration_ms=0,
        )


class ISVMockFabricIQ:
    name = Source.FABRIC
    label = "Fabric IQ"

    def query(self, context: ISVQueryContext) -> ISVSourceResult:
        account_id = context.account["id"]
        usage = related(context.registry, "product_usage", "account_id", account_id)
        cases = related(context.registry, "support_cases", "account_id", account_id)
        invoices = related(context.registry, "invoices", "account_id", account_id)
        open_p1 = [case for case in cases if case["priority"] == "P1" and case["status"] != "resolved"]
        subscriptions = related(context.registry, "subscriptions", "account_id", account_id)
        analytics_subscription = next(
            item for item in subscriptions if item["product"] == "Analytics"
        )
        analytics = next(
            item for item in usage if item["subscription_id"] == analytics_subscription["id"]
        )
        overdue = [invoice for invoice in invoices if invoice["status"] == "overdue"]
        citations = [
            Evidence(
                refId="r4",
                source=self.name,
                title="Account and renewal record",
                snippet=(
                    f"{context.account['name']} has USD {context.renewal['current_arr']:,} ARR, "
                    f"renews in {context.renewal['days_to_renewal']} days, and is forecast "
                    f"{context.renewal['forecast_category']}."
                ),
                url=None,
                sourceType="crm_record",
            ),
            Evidence(
                refId="r5",
                source=self.name,
                title="Analytics adoption trend",
                snippet=(
                    f"Analytics adoption is {analytics['adoption_percent']}% with a "
                    f"{analytics['trend_percent']}% trend in the latest period."
                ),
                url=None,
                sourceType="product_telemetry",
            ),
            Evidence(
                refId="r6",
                source=self.name,
                title="Support and finance exposure",
                snippet=(
                    f"{len(open_p1)} P1 cases remain open; "
                    f"{sum(1 for case in open_p1 if case.get('sla_breached'))} breached SLA. "
                    + (
                        f"Invoice {overdue[0]['id']} is {overdue[0]['days_overdue']} days overdue."
                        if overdue
                        else "All recorded invoices are current."
                    )
                ),
                url=None,
                sourceType="operational_record",
            ),
        ]
        return ISVSourceResult(
            source=self.name,
            label=self.label,
            queries=[
                f"renewal, support, adoption, and invoice facts for {account_id}",
                f"account team and expansion capacity for {context.renewal['id']}",
            ],
            summary=(
                f"Structured data shows {len(open_p1)} open P1 cases, "
                f"{analytics['adoption_percent']}% Analytics adoption, "
                f"{len(overdue)} overdue invoices, and the recorded expansion candidate."
            ),
            citations=citations,
            facts={
                "open_p1_count": len(open_p1),
                "analytics_adoption": analytics["adoption_percent"],
                "analytics_trend": analytics["trend_percent"],
                "invoice_days_overdue": overdue[0]["days_overdue"] if overdue else 0,
            },
            duration_ms=95,
        )


class ISVLiveFabricIQ:
    name = Source.FABRIC
    label = "Fabric IQ"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._scaffold = ISVMockFabricIQ()

    async def _ask_one(self, question: str) -> str:
        last_error: Exception | None = None
        for _ in range(2):
            try:
                return await call_fabric_mcp(
                    self.settings.isv_fabric_mcp_url,
                    self.settings.FABRIC_API_SCOPE,
                    question,
                )
            except Exception as exc:  # noqa: BLE001 - the data agent intermittently returns 500
                last_error = exc
        assert last_error is not None
        raise last_error

    async def _ask_all(self, questions: list[str]) -> list[str]:
        return list(await asyncio.gather(*(self._ask_one(q) for q in questions)))

    def query(self, context: ISVQueryContext) -> ISVSourceResult:
        scaffold = self._scaffold.query(context)
        scope = (
            "Use only the selected customer-renewal Lakehouse tables. "
            f"For account {context.account['id']} and renewal {context.renewal['id']}, report: "
        )
        # Small focused questions keep each data-agent run to a few SQL queries; a single
        # all-in-one prompt took 75-110 s, while focused ones return in about 12 s.
        questions = [
            scope + "account name and ARR; renewal date, days to renewal, current and forecast "
            "ARR; and expansion candidates with estimated ARR. Give exact values and dates.",
            scope + "latest product adoption percentages and trends; count of open P1 support "
            "cases (open means status is anything other than resolved or closed) and SLA "
            "breaches; and overdue invoices and days overdue. Give exact values.",
            scope + "open commitments (status other than completed) with owners and due dates. "
            "Give exact values and dates.",
        ]
        answers = run_coro_blocking(lambda: self._ask_all(questions))
        answer = "\n".join(part for part in answers if part.strip())
        if not answer.strip():
            raise RuntimeError(
                f"ISV Fabric Data Agent returned no answer for {context.account['id']}"
            )

        citations = [
            Evidence(
                refId=citation.refId,
                source=self.name,
                title=f"{citation.title} (live Fabric Data Agent)",
                snippet=answer.strip()[:500],
                url=self.settings.isv_fabric_portal_url,
                sourceType="fabric_data_agent",
            )
            for citation in scaffold.citations
        ]
        return ISVSourceResult(
            source=self.name,
            label=self.label,
            queries=questions,
            summary=answer.strip()[:700],
            citations=citations,
            facts={
                **scaffold.facts,
                "fabric_live": True,
                "fabric_answer": answer,
            },
            duration_ms=0,
        )


class ISVMockWorkIQ:
    name = Source.WORK
    label = "Work IQ"

    def __init__(self, settings: Settings) -> None:
        self.work_dir = settings.DATA_DIR / "isv" / "work"

    def query(self, context: ISVQueryContext) -> ISVSourceResult:
        if context.account["id"] == "ACC-1002":
            qbr_name = "fabrikam_retail_qbr.md"
            plan_name = "fabrikam_internal_plan.md"
            commitments_name = "fabrikam_commitments.json"
            followup_metadata, followup = ({}, "")
        else:
            qbr_name = "alder_creek_qbr.md"
            plan_name = "internal_account_plan.md"
            commitments_name = "commitments.json"
            followup_metadata, followup = _read_isv_work_document(
                self.work_dir / "analytics_escalation_followup.md"
            )
        qbr_metadata, qbr = _read_isv_work_document(self.work_dir / qbr_name)
        plan_metadata, plan = _read_isv_work_document(self.work_dir / plan_name)
        commitment_payload = json.loads(
            (self.work_dir / commitments_name).read_text(encoding="utf-8")
        )
        if commitment_payload.get("synthetic") is not True:
            raise ValueError("ISV Work IQ commitments must be marked synthetic")
        commitments = commitment_payload.get("commitments", [])
        citations = [
            Evidence(
                refId="r7",
                source=self.name,
                title=str(qbr_metadata["title"]),
                snippet=_isv_snippet(
                    f"{qbr} {followup}",
                    ("three-year renewal proposal", "committed resolution date"),
                ),
                url=evidence_doc_url("isv_work", qbr_name),
                sourceType="m365_customer_activity",
            ),
            Evidence(
                refId="r8",
                source=self.name,
                title=str(plan_metadata["title"]),
                snippet=_isv_snippet(
                    plan,
                    ("renewal confidence", "AI Automation opportunity"),
                ),
                url=evidence_doc_url("isv_work", plan_name),
                sourceType="m365_team_activity",
            ),
        ]
        return ISVSourceResult(
            source=self.name,
            label=self.label,
            queries=[
                f"{context.account['name']} customer decisions and sentiment",
                "open account-team commitments and owners",
            ],
            summary=(
                f"Workplace activity for {context.account['name']} confirms the recorded "
                "customer decision, account-team posture, and commitment status."
            ),
            citations=citations,
            facts={
                "interaction_count": 3,
                "open_commitment_count": len(
                    [item for item in commitments if item["status"] == "open"]
                ),
                "followup_title": followup_metadata.get("title"),
            },
            duration_ms=105,
        )


class ISVLiveWorkIQ:
    name = Source.WORK
    label = "Work IQ"

    def __init__(self, settings: Settings) -> None:
        self.client = WorkIQClient(settings)

    def query(self, context: ISVQueryContext) -> ISVSourceResult:
        prompt = (
            "Find Microsoft 365 items containing the exact marker "
            f"[Microsoft IQ for ISVs Demo v1] and {context.account['name']}. "
            f"Retrieval focus: {_isv_work_focus(context.question)} "
            "Return only up to six item titles with their source links. Include at least one "
            "customer-facing QBR, email, or calendar item and at least one internal Teams, task, "
            "or account-plan item. Do not provide an assessment, recommendations, or a long summary."
        )
        answer = self.client.ask(
            user_assertion=context.user_access_token or "",
            question=prompt,
        )
        if len(answer.attributions) < 2:
            raise RuntimeError(
                "ISV Work IQ returned fewer than two grounded Microsoft 365 attributions."
            )
        citations = [
            Evidence(
                refId=f"r{index + 7}",
                source=self.name,
                title=attribution.title,
                snippet=answer.text[:500],
                url=attribution.url,
                sourceType=f"work_iq_{attribution.attribution_type}",
            )
            for index, attribution in enumerate(answer.attributions[:2])
        ]
        return ISVSourceResult(
            source=self.name,
            label=self.label,
            queries=[prompt],
            summary=answer.text,
            citations=citations,
            facts={
                "work_live": True,
                "work_iq_task_id": answer.task_id,
                "work_iq_context_id": answer.context_id,
                "work_iq_attribution_count": len(answer.attributions),
            },
            duration_ms=answer.duration_ms,
        )


class ISVMockWebIQ:
    name = Source.WEB
    label = "Web IQ"

    def query(self, context: ISVQueryContext) -> ISVSourceResult:
        signals = related(
            context.registry, "external_signals", "account_id", context.account["id"]
        )
        citations = [
            Evidence(
                refId="r9",
                source=self.name,
                title=signals[0]["title"],
                snippet=(
                    f"{signals[0]['impact']} {signals[1]['impact']}"
                ),
                url=signals[0]["source_url"],
                sourceType="synthetic_web_news",
            ),
            Evidence(
                refId="r10",
                source=self.name,
                title=signals[2]["title"],
                snippet=signals[2]["impact"],
                url=signals[2]["source_url"],
                sourceType="synthetic_web_news",
            ),
        ]
        return ISVSourceResult(
            source=self.name,
            label=self.label,
            queries=[
                f"{context.account['name']} leadership and AI strategy",
                f"{context.account['industry']} workflow automation developments",
            ],
            summary=(
                f"Public signals provide {context.account['industry']} strategy and market context "
                "for the AI Automation decision."
            ),
            citations=citations,
            facts={"external_signal_count": len(signals)},
            duration_ms=80,
        )


class ISVLiveWebIQ:
    name = Source.WEB
    label = "Web IQ"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def query(self, context: ISVQueryContext) -> ISVSourceResult:
        question = (
            f"Support this renewal scenario: {_isv_scenario_focus(context.question)}\n"
            f"Find current public context relevant to the {context.account['industry']} sector "
            f"and the scenario involving {context.account['name']}: executive leadership, "
            "strategic investment in AI or workflow automation, and competing sector-specific "
            "offerings. The named account is synthetic, so use public sector and market evidence "
            "without asserting that it describes the synthetic account. Return source URLs and "
            "separate verified public facts from inference."
        )
        if self.settings.ISV_WEB_IQ_API_KEY.strip():
            answer, references = self._query_native(question)
            mode = "native"
        else:
            answer, references = _retrieve_search_knowledge_base(
                endpoint=self.settings.ISV_SEARCH_ENDPOINT,
                knowledge_base=self.settings.ISV_WEB_KB_NAME,
                api_version=self.settings.ISV_SEARCH_API_VERSION,
                question=question,
            )
            mode = "search"
        if len(references) < 2:
            raise RuntimeError("ISV Web IQ returned fewer than two grounded public references.")

        citations = [
            Evidence(
                refId=f"r{index + 9}",
                source=self.name,
                title=_reference_title(reference, f"External web result {index + 1}"),
                snippet=_reference_snippet(reference, answer),
                url=str(reference.get("url") or reference.get("blobUrl") or ""),
                sourceType="web",
            )
            for index, reference in enumerate(references[:2])
        ]
        return ISVSourceResult(
            source=self.name,
            label=self.label,
            queries=[question],
            summary=(
                f"Web IQ ({mode}) returned current leadership, strategy, and competitive context."
            ),
            citations=citations,
            facts={
                "web_live": True,
                "external_context": answer[:4000],
                "reference_count": len(references),
            },
            duration_ms=0,
        )

    def _query_native(self, question: str) -> tuple[str, list[dict[str, Any]]]:
        import httpx

        with httpx.Client(timeout=90) as client:
            response = client.post(
                self.settings.ISV_WEB_IQ_ENDPOINT,
                json={
                    "query": question,
                    "maxResults": 5,
                    "contentFormat": "passage",
                    "maxLength": 8000,
                },
                headers={
                    "x-apikey": self.settings.ISV_WEB_IQ_API_KEY,
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            payload = response.json()
        results = payload.get("webResults", [])
        references = [item for item in results if isinstance(item, dict) and item.get("url")]
        answer = "\n\n".join(str(item.get("content") or "") for item in references)
        return answer, references


def create_isv_sources(settings: Settings) -> list[ISVSource]:
    return [
        (
            ISVLiveFoundryIQ(settings)
            if settings.USE_LIVE_ISV_FOUNDRY
            else ISVMockFoundryIQ(settings)
        ),
        ISVLiveFabricIQ(settings) if settings.USE_LIVE_ISV_FABRIC else ISVMockFabricIQ(),
        ISVLiveWorkIQ(settings) if settings.USE_LIVE_ISV_WORK else ISVMockWorkIQ(settings),
        ISVLiveWebIQ(settings) if settings.USE_LIVE_ISV_WEB else ISVMockWebIQ(),
    ]


def _read_isv_documents(
    directory: Path,
) -> list[tuple[Path, dict[str, Any], str]]:
    documents: list[tuple[Path, dict[str, Any], str]] = []
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            raise ValueError(f"{path} must include YAML front matter")
        _, front_matter, body = text.split("---", 2)
        metadata = yaml.safe_load(front_matter) or {}
        if metadata.get("synthetic") is not True:
            raise ValueError(f"{path} must be marked synthetic")
        documents.append((path, metadata, body.strip()))
    return documents


def _read_isv_work_document(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path} must include YAML front matter")
    _, front_matter, body = text.split("---", 2)
    metadata = yaml.safe_load(front_matter) or {}
    if metadata.get("synthetic") is not True:
        raise ValueError(f"{path} must be marked synthetic")
    return metadata, body.strip()


def _isv_work_focus(question: str) -> str:
    lower = question.casefold()
    if "accelerate" in lower and ("$300k" in lower or "fabrikam" in lower):
        return (
            "Find executive sponsorship, customer demand, adoption strength, architecture "
            "validation, specialist capacity, support health, and completed commitments."
        )
    if "price-protected" in lower or "october 13" in lower:
        return "Find the three-year proposal request, payment concern, support recovery, and open commitments."
    if "funded architecture workshop" in lower or "$450k" in lower:
        return "Find AI Automation demand, sponsor interest, architecture ownership, specialist capacity, and workshop plans."
    if "exit renewal recovery" in lower or "exit criteria" in lower:
        return "Find support recovery acceptance, commitment completion, payment confirmation, adoption recovery, and executive sentiment."
    if "full $2.4m" in lower or "reduce the forecast" in lower:
        return "Find customer sentiment, the three-year proposal request, unresolved concerns, and open commitments."
    return "Find customer sentiment, account-team decisions, and the three open commitments."


def _isv_scenario_focus(question: str) -> str:
    lower = question.casefold()
    if "accelerate" in lower and ("$300k" in lower or "fabrikam" in lower):
        return "whether the AI Automation expansion should be accelerated now"
    if "price-protected" in lower or "october 13" in lower:
        return "whether the three-year price-protected proposal is ready to send"
    if "funded architecture workshop" in lower or "$450k" in lower:
        return "whether the AI Automation opportunity is ready for a funded architecture workshop"
    if "exit renewal recovery" in lower or "exit criteria" in lower:
        return "whether the account has met the evidence required to exit renewal recovery"
    return "whether the full renewal value should remain in the forecast"


def _isv_snippet(text: str, terms: tuple[str, ...], max_len: int = 360) -> str:
    normalized = " ".join(text.split())
    lower = normalized.casefold()
    positions = [lower.find(term.casefold()) for term in terms if lower.find(term.casefold()) >= 0]
    start = max(min(positions) - 80, 0) if positions else 0
    excerpt = normalized[start : start + max_len].strip()
    return excerpt + ("..." if len(normalized) > start + max_len else "")


def _retrieve_search_knowledge_base(
    *,
    endpoint: str,
    knowledge_base: str,
    api_version: str,
    question: str,
) -> tuple[str, list[dict[str, Any]]]:
    import httpx
    from azure.identity import DefaultAzureCredential

    token = DefaultAzureCredential().get_token("https://search.azure.com/.default").token
    url = (
        f"{endpoint.rstrip('/')}/knowledgebases/{knowledge_base}/retrieve"
        f"?api-version={api_version}"
    )
    with httpx.Client(timeout=90) as client:
        response = client.post(
            url,
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": question}],
                    }
                ]
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        payload = response.json()
    answer = "".join(
        str(part.get("text") or "")
        for message in payload.get("response", [])
        for part in message.get("content", [])
        if part.get("type") == "text"
    )
    references = [
        reference
        for reference in payload.get("references", [])
        if isinstance(reference, dict)
    ]
    return answer, references


def _reference_title(reference: dict[str, Any], fallback: str) -> str:
    if reference.get("title"):
        return str(reference["title"])
    raw_url = str(reference.get("url") or reference.get("blobUrl") or "")
    if not raw_url:
        return fallback
    return raw_url.rstrip("/").split("/")[-1].rsplit(".", 1)[0].replace("_", " ")


def _reference_snippet(reference: dict[str, Any], answer: str) -> str:
    return str(reference.get("content") or reference.get("snippet") or answer)[:500]


def _select_reference(
    references: list[dict[str, Any]],
    used: set[int],
    terms: tuple[str, ...],
) -> dict[str, Any]:
    for index, reference in enumerate(references):
        if index in used:
            continue
        haystack = " ".join(
            str(reference.get(key) or "")
            for key in ("title", "url", "blobUrl")
        ).casefold()
        if any(term.casefold() in haystack for term in terms):
            used.add(index)
            return reference
    for index, reference in enumerate(references):
        if index not in used:
            used.add(index)
            return reference
    raise RuntimeError("No unused grounded reference is available.")


def _isv_answer_sentence(answer: str, terms: tuple[str, ...]) -> str:
    clean = re.sub(r"\[ref_id:\d+\]", "", answer)
    for sentence in re.split(r"(?<=[.!?])\s+", clean):
        if any(term.casefold() in sentence.casefold() for term in terms):
            return sentence.strip()[:500]
    return clean.strip()[:500]


def _isv_reference_link(reference: dict[str, Any]) -> str | None:
    blob_url = str(reference.get("blobUrl") or "")
    if blob_url:
        name = blob_url.rstrip("/").split("/")[-1]
        if name.endswith(".md"):
            return evidence_doc_url("isv_foundry_docs", name)
    url = reference.get("url")
    return str(url) if url else None
