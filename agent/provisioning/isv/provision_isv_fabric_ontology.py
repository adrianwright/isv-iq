"""Provision the ISV customer-renewal Fabric IQ Ontology as generation-2 TMDL.

The script is isolated from other environments by requiring ISV-prefixed workspace and
Lakehouse settings. Importing the module performs no network or environment access, so the TMDL
definition can be validated locally before any Fabric resource is changed.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import yaml

FABRIC = "https://api.fabric.microsoft.com/v1"
ONELAKE = "https://onelake.dfs.fabric.microsoft.com"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
TMDL_TYPE_MAP = {
    "string": "string",
    "integer": "int64",
    "long": "int64",
    "short": "int64",
    "byte": "int64",
    "int64": "int64",
    "double": "double",
    "float": "double",
    "decimal": "double",
    "boolean": "boolean",
    "date": "dateTime",
    "timestamp": "dateTime",
}


@dataclass(frozen=True)
class EntitySpec:
    name: str
    table: str
    key: str
    attributes: tuple[str, ...]
    description: str


@dataclass(frozen=True)
class RelationshipSpec:
    name: str
    source: str
    target: str
    via: str


def load_contract(path: Path) -> tuple[dict[str, EntitySpec], list[RelationshipSpec]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a YAML object")

    entities = {
        name: EntitySpec(
            name=name,
            table=str(definition["collection"]),
            key=str(definition["key"]),
            attributes=tuple(map(str, definition.get("attributes", []))),
            description=str(
                definition.get(
                    "description",
                    f"{name} business entity in the customer renewal and expansion scenario.",
                )
            ),
        )
        for name, definition in payload.get("entities", {}).items()
    }
    relationships = [
        RelationshipSpec(
            name=str(item["name"]),
            source=str(item["from"]),
            target=str(item["to"]),
            via=str(item["via"]),
        )
        for item in payload.get("relationships", [])
    ]
    return entities, relationships


def infer_csv_schema(path: Path) -> list[tuple[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = list(reader)
    if not columns:
        raise ValueError(f"{path} has no CSV header")

    return [
        (column, _infer_type([row.get(column, "") for row in rows]))
        for column in columns
    ]


def _infer_type(values: list[str]) -> str:
    populated = [value.strip() for value in values if value and value.strip()]
    if not populated:
        return "string"
    lowered = {value.casefold() for value in populated}
    if lowered <= {"true", "false"}:
        return "boolean"
    if all(re.fullmatch(r"-?\d+", value) for value in populated):
        return "int64"
    if all(re.fullmatch(r"-?(?:\d+\.\d+|\d+)", value) for value in populated):
        return "double"
    if all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) for value in populated):
        return "date"
    return "string"


def _det_guid(*parts: str) -> str:
    return str(uuid.UUID(hashlib.sha256("::".join(parts).encode()).hexdigest()[:32]))


def _part(path: str, value: object) -> dict[str, str]:
    raw = value if isinstance(value, str) else json.dumps(value, separators=(",", ":"))
    return {
        "path": path,
        "payload": base64.b64encode(raw.encode()).decode(),
        "payloadType": "InlineBase64",
    }


def _description(value: str) -> str:
    return "\n".join(f"/// {line.strip()}" for line in value.splitlines() if line.strip())


def _table_tmdl(table: str, columns: list[tuple[str, str]]) -> str:
    lines = [f"table {table}", f"\tlineageTag: {_det_guid('isv-table', table)}", ""]
    for column, column_type in columns:
        lines.extend(
            [
                f"\tcolumn {column}",
                f"\t\tdataType: {TMDL_TYPE_MAP.get(column_type, 'string')}",
                f"\t\tlineageTag: {_det_guid('isv-column', table, column)}",
                f"\t\tsourceColumn: {column}",
                "",
            ]
        )
    lines.extend(
        [
            f"\tpartition {table} = entity",
            "\t\tmode: directLake",
            "\t\tsource",
            f"\t\t\tentityName: {table}",
            "\t\t\tschemaName: dbo",
            "\t\t\texpressionSource: DatabaseQuery",
            "",
        ]
    )
    return "\n".join(lines)


def _entity_tmdl(spec: EntitySpec, columns: list[tuple[str, str]]) -> str:
    column_names = {column for column, _ in columns}
    required = {spec.key, *spec.attributes}
    missing = sorted(required - column_names)
    if missing:
        raise ValueError(f"{spec.name}/{spec.table} is missing columns: {', '.join(missing)}")

    lines = [
        _description(spec.description),
        f"entity {spec.name}",
        f"\tlineageTag: {_det_guid('isv-entity', spec.name)}",
        f"\tbackingTable: {spec.table}",
        f"\tkeyProperty: {spec.key}",
        "",
    ]
    for column, column_type in columns:
        lines.extend(
            [
                f"\t/// {column.replace('_', ' ')} for the synthetic {spec.name} record.",
                f"\tproperty {column}",
                f"\t\tdataType: {TMDL_TYPE_MAP.get(column_type, 'string')}",
                f"\t\tlineageTag: {_det_guid('isv-property', spec.name, column)}",
                "",
                "\t\tbackingConfiguration",
                f"\t\t\tvalueColumn: {spec.table}.{column}",
                "",
            ]
        )
    return "\n".join(lines)


def _relationship_tmdl(
    entities: dict[str, EntitySpec],
    relationships: list[RelationshipSpec],
) -> tuple[str, str, list[str], list[str]]:
    model_lines: list[str] = []
    entity_lines: list[str] = []
    model_names: list[str] = []
    entity_names: list[str] = []

    for relation in relationships:
        source = entities[relation.source]
        target = entities[relation.target]
        relationship_name = f"rel_{relation.name}"
        if relation.via in target.attributes:
            from_column = f"{source.table}.{source.key}"
            to_column = f"{target.table}.{relation.via}"
            cardinality = ["\tfromCardinality: one", "\ttoCardinality: many"]
        elif relation.via in source.attributes:
            from_column = f"{source.table}.{relation.via}"
            to_column = f"{target.table}.{target.key}"
            cardinality = []
        else:
            raise ValueError(
                f"{relation.name} via column {relation.via!r} is not present on "
                f"{source.name} or {target.name}"
            )

        model_lines.extend(
            [
                f"relationship {relationship_name}",
                f"\tfromColumn: {from_column}",
                f"\ttoColumn: {to_column}",
                *cardinality,
                "",
            ]
        )
        entity_lines.extend(
            [
                f"entityRelationship {relation.name}",
                f"\tlineageTag: {_det_guid('isv-entity-relationship', relation.name)}",
                f"\tfromEntity: {relation.source}",
                f"\ttoEntity: {relation.target}",
                "",
                "\tbackingConfiguration",
                f"\t\trelationship: {relationship_name}",
                "",
            ]
        )
        model_names.append(relationship_name)
        entity_names.append(relation.name)

    return "\n".join(model_lines), "\n".join(entity_lines), model_names, entity_names


def build_definition(
    *,
    ontology_name: str,
    sql_host: str,
    sql_database: str,
    entities: dict[str, EntitySpec],
    relationships: list[RelationshipSpec],
    schemas: dict[str, list[tuple[str, str]]],
) -> dict[str, Any]:
    description = (
        "Microsoft IQ for ISVs customer-renewal ontology covering accounts, renewals, contracts, "
        "subscriptions, usage, support, finance, relationships, commitments, and expansion."
    )
    relationship_tmdl, entity_relationship_tmdl, relationship_names, entity_relation_names = (
        _relationship_tmdl(entities, relationships)
    )
    platform = {
        "$schema": (
            "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/"
            "platformProperties/2.0.0/schema.json"
        ),
        "metadata": {
            "type": "Ontology",
            "displayName": ontology_name,
            "description": description,
        },
        "config": {
            "version": "2.0",
            "logicalId": "00000000-0000-0000-0000-000000000000",
        },
    }
    parts = [
        _part(".platform", platform),
        _part(
            "database.tmdl",
            f"{_description(description)}\ndatabase\n\tcompatibilityLevel: 1000000\n",
        ),
        _part(
            "expressions.tmdl",
            (
                "expression DatabaseQuery =\n"
                "\t\tlet\n"
                f'\t\t    database = Sql.Database("{sql_host}", "{sql_database}")\n'
                "\t\tin\n"
                "\t\t    database\n"
                f"\tlineageTag: {_det_guid('isv-expression', 'DatabaseQuery')}\n"
            ),
        ),
        _part("namespaces/default.tmdl", "namespace default\n\tlineageTag: default\n"),
    ]
    for spec in entities.values():
        schema = schemas[spec.table]
        parts.append(_part(f"tables/{spec.table}.tmdl", _table_tmdl(spec.table, schema)))
        parts.append(_part(f"entities/{spec.name}.tmdl", _entity_tmdl(spec, schema)))
    parts.append(_part("relationships.tmdl", relationship_tmdl))
    parts.append(_part("entityRelationships.tmdl", entity_relationship_tmdl))

    model_lines = ["model Model", ""]
    model_lines.extend(f"ref table {spec.table}" for spec in entities.values())
    model_lines.extend(f"ref entity {spec.name}" for spec in entities.values())
    model_lines.extend(f"ref relationship {name}" for name in relationship_names)
    model_lines.extend(f"ref entityRelationship {name}" for name in entity_relation_names)
    model_lines.extend(["ref expression DatabaseQuery", "ref namespace default", ""])
    parts.append(_part("model.tmdl", "\n".join(model_lines)))
    return {"definition": {"parts": parts}}


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Set {name} before provisioning ISV Fabric resources.")
    return value


def _request(method: str, url: str, **kwargs: Any) -> requests.Response:
    response: requests.Response | None = None
    for attempt in range(5):
        try:
            response = requests.request(method, url, timeout=60, **kwargs)
            if response.status_code not in RETRYABLE_STATUS_CODES:
                return response
        except requests.RequestException:
            if attempt == 4:
                raise
        time.sleep(min(2**attempt, 16))
    if response is None:
        raise RuntimeError(f"No response received for {method} {url}")
    return response


def _poll(operation_url: str | None, headers: dict[str, str]) -> None:
    if not operation_url:
        return
    for _ in range(30):
        time.sleep(4)
        response = _request("GET", operation_url, headers=headers)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") in {"Succeeded", "Completed"}:
            return
        if payload.get("status") == "Failed":
            raise RuntimeError(f"Fabric operation failed: {response.text[:2000]}")
    raise TimeoutError("Fabric operation did not complete within two minutes.")


def _lakehouse_sql_endpoint(
    workspace_id: str,
    lakehouse_id: str,
    headers: dict[str, str],
) -> tuple[str, str]:
    response = _request(
        "GET",
        f"{FABRIC}/workspaces/{workspace_id}/lakehouses/{lakehouse_id}",
        headers=headers,
    )
    response.raise_for_status()
    properties = response.json().get("properties", {}).get("sqlEndpointProperties", {})
    host = properties.get("connectionString")
    database = properties.get("id")
    if not host or not database or properties.get("provisioningStatus") != "Success":
        raise RuntimeError(f"ISV Lakehouse SQL endpoint is unavailable: {properties}")
    return str(host), str(database)


def _delta_schema(
    workspace_id: str,
    lakehouse_id: str,
    table: str,
    storage_headers: dict[str, str],
) -> list[tuple[str, str]]:
    base = f"{ONELAKE}/{workspace_id}/{lakehouse_id}/Tables/{table}/_delta_log"
    listing = _request(
        "GET",
        f"{base}?recursive=false&resource=filesystem",
        headers=storage_headers,
    )
    listing.raise_for_status()
    commits = sorted(
        item["name"].split("/")[-1]
        for item in listing.json().get("paths", [])
        if item["name"].endswith(".json")
    )
    schema: list[tuple[str, str]] = []
    for commit in commits:
        response = _request("GET", f"{base}/{commit}", headers=storage_headers)
        response.raise_for_status()
        for line in response.content.decode("utf-8").splitlines():
            if '"metaData"' not in line:
                continue
            fields = json.loads(json.loads(line)["metaData"]["schemaString"])["fields"]
            schema = [(field["name"], str(field["type"]).casefold()) for field in fields]
    if not schema:
        raise RuntimeError(f"No Delta schema found for ISV table {table}.")
    return schema


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    contract_path = repo_root / "data" / "isv" / "ontology.yaml"
    workspace_id = _required_environment("ISV_FABRIC_WS")
    lakehouse_id = _required_environment("ISV_FABRIC_LH")
    ontology_name = _required_environment("ISV_ONTOLOGY_NAME")
    fabric_token = _required_environment("FABRIC_TOKEN")
    storage_token = _required_environment("STORAGE_TOKEN")
    ontology_id = os.environ.get("ISV_ONTOLOGY_ID", "").strip()
    fabric_headers = {
        "Authorization": f"Bearer {fabric_token}",
        "Content-Type": "application/json",
    }
    storage_headers = {"Authorization": f"Bearer {storage_token}"}

    entities, relationships = load_contract(contract_path)
    schemas = {
        spec.table: _delta_schema(
            workspace_id,
            lakehouse_id,
            spec.table,
            storage_headers,
        )
        for spec in entities.values()
    }
    sql_host, sql_database = _lakehouse_sql_endpoint(
        workspace_id,
        lakehouse_id,
        fabric_headers,
    )

    base = f"{FABRIC}/workspaces/{workspace_id}/ontologies"
    if not ontology_id:
        response = _request("GET", base, headers=fabric_headers)
        response.raise_for_status()
        existing = next(
            (
                item
                for item in response.json().get("value", [])
                if item.get("displayName") == ontology_name
            ),
            None,
        )
        if existing:
            ontology_id = str(existing["id"])
        else:
            response = _request(
                "POST",
                base,
                headers=fabric_headers,
                json={
                    "displayName": ontology_name,
                    "description": (
                        "ISV customer renewal and expansion ontology over synthetic data."
                    ),
                },
            )
            if response.status_code == 202:
                _poll(response.headers.get("Location"), fabric_headers)
            elif response.status_code not in {200, 201}:
                response.raise_for_status()
            for _ in range(15):
                items = _request("GET", base, headers=fabric_headers)
                items.raise_for_status()
                existing = next(
                    (
                        item
                        for item in items.json().get("value", [])
                        if item.get("displayName") == ontology_name
                    ),
                    None,
                )
                if existing:
                    ontology_id = str(existing["id"])
                    break
                time.sleep(3)
    if not ontology_id:
        raise RuntimeError(f"Ontology {ontology_name!r} did not appear after creation.")

    definition = build_definition(
        ontology_name=ontology_name,
        sql_host=sql_host,
        sql_database=sql_database,
        entities=entities,
        relationships=relationships,
        schemas=schemas,
    )
    response = _request(
        "POST",
        (
            f"{FABRIC}/workspaces/{workspace_id}/ontologies/{ontology_id}"
            "/updateDefinition?updateMetadata=true"
        ),
        headers=fabric_headers,
        json=definition,
    )
    if response.status_code == 202:
        _poll(response.headers.get("Location"), fabric_headers)
    elif response.status_code not in {200, 201}:
        response.raise_for_status()

    expected_paths = {
        *(f"entities/{spec.name}.tmdl" for spec in entities.values()),
        *(f"tables/{spec.table}.tmdl" for spec in entities.values()),
        "relationships.tmdl",
        "entityRelationships.tmdl",
    }
    response = _request(
        "POST",
        f"{FABRIC}/workspaces/{workspace_id}/ontologies/{ontology_id}/getDefinition",
        headers=fabric_headers,
        json={},
    )
    if response.status_code == 202:
        operation_url = response.headers.get("Location")
        if not operation_url:
            raise RuntimeError("Ontology getDefinition returned no operation location.")
        for _ in range(30):
            time.sleep(4)
            operation = _request("GET", operation_url, headers=fabric_headers)
            operation.raise_for_status()
            payload = operation.json()
            if payload.get("status") in {"Succeeded", "Completed"}:
                response = _request(
                    "GET",
                    str(payload["resourceLocation"]),
                    headers=fabric_headers,
                )
                break
            if payload.get("status") == "Failed":
                raise RuntimeError(f"Ontology verification failed: {operation.text[:2000]}")
        else:
            raise TimeoutError("Ontology getDefinition did not complete.")
    response.raise_for_status()
    actual_paths = {
        part.get("path")
        for part in response.json().get("definition", {}).get("parts", [])
    }
    missing = sorted(expected_paths - actual_paths)
    if missing:
        raise RuntimeError(
            "Fabric accepted but did not persist required ISV ontology parts: "
            + ", ".join(missing)
        )

    print(
        f"Provisioned ISV ontology {ontology_name} ({ontology_id}) with "
        f"{len(entities)} entities and {len(relationships)} relationships."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
