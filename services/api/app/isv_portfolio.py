from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter

from app.isv_runtime import load_isv_portfolio
from app.isv_schemas import (
    Confidence,
    ISVPortfolioV1,
    PortfolioAccountV1,
    RenewalStatus,
)

_STATUS = TypeAdapter(RenewalStatus)
_CONFIDENCE = TypeAdapter(Confidence)


def build_isv_portfolio(path: Path) -> ISVPortfolioV1:
    payload = load_isv_portfolio(str(path))
    meta = payload["meta"]
    hero_account_id = str(meta["hero_account_id"])
    accounts = [
        PortfolioAccountV1(
            id=str(account["id"]),
            name=str(account["name"]),
            industry=str(account["industry"]),
            segment=str(account["segment"]),
            region=str(account["region"]),
            renewalId=str(account["renewal_id"]),
            renewalDate=str(account["renewal_date"]),
            daysToRenewal=int(account["days_to_renewal"]),
            currentArr=int(account["current_arr"]),
            forecastArr=int(account["forecast_arr"]),
            currency=str(account["currency"]),
            status=_STATUS.validate_python(account["status"]),
            confidence=_CONFIDENCE.validate_python(account["confidence"]),
            expansionArr=int(account["expansion_arr"]),
            priority=int(account["priority"]),
            primaryDriver=str(account["primary_driver"]),
            recommendedMotion=str(account["recommended_motion"]),
            hero=str(account["id"]) == hero_account_id,
        )
        for account in payload["accounts"]
    ]
    accounts.sort(key=lambda account: (account.priority, account.daysToRenewal))
    return ISVPortfolioV1(
        asOf=str(meta["as_of"]),
        totalArr=sum(account.currentArr for account in accounts),
        forecastArr=sum(account.forecastArr for account in accounts),
        expansionPipeline=sum(account.expansionArr for account in accounts),
        atRiskArr=sum(
            account.currentArr
            for account in accounts
            if account.status in {"critical", "at_risk"}
        ),
        accounts=accounts,
        disclaimer=str(meta["disclaimer"]),
    )
