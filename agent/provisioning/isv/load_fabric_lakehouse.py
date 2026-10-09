"""Load generated ISV CSVs into an isolated Fabric Lakehouse as Delta tables.

Required environment:
  ISV_FABRIC_WS   target ISV workspace id
  ISV_FABRIC_LH   target ISV Lakehouse id
  ONELAKE_TOKEN   token for https://storage.azure.com/.default
  FABRIC_TOKEN    token for https://api.fabric.microsoft.com/.default
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests

FABRIC = "https://api.fabric.microsoft.com/v1"
ONELAKE = "https://onelake.dfs.fabric.microsoft.com"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Set {name} before loading ISV Fabric tables.")
    return value


def load_manifest(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != "isv.fabric.v1":
        raise ValueError(f"{path} is not an isv.fabric.v1 manifest")
    tables = [str(item["name"]) for item in payload.get("tables", [])]
    if not tables:
        raise ValueError(f"{path} contains no tables")
    return tables


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
            raise RuntimeError(f"Fabric table load failed: {response.text[:2000]}")
    raise TimeoutError("Fabric table load did not complete within two minutes.")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    csv_dir = Path(os.environ.get("ISV_CSV_DIR", repo_root / "data" / "isv" / "fabric"))
    tables = load_manifest(csv_dir / "manifest.json")
    workspace_id = _required("ISV_FABRIC_WS")
    lakehouse_id = _required("ISV_FABRIC_LH")
    onelake_headers = {"Authorization": f"Bearer {_required('ONELAKE_TOKEN')}"}
    fabric_headers = {
        "Authorization": f"Bearer {_required('FABRIC_TOKEN')}",
        "Content-Type": "application/json",
    }

    for table in tables:
        local_path = csv_dir / f"{table}.csv"
        payload = local_path.read_bytes()
        relative_path = f"Files/isv/{table}.csv"
        base = f"{ONELAKE}/{workspace_id}/{lakehouse_id}/{relative_path}"

        response = _request("PUT", f"{base}?resource=file", headers=onelake_headers)
        response.raise_for_status()
        response = _request(
            "PATCH",
            f"{base}?action=append&position=0",
            headers={**onelake_headers, "Content-Type": "application/octet-stream"},
            data=payload,
        )
        response.raise_for_status()
        response = _request(
            "PATCH",
            f"{base}?action=flush&position={len(payload)}",
            headers=onelake_headers,
        )
        response.raise_for_status()

        response = _request(
            "POST",
            (
                f"{FABRIC}/workspaces/{workspace_id}/lakehouses/{lakehouse_id}"
                f"/tables/{table}/load"
            ),
            headers=fabric_headers,
            json={
                "relativePath": relative_path,
                "pathType": "File",
                "mode": "Overwrite",
                "formatOptions": {
                    "format": "Csv",
                    "header": True,
                    "delimiter": ",",
                },
            },
        )
        if response.status_code == 202:
            _poll(response.headers.get("Location"), fabric_headers)
        elif response.status_code not in {200, 201}:
            response.raise_for_status()
        print(f"Loaded {table} ({len(payload)} bytes).")

    print(f"Loaded {len(tables)} ISV tables into Lakehouse {lakehouse_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
