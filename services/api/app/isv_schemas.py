"""Versioned ISV customer-renewal contract."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas import Evidence, HumanReview, NextAction, Reviewer, SourceMapItem, TraceStep

RenewalStatus = Literal["on_track", "at_risk", "critical", "indeterminate"]
SignalStatus = Literal["positive", "watch", "negative", "unknown"]
Confidence = Literal["low", "medium", "high"]
SpecialistId = Literal["commercial", "adoption", "support", "relationship", "expansion"]


class ISVAskRequestV1(BaseModel):
    question: str = Field(min_length=1)
    accountId: str | None = None
    renewalId: str | None = None


class AccountSnapshotV1(BaseModel):
    id: str
    name: str
    industry: str
    segment: str
    region: str
    health: str
    annualRecurringRevenue: int
    currency: str
    primaryContact: str
    executiveSponsor: str


class RenewalSummaryV1(BaseModel):
    id: str
    renewalDate: str
    daysToRenewal: int
    currentArr: int
    forecastArr: int
    currency: str
    stage: str
    requestedTermMonths: int


class RenewalAssessmentV1(BaseModel):
    status: RenewalStatus
    label: str
    confidence: Confidence


class BusinessSignalV1(BaseModel):
    id: str
    category: Literal["adoption", "support", "commercial", "relationship", "expansion"]
    title: str
    status: SignalStatus
    impact: str
    evidenceRefs: list[str] = Field(default_factory=list)
    owner: str | None = None
    remediation: str | None = None


class BusinessRiskV1(BaseModel):
    id: str
    title: str
    severity: Literal["low", "medium", "high", "critical"]
    impact: str
    evidenceRefs: list[str] = Field(default_factory=list)


class ExpansionOpportunityV1(BaseModel):
    id: str
    product: str
    estimatedArr: int
    currency: str
    fit: Literal["weak", "moderate", "strong"]
    confidence: Confidence
    rationale: str
    blockers: list[str] = Field(default_factory=list)
    evidenceRefs: list[str] = Field(default_factory=list)


class SpecialistInsightV1(BaseModel):
    id: SpecialistId
    label: str
    domain: str
    status: SignalStatus
    summary: str
    recommendation: str
    evidenceRefs: list[str] = Field(default_factory=list)
    investigationLead: str | None = None


class PortfolioAccountV1(BaseModel):
    id: str
    name: str
    industry: str
    segment: str
    region: str
    renewalId: str
    renewalDate: str
    daysToRenewal: int
    currentArr: int
    forecastArr: int
    currency: str
    status: RenewalStatus
    confidence: Confidence
    expansionArr: int
    priority: int
    primaryDriver: str
    recommendedMotion: str
    hero: bool = False


class ISVPortfolioV1(BaseModel):
    schemaVersion: Literal["isv.portfolio.v1"] = "isv.portfolio.v1"
    asOf: str
    totalArr: int
    forecastArr: int
    expansionPipeline: int
    atRiskArr: int
    accounts: list[PortfolioAccountV1]
    disclaimer: str


class ISVAskResultV1(BaseModel):
    schemaVersion: Literal["isv.v1"] = "isv.v1"
    question: str
    answer: str
    answerRefs: list[str] = Field(default_factory=list)
    intent: str = "renewal_assessment"
    scope: str = ""
    bottomLine: str = ""
    account: AccountSnapshotV1
    renewal: RenewalSummaryV1
    assessment: RenewalAssessmentV1
    signals: list[BusinessSignalV1]
    risks: list[BusinessRiskV1]
    opportunities: list[ExpansionOpportunityV1]
    specialists: list[SpecialistInsightV1] = Field(default_factory=list)
    evidence: list[Evidence]
    missingData: list[str]
    nextAction: NextAction
    humanReview: HumanReview
    reviewers: list[Reviewer] = Field(default_factory=list)
    unavailableSources: list[str] = Field(default_factory=list)
    sourceMap: list[SourceMapItem]
    trace: list[TraceStep]
    agentDriven: bool = False
    mode: Literal["mock", "live"]
    disclaimer: str
