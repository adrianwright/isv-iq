"""Validate the additive ISV customer-renewal scenario package."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
ISV_DIR = ROOT / "data" / "isv"
REGISTRY_PATH = ISV_DIR / "registry.yaml"
ONTOLOGY_PATH = ISV_DIR / "ontology.yaml"
PROMPTS_PATH = ISV_DIR / "prompts.yaml"
FABRIC_DIR = ISV_DIR / "fabric"
FABRIC_MANIFEST_PATH = FABRIC_DIR / "manifest.json"
FOUNDRY_DOCS_DIR = ISV_DIR / "foundry_docs"
WORK_DIR = ISV_DIR / "work"
PORTFOLIO_PATH = ISV_DIR / "portfolio.yaml"
SPECIALISTS_PATH = ISV_DIR / "specialists.yaml"

IQ_NAMES = {"fabric", "foundry", "work", "web"}
PROMPT_CATEGORIES = {"understand", "prepare", "expand", "act"}
PROMPT_INTENTS = {
    "renewal_forecast",
    "proposal_readiness",
    "expansion_gate",
    "expansion_acceleration",
}


def _load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML object")
    return data


def _ids(registry: dict, collection: str) -> set[str]:
    return {str(item["id"]) for item in registry.get(collection, [])}


def _fabric_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    return str(value)


def validate() -> list[str]:
    problems: list[str] = []
    try:
        registry = _load(REGISTRY_PATH)
        ontology = _load(ONTOLOGY_PATH)
        prompt_catalog = _load(PROMPTS_PATH)
        portfolio = _load(PORTFOLIO_PATH)
        specialist_catalog = _load(SPECIALISTS_PATH)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return [str(exc)]

    meta = registry.get("meta", {})
    hero_account = str(meta.get("hero_account_id", ""))
    hero_renewal = str(meta.get("hero_renewal_id", ""))
    if hero_account not in _ids(registry, "accounts"):
        problems.append(f"hero account {hero_account!r} is not defined")
    if hero_renewal not in _ids(registry, "renewals"):
        problems.append(f"hero renewal {hero_renewal!r} is not defined")
    if "Synthetic" not in str(meta.get("disclaimer", "")):
        problems.append("registry disclaimer must explicitly identify synthetic data")

    portfolio_meta = portfolio.get("meta", {})
    portfolio_accounts = portfolio.get("accounts", [])
    if portfolio_meta.get("schema_version") != "isv.portfolio.v1":
        problems.append("portfolio must use schema_version isv.portfolio.v1")
    if portfolio_meta.get("hero_account_id") != hero_account:
        problems.append("portfolio hero_account_id does not match the registry")
    if "Synthetic" not in str(portfolio_meta.get("disclaimer", "")):
        problems.append("portfolio disclaimer must explicitly identify synthetic data")
    portfolio_ids = [str(account.get("id", "")) for account in portfolio_accounts]
    if len(portfolio_accounts) < 5:
        problems.append("portfolio must contain at least five accounts")
    if len(set(portfolio_ids)) != len(portfolio_ids):
        problems.append("portfolio account IDs must be unique")
    priorities = [account.get("priority") for account in portfolio_accounts]
    if len(set(priorities)) != len(priorities):
        problems.append("portfolio priorities must be unique")
    if sum(account_id == hero_account for account_id in portfolio_ids) != 1:
        problems.append("portfolio must contain the registry hero account exactly once")
    portfolio_as_of = date.fromisoformat(str(portfolio_meta.get("as_of")))
    for account in portfolio_accounts:
        account_id = account.get("id", "<unknown>")
        expected_days = (
            date.fromisoformat(str(account.get("renewal_date"))) - portfolio_as_of
        ).days
        if account.get("days_to_renewal") != expected_days:
            problems.append(
                f"portfolio.{account_id}: days_to_renewal is {account.get('days_to_renewal')}, "
                f"expected {expected_days}"
            )
        if account.get("status") not in {"on_track", "at_risk", "critical", "indeterminate"}:
            problems.append(f"portfolio.{account_id}: invalid status")
        if int(account.get("forecast_arr", 0)) < 0 or int(account.get("expansion_arr", 0)) < 0:
            problems.append(f"portfolio.{account_id}: ARR values cannot be negative")

    hero_portfolio = next(
        (account for account in portfolio_accounts if account.get("id") == hero_account),
        {},
    )
    hero_registry = next(
        (account for account in registry.get("accounts", []) if account.get("id") == hero_account),
        {},
    )
    hero_registry_renewal = next(
        (renewal for renewal in registry.get("renewals", []) if renewal.get("id") == hero_renewal),
        {},
    )
    if hero_portfolio.get("current_arr") != hero_registry.get("annual_recurring_revenue"):
        problems.append("portfolio hero ARR does not match the registry")
    if hero_portfolio.get("renewal_id") != hero_renewal:
        problems.append("portfolio hero renewal_id does not match the registry")
    if hero_portfolio.get("renewal_date") != hero_registry_renewal.get("renewal_date"):
        problems.append("portfolio hero renewal_date does not match the registry")

    expected_specialists = {
        "commercial": "commercial",
        "adoption": "adoption",
        "support": "support",
        "relationship": "relationship",
        "expansion": "expansion",
    }
    specialist_rows = specialist_catalog.get("specialists", [])
    actual_specialists = {
        str(specialist.get("id")): str(specialist.get("signal_category"))
        for specialist in specialist_rows
    }
    if specialist_catalog.get("meta", {}).get("schema_version") != "isv.specialists.v1":
        problems.append("specialists must use schema_version isv.specialists.v1")
    if actual_specialists != expected_specialists:
        problems.append("specialist roles must cover all five business-signal categories")
    for specialist in specialist_rows:
        if not str(specialist.get("label", "")).strip() or not str(
            specialist.get("domain", "")
        ).strip():
            problems.append(f"specialist {specialist.get('id')}: label and domain are required")

    all_ids: list[str] = []
    for collection, rows in registry.items():
        if collection == "meta" or not isinstance(rows, list):
            continue
        all_ids.extend(str(row.get("id", "")) for row in rows)
    duplicates = sorted(value for value, count in Counter(all_ids).items() if value and count > 1)
    if duplicates:
        problems.append(f"duplicate entity IDs: {duplicates}")

    account_ids = _ids(registry, "accounts")
    renewal_ids = _ids(registry, "renewals")
    contact_ids = _ids(registry, "contacts")
    employee_ids = _ids(registry, "employees")
    subscription_ids = _ids(registry, "subscriptions")
    support_case_ids = _ids(registry, "support_cases")
    participant_ids = contact_ids | employee_ids

    for row in registry.get("accounts", []):
        if row.get("primary_contact_id") not in contact_ids:
            problems.append(f"accounts.{row.get('id')}: dangling primary_contact_id")
        if row.get("executive_sponsor_id") not in employee_ids:
            problems.append(f"accounts.{row.get('id')}: dangling executive_sponsor_id")

    for collection in (
        "contacts",
        "account_team",
        "renewals",
        "contracts",
        "subscriptions",
        "product_usage",
        "support_cases",
        "invoices",
        "success_milestones",
        "commitments",
        "expansion_candidates",
        "interactions",
        "external_signals",
    ):
        for row in registry.get(collection, []):
            if row.get("account_id") not in account_ids:
                problems.append(f"{collection}.{row.get('id')}: dangling account_id")

    for row in registry.get("renewals", []):
        if row.get("owner_id") not in employee_ids:
            problems.append(f"renewals.{row.get('id')}: dangling owner_id")
        expected_days = (
            date.fromisoformat(str(row.get("renewal_date")))
            - date.fromisoformat(str(meta.get("scenario_today")))
        ).days
        if row.get("days_to_renewal") != expected_days:
            problems.append(
                f"renewals.{row.get('id')}: days_to_renewal is {row.get('days_to_renewal')}, "
                f"expected {expected_days}"
            )
    for row in registry.get("account_team", []):
        if row.get("employee_id") not in employee_ids:
            problems.append(f"account_team.{row.get('id')}: dangling employee_id")
    for row in registry.get("contracts", []) + registry.get("commitments", []):
        if row.get("renewal_id") not in renewal_ids:
            problems.append(f"{row.get('id')}: dangling renewal_id")
    for row in registry.get("product_usage", []):
        if row.get("subscription_id") not in subscription_ids:
            problems.append(f"product_usage.{row.get('id')}: dangling subscription_id")
    for row in registry.get("support_cases", []):
        if row.get("owner_id") not in employee_ids:
            problems.append(f"support_cases.{row.get('id')}: dangling owner_id")
    for row in registry.get("success_milestones", []):
        if row.get("owner_id") not in employee_ids:
            problems.append(f"success_milestones.{row.get('id')}: dangling owner_id")
        blocker = row.get("blocker")
        if isinstance(blocker, str) and blocker.startswith("CASE-") and blocker not in support_case_ids:
            problems.append(f"success_milestones.{row.get('id')}: dangling blocker")
    for row in registry.get("expansion_candidates", []):
        if row.get("renewal_id") not in renewal_ids:
            problems.append(f"expansion_candidates.{row.get('id')}: dangling renewal_id")
        if row.get("sponsor_contact_id") not in contact_ids:
            problems.append(f"expansion_candidates.{row.get('id')}: dangling sponsor_contact_id")
        if row.get("technical_owner_id") not in employee_ids:
            problems.append(f"expansion_candidates.{row.get('id')}: dangling technical_owner_id")
    for row in registry.get("commitments", []):
        if row.get("owner_id") not in employee_ids:
            problems.append(f"commitments.{row.get('id')}: dangling owner_id")
    for row in registry.get("interactions", []):
        unknown_participants = sorted(set(row.get("participants", [])) - participant_ids)
        if unknown_participants:
            problems.append(
                f"interactions.{row.get('id')}: unknown participants {unknown_participants}"
            )
    for row in registry.get("external_signals", []):
        parsed = urlsplit(str(row.get("source_url", "")))
        if parsed.scheme != "https" or not (parsed.hostname or "").endswith(".invalid"):
            problems.append(f"external_signals.{row.get('id')}: source_url must use HTTPS .invalid")

    entity_collections = {
        str(definition.get("collection"))
        for definition in ontology.get("entities", {}).values()
        if isinstance(definition, dict)
    }
    missing_collections = sorted(entity_collections - set(registry))
    if missing_collections:
        problems.append(f"ontology collections missing from registry: {missing_collections}")
    entity_names = set(ontology.get("entities", {}))
    for entity_name, definition in ontology.get("entities", {}).items():
        collection = str(definition.get("collection", ""))
        rows = registry.get(collection, [])
        required_fields = {str(definition.get("key", "")), *definition.get("attributes", [])}
        for row in rows:
            missing_fields = sorted(field for field in required_fields if field not in row)
            if missing_fields:
                problems.append(
                    f"ontology {entity_name}/{row.get('id')}: missing fields {missing_fields}"
                )
    for relation in ontology.get("relationships", []):
        if relation.get("from") not in entity_names or relation.get("to") not in entity_names:
            problems.append(f"ontology relationship {relation.get('name')} has an unknown entity")
    for signal in ontology.get("assessment_signals", []):
        unknown_entities = sorted(set(signal.get("evidence_entities", [])) - entity_names)
        if unknown_entities:
            problems.append(
                f"assessment signal {signal.get('id')}: unknown entities {unknown_entities}"
            )

    try:
        fabric_manifest = json.loads(FABRIC_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"invalid ISV Fabric manifest: {exc}")
        fabric_manifest = {}
    if fabric_manifest.get("schemaVersion") != "isv.fabric.v1":
        problems.append("ISV Fabric manifest must use schemaVersion isv.fabric.v1")
    manifest_by_name = {
        str(item.get("name")): item
        for item in fabric_manifest.get("tables", [])
        if isinstance(item, dict)
    }
    expected_tables = {
        str(definition.get("collection"))
        for definition in ontology.get("entities", {}).values()
        if isinstance(definition, dict)
    }
    if set(manifest_by_name) != expected_tables:
        problems.append(
            "ISV Fabric manifest tables do not match ontology collections: "
            f"expected {sorted(expected_tables)}, got {sorted(manifest_by_name)}"
        )
    for entity_name, definition in ontology.get("entities", {}).items():
        table = str(definition.get("collection"))
        columns = [str(definition.get("key")), *map(str, definition.get("attributes", []))]
        manifest_table = manifest_by_name.get(table, {})
        if manifest_table.get("columns") != columns:
            problems.append(f"ISV Fabric manifest {table}: columns do not match {entity_name}")
        registry_rows = registry.get(table, [])
        if manifest_table.get("rowCount") != len(registry_rows):
            problems.append(f"ISV Fabric manifest {table}: rowCount is stale")
        csv_path = FABRIC_DIR / f"{table}.csv"
        try:
            with csv_path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                csv_rows = list(reader)
                csv_columns = list(reader.fieldnames or [])
        except OSError as exc:
            problems.append(f"ISV Fabric table {table}: {exc}")
            continue
        if csv_columns != columns:
            problems.append(f"ISV Fabric table {table}: header does not match ontology")
        expected_rows = [
            {column: _fabric_value(row.get(column)) for column in columns}
            for row in registry_rows
        ]
        if csv_rows != expected_rows:
            problems.append(f"ISV Fabric table {table}: generated rows are stale")

    prompts = prompt_catalog.get("prompts", [])
    prompt_ids = [str(prompt.get("id", "")) for prompt in prompts]
    if len(set(prompt_ids)) != len(prompt_ids):
        problems.append("prompt IDs must be unique")
    prompt_meta = prompt_catalog.get("meta", {})
    if prompt_meta.get("account_id") != hero_account:
        problems.append("prompt catalog account_id does not match the hero account")
    if prompt_meta.get("renewal_id") != hero_renewal:
        problems.append("prompt catalog renewal_id does not match the hero renewal")
    if not str(prompt_meta.get("account_id", "")).strip():
        problems.append("prompt catalog account_id is missing")
    for prompt in prompts:
        prompt_id = prompt.get("id", "<unknown>")
        prompt_account = str(prompt.get("account_id", ""))
        prompt_renewal = str(prompt.get("renewal_id", ""))
        if prompt_account not in account_ids:
            problems.append(f"prompt {prompt_id}: unknown account_id")
        if prompt_renewal not in renewal_ids:
            problems.append(f"prompt {prompt_id}: unknown renewal_id")
        if prompt.get("category") not in PROMPT_CATEGORIES:
            problems.append(f"prompt {prompt_id}: invalid category")
        if prompt.get("intent") not in PROMPT_INTENTS:
            problems.append(f"prompt {prompt_id}: invalid intent")
        required_iqs = set(prompt.get("required_iqs", []))
        if not required_iqs or not required_iqs <= IQ_NAMES:
            problems.append(f"prompt {prompt_id}: invalid required_iqs")
        if not prompt.get("expected_outcomes"):
            problems.append(f"prompt {prompt_id}: expected_outcomes is empty")
    if len(prompts) != 4:
        problems.append("prompt catalog must include exactly four demo prompts")
    named_prompts = [
        prompt for prompt in prompts if "Contoso" in str(prompt.get("text", ""))
    ]
    if len(named_prompts) < 3:
        problems.append(
            "prompt catalog must include at least three explicitly named hero-account prompts"
        )
    if not any(set(prompt.get("required_iqs", [])) == IQ_NAMES for prompt in prompts):
        problems.append("prompt catalog needs at least one all-four-IQ prompt")
    if {prompt.get("category") for prompt in prompts} != PROMPT_CATEGORIES:
        problems.append("prompt catalog must cover all four categories")
    if {prompt.get("intent") for prompt in prompts} != PROMPT_INTENTS:
        problems.append("prompt catalog must cover all four grounded synthesis intents")

    for account in registry.get("accounts", []):
        subscription_arr = sum(
            int(subscription.get("annual_value", 0))
            for subscription in registry.get("subscriptions", [])
            if subscription.get("account_id") == account.get("id")
        )
        if subscription_arr != account.get("annual_recurring_revenue"):
            problems.append(
                f"accounts.{account.get('id')}: subscription ARR {subscription_arr} does not "
                f"match account ARR {account.get('annual_recurring_revenue')}"
            )

    required_document_types = {
        "contract",
        "support_policy",
        "pricing_policy",
        "product_brief",
        "renewal_playbook",
    }
    actual_document_types: set[str] = set()
    for path in sorted(FOUNDRY_DOCS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            problems.append(f"ISV Foundry document {path.name}: missing YAML front matter")
            continue
        try:
            _, front_matter, _ = text.split("---", 2)
            metadata = yaml.safe_load(front_matter) or {}
        except (ValueError, yaml.YAMLError) as exc:
            problems.append(f"ISV Foundry document {path.name}: invalid front matter: {exc}")
            continue
        if metadata.get("synthetic") is not True:
            problems.append(f"ISV Foundry document {path.name}: synthetic must be true")
        document_type = str(metadata.get("doc_type", ""))
        if document_type:
            actual_document_types.add(document_type)
        if metadata.get("account_id") not in (None, *account_ids):
            problems.append(f"ISV Foundry document {path.name}: unexpected account_id")
        if metadata.get("renewal_id") not in (None, *renewal_ids):
            problems.append(f"ISV Foundry document {path.name}: unexpected renewal_id")
    if actual_document_types != required_document_types:
        problems.append(
            "ISV Foundry corpus document types do not match the required set: "
            f"expected {sorted(required_document_types)}, got {sorted(actual_document_types)}"
        )

    required_work_types = {
        "customer_meeting",
        "customer_email",
        "internal_team_plan",
    }
    actual_work_types: set[str] = set()
    for path in sorted(WORK_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            problems.append(f"ISV Work document {path.name}: missing YAML front matter")
            continue
        try:
            _, front_matter, _ = text.split("---", 2)
            metadata = yaml.safe_load(front_matter) or {}
        except (ValueError, yaml.YAMLError) as exc:
            problems.append(f"ISV Work document {path.name}: invalid front matter: {exc}")
            continue
        if metadata.get("synthetic") is not True:
            problems.append(f"ISV Work document {path.name}: synthetic must be true")
        document_account_id = str(metadata.get("account_id", ""))
        document_renewal_id = str(metadata.get("renewal_id", ""))
        if document_account_id not in account_ids:
            problems.append(f"ISV Work document {path.name}: account_id mismatch")
        if document_renewal_id not in renewal_ids:
            problems.append(f"ISV Work document {path.name}: renewal_id mismatch")
        elif next(
            (
                renewal.get("account_id")
                for renewal in registry.get("renewals", [])
                if renewal.get("id") == document_renewal_id
            ),
            None,
        ) != document_account_id:
            problems.append(f"ISV Work document {path.name}: account/renewal mismatch")
        actual_work_types.add(str(metadata.get("doc_type", "")))
    if actual_work_types != required_work_types:
        problems.append(
            "ISV Work document types do not match the required set: "
            f"expected {sorted(required_work_types)}, got {sorted(actual_work_types)}"
        )
    work_commitment_payloads: list[dict] = []
    for path in sorted(WORK_DIR.glob("*commitments.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"invalid ISV Work commitments {path.name}: {exc}")
            continue
        if payload.get("schemaVersion") != "isv.work.v1":
            problems.append(
                f"ISV Work commitments {path.name} must use schemaVersion isv.work.v1"
            )
        if payload.get("synthetic") is not True:
            problems.append(f"ISV Work commitments {path.name} must be marked synthetic")
        work_commitment_payloads.append(payload)
    registry_commitments = {
        str(item["id"]): {
            "owner": next(
                (
                    employee["display_name"]
                    for employee in registry.get("employees", [])
                    if employee["id"] == item["owner_id"]
                ),
                "",
            ),
            "dueDate": item["due_date"],
            "status": item["status"],
            "text": item["text"],
        }
        for item in registry.get("commitments", [])
    }
    work_commitment_rows = {
        str(item["id"]): {
            key: item.get(key)
            for key in ("owner", "dueDate", "status", "text")
        }
        for payload in work_commitment_payloads
        for item in payload.get("commitments", [])
    }
    if work_commitment_rows != registry_commitments:
        problems.append("ISV Work commitments do not match the canonical registry")

    return problems


def main() -> int:
    problems = validate()
    if problems:
        print(f"FAIL, {len(problems)} ISV consistency problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(
        "OK, ISV registry, ontology, prompts, portfolio, specialists, and synthetic "
        "relationships are consistent."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
