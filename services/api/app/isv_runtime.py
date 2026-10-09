from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


@lru_cache(maxsize=4)
def load_isv_registry(path: str) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("ISV registry must contain a YAML object")
    return data


@lru_cache(maxsize=4)
def load_isv_portfolio(path: str) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("accounts"), list):
        raise ValueError("ISV portfolio must contain an accounts list")
    return data


def find_isv_record(registry: dict[str, Any], collection: str, record_id: str) -> dict[str, Any]:
    record = next(
        (item for item in registry.get(collection, []) if item.get("id") == record_id),
        None,
    )
    if record is None:
        raise ValueError(f"Unknown {collection.rstrip('s')} id: {record_id}")
    return record


def related(
    registry: dict[str, Any],
    collection: str,
    field: str,
    value: str,
) -> list[dict[str, Any]]:
    return [item for item in registry.get(collection, []) if item.get(field) == value]


def resolve_isv_context(
    registry: dict[str, Any],
    account_id: str | None,
    renewal_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = registry["meta"]
    resolved_account_id = account_id or meta["hero_account_id"]
    resolved_renewal_id = renewal_id or meta["hero_renewal_id"]
    account = find_isv_record(registry, "accounts", resolved_account_id)
    renewal = find_isv_record(registry, "renewals", resolved_renewal_id)
    if renewal["account_id"] != account["id"]:
        raise ValueError(
            f"Renewal {renewal['id']} does not belong to account {account['id']}"
        )
    return account, renewal
