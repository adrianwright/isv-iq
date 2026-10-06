"""Provision the REAL Fabric IQ Ontology for the AMC IQ proof-of-concept (no GUI, pure REST).

The Fabric IQ Ontology is a first-class Fabric item (type "Ontology") in the Fabric IQ (preview)
workload. This script defines the precision-oncology domain ontology as generation 2 TMDL: Direct
Lake backing tables, typed ontology entities, model relationships, and entity relationships. It
pushes the definition through updateDefinition so the ontology is portal-visible and can be
consumed by a Fabric Data Agent (NL2Ontology).

It maps the portable contract in data/ontology/ontology.yaml onto real Fabric constructs and binds
each entity type to the corresponding Delta table in the amciq_fabric_oncology_clinical Lakehouse.

Synthetic data only. No PHI. Not clinical decision support.

Environment:
  FABRIC_TOKEN   token for https://api.fabric.microsoft.com/.default (Contributor on the workspace)
  STORAGE_TOKEN  token for https://storage.azure.com/.default (to read Delta schemas from OneLake)
  FABRIC_WS      workspace id       (required)
  FABRIC_LH      lakehouse id       (required)
  ONTOLOGY_ID    existing ontology item id (optional; otherwise looked up/created by name)
  ONLY_ENTITY    optional: build just one entity type (validation mode)
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import uuid

import requests
from live_environment import required_environment

FABRIC = "https://api.fabric.microsoft.com/v1"
ONELAKE = "https://onelake.dfs.fabric.microsoft.com"

WS = required_environment("FABRIC_WS")
LH = required_environment("FABRIC_LH")
ONTOLOGY_NAME = required_environment("ONTOLOGY_NAME")
DATA_AGENT_NAME = required_environment("DATA_AGENT_NAME")
FABRIC_TOKEN = required_environment("FABRIC_TOKEN")
STORAGE_TOKEN = required_environment("STORAGE_TOKEN")
# ONTOLOGY_ID may be provided to target an existing item; otherwise it is created/looked up by name.
ONT = os.environ.get("ONTOLOGY_ID", "")
ONLY_ENTITY = os.environ.get("ONLY_ENTITY")

TMDL_TYPE_MAP = {
    "string": "string",
    "integer": "int64",
    "long": "int64",
    "short": "int64",
    "byte": "int64",
    "double": "double",
    "float": "double",
    "decimal": "double",
    "boolean": "boolean",
    "date": "dateTime",
    "timestamp": "dateTime",
}

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

from dataclasses import dataclass


@dataclass(frozen=True)
class EntitySpec:
    table: str
    keys: tuple[str, ...]      # columns that together uniquely identify an instance
    display: str               # column used as the human-readable node label
    description: str           # entity-type description (semanticEnrichment) for AI agents / NL2Ontology
    synonyms: tuple[str, ...]  # entity-type synonyms (semanticEnrichment)
    props: dict[str, str]      # column -> property description (semanticEnrichment)


@dataclass(frozen=True)
class RelSpec:
    name: str
    src: str
    tgt: str
    table: str                       # relationship (fact/dimension) table carrying both keys
    src_map: dict[str, str]          # rel-table column -> source entity key column
    tgt_map: dict[str, str]          # rel-table column -> target entity key column


# Entity type -> spec. `description` and `props` become TMDL documentation comments surfaced to
# ontology consumers. Generation 2 currently accepts one keyProperty, so composite contracts use
# their final, most-specific key component.
ENTITIES: dict[str, EntitySpec] = {
    "Patient": EntitySpec(
        "patient_registry", ("patient_id",), "display_name",
        "An oncology patient in the AMC IQ precision-oncology cohort, with demographics, diagnosis, "
        "stage, ECOG performance status, care-team owners, and the scenario eligibility archetype. The root of the "
        "clinical-trial eligibility graph.",
        ("subject", "case", "individual"),
        {
            "patient_id": "Unique patient identifier, for example PT-1042. Entity key.",
            "mrn": "Medical record number.",
            "display_name": "Patient display name, used as the graph node label.",
            "sex": "Biological sex.",
            "age": "Patient age in years.",
            "ecog_ps": "ECOG performance status (0-4); lower is better function. Compared against a trial's ecog_max.",
            "primary_diagnosis": "Primary cancer diagnosis in clinical text.",
            "diagnosis_icd10": "ICD-10 code for the primary diagnosis.",
            "cancer_type": "Normalized cancer type (for example NSCLC) used for trial matching.",
            "stage": "Cancer stage at the staging date.",
            "staging_date": "Date the cancer stage was assigned.",
            "treating_oncologist_id": "person_id of the treating oncologist / principal investigator.",
            "coordinator_id": "person_id of the trial coordinator who owns this patient's screening tasks.",
            "archetype": "Scenario eligibility archetype: clear_eligible, borderline, hard_excluded, biomarker_mismatch, or treatment_naive_hold.",
        },
    ),
    "Trial": EntitySpec(
        "trials", ("trial_id",), "short_title",
        "A clinical trial the cancer center can screen patients for, including its condition, phase, status, "
        "site, and structured eligibility thresholds (maximum ECOG, minimum CrCl, required biomarker).",
        ("study", "clinical trial", "protocol"),
        {
            "trial_id": "Unique trial identifier, for example NCT99004324. Entity key.",
            "short_title": "Short human-readable trial title, used as the graph node label.",
            "condition": "Condition or indication the trial targets.",
            "cancer_type": "Cancer type the trial enrolls (for example NSCLC; Solid tumor matches any).",
            "phase": "Clinical trial phase.",
            "status": "Trial operational status, for example Open or Recruiting.",
            "site_id": "site_id where the trial runs.",
            "ecog_max": "Maximum ECOG performance status allowed for eligibility.",
            "crcl_min": "Minimum required creatinine clearance (CrCl_CKD-EPI, mL/min) for eligibility.",
            "biomarker_required": "Biomarker required for inclusion, for example EGFR exon 20 insertion.",
            "latest_protocol": "Latest protocol or amendment version in effect.",
        },
    ),
    "Criterion": EntitySpec(
        "trial_criteria", ("trial_id", "criterion_id"), "criterion_id",
        "A single inclusion or exclusion eligibility criterion of a trial, expressed as a structured rule "
        "(references_entity, param, comparator, value) so eligibility is a relationship traversal, not free text.",
        ("eligibility criterion", "requirement", "rule"),
        {
            "trial_id": "Trial this criterion belongs to. Part of the entity key.",
            "criterion_id": "Unique criterion identifier within the trial. Node label and part of the key.",
            "kind": "Whether this is an inclusion or an exclusion criterion.",
            "category": "Clinical category: diagnosis, biomarker, performance, renal, prior_therapy, hepatic, hematologic, or consent.",
            "description": "Human-readable statement of the criterion.",
            "references_entity": "The fact entity the criterion evaluates (Lab, Biomarker, Treatment, or Patient); enables relationship-aware matching.",
            "param": "The specific attribute evaluated, for example CrCl_CKD-EPI, ecog_ps, or drug_class.",
            "comparator": "Comparison operator, for example >=, <=, ==, present, or absent.",
            "value": "Threshold or required value the parameter is compared against.",
        },
    ),
    "Biomarker": EntitySpec(
        "biomarkers", ("patient_id", "marker"), "marker",
        "A tested molecular marker or variant for a patient (for example EGFR exon 20 insertion), with its gene, "
        "category, detection status, and assay method.",
        ("variant", "molecular marker", "mutation"),
        {
            "patient_id": "Patient this marker was tested for. Part of the key.",
            "marker": "Marker or variant name, for example EGFR exon 20 insertion. Node label and part of the key.",
            "gene": "Gene the marker relates to.",
            "category": "Marker category, for example mutation, amplification, or fusion.",
            "status": "Detection status, for example Detected, Not detected, Positive, Negative, or Amplified.",
            "method": "Assay method, for example NGS.",
            "assessed_date": "Date the marker was assessed.",
        },
    ),
    "Lab": EntitySpec(
        "labs", ("patient_id",), "lab_type",
        "A longitudinal laboratory result for a patient. CrCl_CKD-EPI is renal function in mL/min and drives the "
        "renal eligibility criterion; each row carries a value, unit, reference range, and collection date.",
        ("lab result", "laboratory value", "test result"),
        {
            "patient_id": "Patient the lab result belongs to. Entity key.",
            "lab_date": "Collection date of the result.",
            "lab_type": "Lab analyte, for example CrCl_CKD-EPI for renal function. Node label.",
            "value": "Numeric result value.",
            "unit": "Unit of the value, for example mL/min.",
            "ref_low": "Lower bound of the reference range.",
            "ref_high": "Upper bound of the reference range.",
        },
    ),
    "Treatment": EntitySpec(
        "treatment_history", ("patient_id",), "drug_name",
        "A prior or ongoing line of anticancer therapy for a patient, with the drug, drug class, line number, "
        "dates, cycles, and best response. Drug class drives prior-therapy exclusion matching.",
        ("therapy", "regimen", "prior therapy"),
        {
            "patient_id": "Patient who received the therapy. Entity key.",
            "drug_name": "Drug name. Node label.",
            "drug_class": "Drug class, for example platinum doublet, used for prior-therapy exclusion matching.",
            "line": "Line of therapy (1 = first line).",
            "start_date": "Date therapy started.",
            "end_date": "Date therapy ended.",
            "cycles_completed": "Number of treatment cycles completed.",
            "best_response": "Best response achieved, RECIST-style.",
            "reason_stopped": "Reason the therapy was stopped.",
        },
    ),
    "Amendment": EntitySpec(
        "amendments", ("trial_id", "amendment_id"), "label",
        "A protocol amendment that revises a trial's criteria (for example softening a prior-therapy exclusion), "
        "with its effective date and the criterion it modifies.",
        ("protocol amendment", "revision"),
        {
            "trial_id": "Trial the amendment applies to. Part of the key.",
            "amendment_id": "Unique amendment identifier within the trial. Part of the key.",
            "label": "Amendment label, for example Amendment 2. Node label.",
            "effective_date": "Date the amendment took effect.",
            "modifies_criterion_id": "criterion_id of the criterion this amendment revises.",
            "summary": "Summary of what the amendment changes.",
        },
    ),
    "Enrollment": EntitySpec(
        "trial_enrollment", ("patient_id", "trial_id"), "status",
        "The screening and enrollment relationship between a patient and a trial, capturing screening status, "
        "date, and coordinator notes.",
        ("screening", "enrollment record"),
        {
            "patient_id": "Patient in the screening relationship. Part of the key.",
            "trial_id": "Trial in the screening relationship. Part of the key.",
            "status": "Screening or enrollment status: Pre-screening, Screening, Not enrolled, or Enrolled. Node label.",
            "screening_date": "Date of the screening activity.",
            "coordinator_id": "person_id of the coordinator who owns this screening.",
            "notes": "Coordinator notes on the screening.",
        },
    ),
    "Person": EntitySpec(
        "people", ("person_id",), "display_name",
        "A member of the care team (principal investigator, coordinator, or navigator) associated with a site.",
        ("care team member", "staff", "clinician"),
        {
            "person_id": "Unique person identifier. Entity key.",
            "display_name": "Person's name. Node label.",
            "role": "Care-team role, for example Principal Investigator, Coordinator, or Navigator.",
            "site_id": "site_id where the person works.",
        },
    ),
    "Site": EntitySpec(
        "sites", ("site_id",), "display_name",
        "A clinical research site where trials run and care-team members work.",
        ("location", "center", "facility"),
        {
            "site_id": "Unique site identifier. Entity key.",
            "display_name": "Site name. Node label.",
            "short_name": "Short site code.",
        },
    ),
}

# Relationship types with contextualizations: each relationship is bound to the table that carries
# both endpoints' keys, so the graph materializes real edges (Patient-has-Lab, Trial-requires-
# Criterion, ...) rather than dangling relationship types. Mirrors data/ontology/ontology.yaml.
RELATIONSHIPS: list[RelSpec] = [
    RelSpec("has_biomarker", "Patient", "Biomarker", "biomarkers",
            {"patient_id": "patient_id"}, {"patient_id": "patient_id", "marker": "marker"}),
    RelSpec("has_lab", "Patient", "Lab", "labs",
            {"patient_id": "patient_id"}, {"patient_id": "patient_id"}),
    RelSpec("on_treatment", "Patient", "Treatment", "treatment_history",
            {"patient_id": "patient_id"}, {"patient_id": "patient_id"}),
    RelSpec("screened_for", "Patient", "Trial", "trial_enrollment",
            {"patient_id": "patient_id"}, {"trial_id": "trial_id"}),
    RelSpec("requires_criterion", "Trial", "Criterion", "trial_criteria",
            {"trial_id": "trial_id"}, {"trial_id": "trial_id", "criterion_id": "criterion_id"}),
    RelSpec("has_amendment", "Trial", "Amendment", "amendments",
            {"trial_id": "trial_id"}, {"trial_id": "trial_id", "amendment_id": "amendment_id"}),
    RelSpec("amendment_modifies", "Amendment", "Criterion", "amendments",
            {"trial_id": "trial_id", "amendment_id": "amendment_id"}, {"trial_id": "trial_id", "modifies_criterion_id": "criterion_id"}),
    RelSpec("treated_by", "Patient", "Person", "patient_registry",
            {"patient_id": "patient_id"}, {"treating_oncologist_id": "person_id"}),
    RelSpec("trial_at_site", "Trial", "Site", "trials",
            {"trial_id": "trial_id"}, {"site_id": "site_id"}),
]


def _det_guid(*parts: str) -> str:
    return str(uuid.UUID(hashlib.sha256("::".join(parts).encode()).hexdigest()[:32]))


def _b64(value: object) -> str:
    raw = value if isinstance(value, str) else json.dumps(value, separators=(",", ":"))
    return base64.b64encode(raw.encode()).decode()


def _part(path: str, value: object) -> dict[str, str]:
    return {"path": path, "payload": _b64(value), "payloadType": "InlineBase64"}


def _description(value: str) -> str:
    return "\n".join(f"/// {line.strip()}" for line in value.splitlines() if line.strip())


def _request(method: str, url: str, **kwargs) -> requests.Response:
    for attempt in range(5):
        try:
            response = requests.request(method, url, timeout=60, **kwargs)
            if response.status_code not in RETRYABLE_STATUS_CODES:
                return response
        except requests.RequestException:
            if attempt == 4:
                raise
        time.sleep(min(2**attempt, 16))
    return response


def _lakehouse_sql_endpoint() -> tuple[str, str]:
    h = {"Authorization": "Bearer " + FABRIC_TOKEN}
    url = f"{FABRIC}/workspaces/{WS}/lakehouses/{LH}"
    response = _request("GET", url, headers=h)
    response.raise_for_status()
    properties = response.json().get("properties", {}).get("sqlEndpointProperties", {})
    host = properties.get("connectionString")
    database = properties.get("id")
    if not host or not database or properties.get("provisioningStatus") != "Success":
        raise RuntimeError(f"Lakehouse SQL endpoint is unavailable: {properties}")
    return host, database


def delta_schema(table: str) -> list[tuple[str, str]]:
    """Return [(column, delta_type)] from the latest Delta log commit for a table."""
    base = f"{ONELAKE}/{WS}/{LH}/Tables/{table}/_delta_log"
    h = {"Authorization": f"Bearer {STORAGE_TOKEN}"}
    listing = _request("GET", f"{base}?recursive=false&resource=filesystem", headers=h)
    listing.raise_for_status()
    commits = sorted(
        p["name"].split("/")[-1]
        for p in listing.json().get("paths", [])
        if p["name"].endswith(".json")
    )
    schema: list[tuple[str, str]] = []
    for commit in commits:  # later commits override earlier metaData
        raw = _request("GET", f"{base}/{commit}", headers=h)
        raw.raise_for_status()
        for line in raw.content.decode("utf-8").split("\n"):
            if '"metaData"' not in line:
                continue
            meta = json.loads(line)["metaData"]
            fields = json.loads(meta["schemaString"])["fields"]
            schema = [(f["name"], str(f["type"])) for f in fields]
    return schema


def _table_tmdl(table: str, columns: list[tuple[str, str]]) -> str:
    lines = [f"table {table}", f"\tlineageTag: {_det_guid('table', table)}", ""]
    for column, delta_type in columns:
        lines.extend(
            [
                f"\tcolumn {column}",
                f"\t\tdataType: {TMDL_TYPE_MAP.get(delta_type.lower(), 'string')}",
                f"\t\tlineageTag: {_det_guid('column', table, column)}",
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


def _entity_tmdl(entity: str, spec: EntitySpec, columns: list[tuple[str, str]]) -> str:
    column_names = {column for column, _ in columns}
    keys = [key for key in spec.keys if key in column_names]
    if not keys:
        raise ValueError(f"{entity} has no available key property in {spec.table}.")
    # Generation 2 currently exposes one keyProperty. For composite contracts, the final component is
    # the most specific identifier (criterion_id, marker, amendment_id, or trial_id).
    key = keys[-1]
    lines = [
        _description(spec.description),
        f"entity {entity}",
        f"\tlineageTag: {_det_guid('entity', entity)}",
        f"\tbackingTable: {spec.table}",
        f"\tkeyProperty: {key}",
        "",
    ]
    for column, delta_type in columns:
        description = spec.props.get(column)
        if description:
            lines.append("\t" + _description(description).replace("\n", "\n\t"))
        lines.extend(
            [
                f"\tproperty {column}",
                f"\t\tdataType: {TMDL_TYPE_MAP.get(delta_type.lower(), 'string')}",
                f"\t\tlineageTag: {_det_guid('property', entity, column)}",
                "",
                "\t\tbackingConfiguration",
                f"\t\t\tvalueColumn: {spec.table}.{column}",
                "",
            ]
        )
    return "\n".join(lines)


def _relationship_parts(
    selected_entities: dict[str, EntitySpec],
) -> tuple[str, str, list[str], list[str]]:
    model_relationships: list[str] = []
    entity_relationships: list[str] = []
    relationship_names: list[str] = []
    entity_relationship_names: list[str] = []

    def add(
        name: str,
        source_entity: str,
        target_entity: str,
        source_column: str,
        target_column: str,
        *,
        one_to_many: bool = False,
    ) -> None:
        relationship_name = f"rel_{name}"
        source_table = selected_entities[source_entity].table
        target_table = selected_entities[target_entity].table
        model_relationships.extend(
            [
                f"relationship {relationship_name}",
                f"\tfromColumn: {source_table}.{source_column}",
                f"\ttoColumn: {target_table}.{target_column}",
            ]
        )
        if one_to_many:
            model_relationships.extend(["\tfromCardinality: one", "\ttoCardinality: many"])
        model_relationships.append("")
        entity_relationships.extend(
            [
                f"entityRelationship {name}",
                f"\tlineageTag: {_det_guid('entity-relationship', name)}",
                f"\tfromEntity: {source_entity}",
                f"\ttoEntity: {target_entity}",
                "",
                "\tbackingConfiguration",
                f"\t\trelationship: {relationship_name}",
                "",
            ]
        )
        relationship_names.append(relationship_name)
        entity_relationship_names.append(name)

    for relationship in RELATIONSHIPS:
        if relationship.src not in selected_entities or relationship.tgt not in selected_entities:
            continue
        source_spec = selected_entities[relationship.src]
        target_spec = selected_entities[relationship.tgt]
        if relationship.table == source_spec.table:
            source_column, target_key = list(relationship.tgt_map.items())[-1]
            add(
                relationship.name,
                relationship.src,
                relationship.tgt,
                source_column,
                target_key,
            )
        elif relationship.table == target_spec.table:
            target_column, source_key = list(relationship.src_map.items())[-1]
            add(
                relationship.name,
                relationship.src,
                relationship.tgt,
                source_key,
                target_column,
                one_to_many=True,
            )
        elif relationship.table == ENTITIES["Enrollment"].table:
            # Generation 2 model relationships are table-to-table. Represent the many-to-many
            # Patient/Trial screening edge through the existing Enrollment entity.
            add(
                "has_enrollment",
                "Patient",
                "Enrollment",
                "patient_id",
                "patient_id",
                one_to_many=True,
            )
            add(
                "enrollment_for_trial",
                "Enrollment",
                "Trial",
                "trial_id",
                "trial_id",
            )

    return (
        "\n".join(model_relationships),
        "\n".join(entity_relationships),
        relationship_names,
        entity_relationship_names,
    )


def build_definition() -> dict:
    description = (
        "AMC IQ precision-oncology domain ontology for clinical-trial readiness: patients, trials, "
        "criteria, biomarkers, labs, treatments, and care-team workflow."
    )
    items = list(ENTITIES.items())
    if ONLY_ENTITY:
        items = [(ONLY_ENTITY, ENTITIES[ONLY_ENTITY])]
    selected_entities = dict(items)
    schemas = {entity: delta_schema(spec.table) for entity, spec in items}
    sql_host, sql_database = _lakehouse_sql_endpoint()
    relationship_tmdl = ""
    entity_relationship_tmdl = ""
    relationship_names: list[str] = []
    entity_relationship_names: list[str] = []
    if not ONLY_ENTITY:
        (
            relationship_tmdl,
            entity_relationship_tmdl,
            relationship_names,
            entity_relationship_names,
        ) = _relationship_parts(selected_entities)

    platform = {
        "$schema": (
            "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/"
            "platformProperties/2.0.0/schema.json"
        ),
        "metadata": {
            "type": "Ontology",
            "displayName": ONTOLOGY_NAME,
            "description": description,
        },
        "config": {
            "version": "2.0",
            "logicalId": "00000000-0000-0000-0000-000000000000",
        },
    }
    parts = [
        _part(".platform", platform),
        _part("database.tmdl", f"{_description(description)}\ndatabase\n\tcompatibilityLevel: 1000000\n"),
        _part(
            "expressions.tmdl",
            (
                "expression DatabaseQuery =\n"
                "\t\tlet\n"
                f'\t\t    database = Sql.Database("{sql_host}", "{sql_database}")\n'
                "\t\tin\n"
                "\t\t    database\n"
                f"\tlineageTag: {_det_guid('expression', 'DatabaseQuery')}\n"
            ),
        ),
        _part(
            "namespaces/default.tmdl",
            "namespace default\n\tlineageTag: default\n",
        ),
    ]
    for entity, spec in items:
        parts.append(_part(f"tables/{spec.table}.tmdl", _table_tmdl(spec.table, schemas[entity])))
        parts.append(_part(f"entities/{entity}.tmdl", _entity_tmdl(entity, spec, schemas[entity])))

    if relationship_tmdl:
        parts.append(_part("relationships.tmdl", relationship_tmdl))
    if entity_relationship_tmdl:
        parts.append(_part("entityRelationships.tmdl", entity_relationship_tmdl))

    model_lines = ["model Model", ""]
    model_lines.extend(f"ref table {spec.table}" for _, spec in items)
    model_lines.extend(f"ref entity {entity}" for entity, _ in items)
    model_lines.extend(f"ref relationship {name}" for name in relationship_names)
    model_lines.extend(f"ref entityRelationship {name}" for name in entity_relationship_names)
    model_lines.extend(["ref expression DatabaseQuery", "ref namespace default", ""])
    parts.append(_part("model.tmdl", "\n".join(model_lines)))
    return {"definition": {"parts": parts}}


def update_definition(definition: dict) -> None:
    url = f"{FABRIC}/workspaces/{WS}/ontologies/{ONT}/updateDefinition?updateMetadata=true"
    h = {"Authorization": f"Bearer {FABRIC_TOKEN}", "Content-Type": "application/json"}
    r = _request("POST", url, headers=h, json=definition)
    print(f"updateDefinition HTTP {r.status_code}")
    if r.status_code == 202:
        op = r.headers.get("Location")
        print(f"  polling {op}")
        _poll(op)
    elif r.status_code not in (200, 201):
        print(f"  ERROR body: {r.text[:2000]}")
        r.raise_for_status()
    else:
        print("  applied synchronously")


def verify_definition(expected_entities: set[str]) -> None:
    h = {"Authorization": "Bearer " + FABRIC_TOKEN, "Content-Type": "application/json"}
    url = f"{FABRIC}/workspaces/{WS}/ontologies/{ONT}/getDefinition"
    response = _request("POST", url, headers=h, json={})
    if response.status_code == 202:
        operation_url = response.headers.get("Location")
        if not operation_url:
            raise RuntimeError("Ontology getDefinition returned 202 without a Location header.")
        for _ in range(30):
            time.sleep(4)
            operation = _request("GET", operation_url, headers=h)
            operation.raise_for_status()
            payload = operation.json()
            if payload.get("status") in ("Succeeded", "Completed"):
                resource_url = payload.get("resourceLocation")
                if not resource_url:
                    raise RuntimeError("Ontology getDefinition completed without a resourceLocation.")
                response = _request("GET", resource_url, headers=h)
                break
            if payload.get("status") == "Failed":
                raise RuntimeError(f"Ontology getDefinition failed: {operation.text[:2000]}")
        else:
            raise RuntimeError("Ontology getDefinition timed out.")
    response.raise_for_status()
    paths = {
        part.get("path")
        for part in response.json().get("definition", {}).get("parts", [])
        if part.get("path")
    }
    expected_paths = {
        f"entities/{entity}.tmdl" for entity in expected_entities
    } | {
        f"tables/{ENTITIES[entity].table}.tmdl" for entity in expected_entities
    }
    missing = sorted(expected_paths - paths)
    if missing:
        raise RuntimeError(
            "Fabric accepted the ontology update but did not persist required TMDL parts: "
            + ", ".join(missing)
        )
    if len(expected_entities) > 1:
        relationship_parts = {"relationships.tmdl", "entityRelationships.tmdl"}
        missing_relationships = sorted(relationship_parts - paths)
        if missing_relationships:
            raise RuntimeError(
                "Fabric did not persist ontology relationship parts: "
                + ", ".join(missing_relationships)
            )
    print(
        f"  verified: {len(expected_entities)} entities, "
        f"{len(expected_entities)} Direct Lake tables"
    )


def _poll(op_url: str | None) -> None:
    if not op_url:
        return
    h = {"Authorization": f"Bearer {FABRIC_TOKEN}"}
    for _ in range(30):
        time.sleep(4)
        r = _request("GET", op_url, headers=h)
        if not r.headers.get("content-type", "").startswith("application/json"):
            continue
        status = r.json().get("status")
        if status in ("Succeeded", "Completed"):
            print("  -> succeeded")
            return
        if status == "Failed":
            print(f"  -> FAILED: {r.text[:2000]}")
            raise SystemExit(1)
    print("  -> timeout")


def _lro_wait(resp: requests.Response) -> None:
    if resp.status_code == 202:
        _poll(resp.headers.get("Location"))


def get_or_create_ontology() -> str:
    """Return the ontology item id, creating the item (by name) if it does not exist."""
    h = {"Authorization": f"Bearer {FABRIC_TOKEN}", "Content-Type": "application/json"}
    base = f"{FABRIC}/workspaces/{WS}/ontologies"
    existing = _request("GET", base, headers=h).json().get("value", [])
    for o in existing:
        if o.get("displayName") == ONTOLOGY_NAME:
            print(f"  ontology exists: {ONTOLOGY_NAME} ({o['id']})")
            return o["id"]
    body = {"displayName": ONTOLOGY_NAME, "description": "AMC IQ precision-oncology domain ontology for clinical-trial readiness: patients, trials, criteria, biomarkers, labs, treatments, and care-team workflow."}
    r = _request("POST", base, headers=h, json=body)
    _lro_wait(r)
    for _ in range(15):
        time.sleep(3)
        for o in _request("GET", base, headers=h).json().get("value", []):
            if o.get("displayName") == ONTOLOGY_NAME:
                print(f"  ontology created: {ONTOLOGY_NAME} ({o['id']})")
                return o["id"]
    raise SystemExit("Ontology item did not appear after creation.")


def attach_to_data_agent() -> None:
    """Attach the ontology as a FabricItem datasource to the published Data Agent and publish."""
    h = {"Authorization": f"Bearer {FABRIC_TOKEN}", "Content-Type": "application/json"}
    items = _request("GET", f"{FABRIC}/workspaces/{WS}/items", headers=h).json().get("value", [])
    da = next((i for i in items if i.get("type") == "DataAgent" and i.get("displayName") == DATA_AGENT_NAME), None)
    if not da:
        print(f"  Data Agent '{DATA_AGENT_NAME}' not found; skipping attach.")
        return
    b = f"{FABRIC}/workspaces/{WS}/dataAgents/{da['id']}"
    sources = _request("GET", f"{b}/staging/datasources", headers=h).json().get("value", [])
    if any(s.get("id") == ONT for s in sources):
        print("  ontology already attached to Data Agent.")
    else:
        body = {"type": "FabricItem", "itemReference": {"referenceType": "ById", "itemId": ONT, "workspaceId": WS}}
        _lro_wait(_request("POST", f"{b}/staging/datasources", headers=h, json=body))
        print("  ontology attached to Data Agent as FabricItem datasource.")
    # Add the documented group-by GQL instruction and (re)publish.
    instr = (
        "You answer questions about oncology patients and clinical trial operations using "
        f"the {ONTOLOGY_NAME} Fabric IQ Ontology (entity types Patient, Trial, Criterion, Biomarker, "
        "Lab, Treatment, Amendment, Enrollment, Person, Site and their relationships) for "
        "relationship-aware questions, and the Lakehouse tables for direct structured lookups. "
        "CrCl_CKD-EPI in labs is renal function in mL/min. Patient IDs look like PT-1042; trial IDs "
        "like NCT99004324. Give precise values with dates. Support group by in GQL. Do not give medical advice."
    )
    try:
        _request("PATCH", f"{b}/staging/settings", headers=h, json={"aiInstructions": instr})
    except Exception as exc:  # noqa: BLE001
        print(f"  (settings patch skipped: {exc})")
    _lro_wait(
        _request(
            "POST",
            f"{b}/staging/publish",
            headers=h,
            json={
                "publishedDescription": (
                    "AMC IQ Fabric Data Agent: Lakehouse + Fabric IQ Ontology (NL2Ontology)"
                )
            },
        )
    )
    print("  Data Agent published with ontology source.")


def main() -> None:
    global ONT
    if not ONT:
        ONT = get_or_create_ontology()
    print(f"Building ontology definition for {ONT} (only={ONLY_ENTITY or 'ALL'})")
    definition = build_definition()
    print(f"  parts: {len(definition['definition']['parts'])}")
    update_definition(definition)
    expected_entities = {ONLY_ENTITY} if ONLY_ENTITY else set(ENTITIES)
    verify_definition(expected_entities)
    # Keep the Ontology source detached while its system-owned child GraphModel is empty. The
    # supported standalone GraphModel is provisioned and attached by provision_fabric_graph.py.
    if not ONLY_ENTITY and os.environ.get("ATTACH_ONTOLOGY_TO_DA"):
        attach_to_data_agent()
    print("Done.")


if __name__ == "__main__":
    main()
