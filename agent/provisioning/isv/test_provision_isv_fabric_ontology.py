from __future__ import annotations

import base64
from pathlib import Path

from provision_isv_fabric_ontology import (
    build_definition,
    infer_csv_schema,
    load_contract,
)


ROOT = Path(__file__).resolve().parents[3]
ISV_DIR = ROOT / "data" / "isv"


def _decode_parts(definition: dict) -> dict[str, str]:
    return {
        part["path"]: base64.b64decode(part["payload"]).decode("utf-8")
        for part in definition["definition"]["parts"]
    }


def test_builds_isolated_generation_two_definition() -> None:
    entities, relationships = load_contract(ISV_DIR / "ontology.yaml")
    schemas = {
        spec.table: infer_csv_schema(ISV_DIR / "fabric" / f"{spec.table}.csv")
        for spec in entities.values()
    }

    parts = _decode_parts(
        build_definition(
            ontology_name="microsoft-iq-isv-customer-ontology",
            sql_host="example.datawarehouse.fabric.microsoft.com",
            sql_database="isv-sql-endpoint",
            entities=entities,
            relationships=relationships,
            schemas=schemas,
        )
    )

    assert "definition.json" not in parts
    assert sum(path.startswith("tables/") for path in parts) == 15
    assert sum(path.startswith("entities/") for path in parts) == 15
    assert parts["relationships.tmdl"].count("relationship rel_") == 16
    assert parts["entityRelationships.tmdl"].count("entityRelationship ") == 16
    assert "mode: directLake" in parts["tables/accounts.tmdl"]
    assert "backingTable: accounts" in parts["entities/Account.tmdl"]
    assert "fromColumn: accounts.id" in parts["relationships.tmdl"]
    assert "toColumn: renewals.account_id" in parts["relationships.tmdl"]
    assert "ref entity ExpansionCandidate" in parts["model.tmdl"]


def test_infers_fabric_types_from_generated_tables() -> None:
    schema = dict(infer_csv_schema(ISV_DIR / "fabric" / "accounts.csv"))
    assert schema["annual_recurring_revenue"] == "int64"
    assert schema["customer_since"] == "date"

    contract_schema = dict(infer_csv_schema(ISV_DIR / "fabric" / "contracts.csv"))
    assert contract_schema["service_credit_eligible"] == "boolean"
    assert contract_schema["uptime_sla_percent"] == "double"
