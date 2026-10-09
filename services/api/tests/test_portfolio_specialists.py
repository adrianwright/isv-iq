from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.isv_orchestrator import ISVOrchestrator
from app.isv_portfolio import build_isv_portfolio
from app.isv_schemas import ISVAskRequestV1
from app.main import app


def test_isv_portfolio_prioritizes_critical_renewal() -> None:
    settings = get_settings()
    portfolio = build_isv_portfolio(settings.DATA_DIR / "isv" / "portfolio.yaml")

    assert portfolio.schemaVersion == "isv.portfolio.v1"
    assert len(portfolio.accounts) == 5
    assert portfolio.accounts[0].name == "Northwind Unified School District"
    assert all(account.name.endswith("School District") for account in portfolio.accounts)
    assert all(account.industry == "Education" for account in portfolio.accounts)
    assert portfolio.accounts[0].status == "critical"
    assert portfolio.atRiskArr == 4_500_000
    assert portfolio.expansionPipeline == 1_500_000
    assert sum(account.hero for account in portfolio.accounts) == 1


def test_isv_portfolio_endpoint_returns_versioned_summary() -> None:
    response = TestClient(app).get("/api/isv/portfolio")

    assert response.status_code == 200
    assert response.json()["schemaVersion"] == "isv.portfolio.v1"
    assert response.json()["accounts"][0]["status"] == "critical"


def test_isv_assessment_includes_grounded_specialist_team() -> None:
    result = ISVOrchestrator().answer(
        ISVAskRequestV1(
            question="Assess the renewal and expansion path.",
            accountId="ACC-1001",
            renewalId="REN-1001",
        )
    )

    assert [specialist.id for specialist in result.specialists] == [
        "commercial",
        "adoption",
        "support",
        "relationship",
    ]
    assert all(specialist.evidenceRefs for specialist in result.specialists)
    assert any(step.step == "Support Recovery Lead assessment" for step in result.trace)


def test_phase6_contract_files_exist() -> None:
    settings = get_settings()
    assert (Path(settings.DATA_DIR) / "isv" / "portfolio.yaml").is_file()
    assert (Path(settings.DATA_DIR) / "isv" / "specialists.yaml").is_file()
