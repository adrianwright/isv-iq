from __future__ import annotations

import base64
import os

import pytest

os.environ.setdefault("FABRIC_TOKEN", "test-token")
os.environ.setdefault("STORAGE_TOKEN", "test-token")
os.environ.setdefault("FABRIC_WS", "test-workspace")
os.environ.setdefault("FABRIC_LH", "test-lakehouse")
os.environ.setdefault("ONTOLOGY_NAME", "test-ontology")
os.environ.setdefault("DATA_AGENT_NAME", "test-data-agent")

import provision_fabric_ontology as ontology


def _decode_parts(definition: dict) -> dict[str, str]:
    return {
        part["path"]: base64.b64decode(part["payload"]).decode("utf-8")
        for part in definition["definition"]["parts"]
    }


def _schema(table: str) -> list[tuple[str, str]]:
    spec = next(item for item in ontology.ENTITIES.values() if item.table == table)
    return [(column, "string") for column in spec.props]


def test_builds_generation_two_tmdl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ontology, "ONLY_ENTITY", None)
    monkeypatch.setattr(ontology, "delta_schema", _schema)
    monkeypatch.setattr(
        ontology,
        "_lakehouse_sql_endpoint",
        lambda: ("example.datawarehouse.fabric.microsoft.com", "sql-endpoint-id"),
    )

    parts = _decode_parts(ontology.build_definition())

    assert "definition.json" not in parts
    assert sum(path.startswith("tables/") for path in parts) == len(ontology.ENTITIES)
    assert sum(path.startswith("entities/") for path in parts) == len(ontology.ENTITIES)
    assert parts["relationships.tmdl"].count("\nrelationship ") == 9
    assert parts["relationships.tmdl"].startswith("relationship ")
    assert parts["entityRelationships.tmdl"].count("\nentityRelationship ") == 9
    assert parts["entityRelationships.tmdl"].startswith("entityRelationship ")
    assert "mode: directLake" in parts["tables/patient_registry.tmdl"]
    assert "backingTable: patient_registry" in parts["entities/Patient.tmdl"]
    assert "ref table patient_registry" in parts["model.tmdl"]
    assert "ref entity Patient" in parts["model.tmdl"]


def test_verify_definition_rejects_silent_empty_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        status_code = 200
        headers: dict[str, str] = {}
        text = "{}"

        @staticmethod
        def json() -> dict:
            return {
                "definition": {
                    "parts": [
                        {"path": ".platform"},
                        {"path": "database.tmdl"},
                        {"path": "model.tmdl"},
                        {"path": "namespaces/default.tmdl"},
                    ]
                }
            }

        @staticmethod
        def raise_for_status() -> None:
            return None

    monkeypatch.setattr(ontology, "_request", lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.setattr(ontology, "ONT", "test-ontology-id")

    with pytest.raises(RuntimeError, match="did not persist required TMDL parts"):
        ontology.verify_definition({"Patient"})
