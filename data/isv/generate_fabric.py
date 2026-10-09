"""Export the canonical ISV registry as deterministic Fabric Lakehouse CSV tables."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import yaml

ISV_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = ISV_DIR / "registry.yaml"
ONTOLOGY_PATH = ISV_DIR / "ontology.yaml"
OUTPUT_DIR = ISV_DIR / "fabric"


def _load(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a YAML object")
    return payload


def _csv_value(value: Any) -> str | int | float:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    return value


def export_fabric_tables(
    registry_path: Path = REGISTRY_PATH,
    ontology_path: Path = ONTOLOGY_PATH,
    output_dir: Path = OUTPUT_DIR,
) -> list[Path]:
    registry = _load(registry_path)
    ontology = _load(ontology_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    manifest_tables: list[dict[str, Any]] = []
    for definition in ontology.get("entities", {}).values():
        collection = str(definition["collection"])
        fieldnames = [str(definition["key"]), *map(str, definition.get("attributes", []))]
        rows = registry.get(collection, [])
        if not isinstance(rows, list):
            raise ValueError(f"registry collection {collection!r} must be a list")

        output_path = output_dir / f"{collection}.csv"
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="raise")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: _csv_value(row.get(field)) for field in fieldnames})
        written.append(output_path)
        manifest_tables.append(
            {
                "name": collection,
                "key": str(definition["key"]),
                "columns": fieldnames,
                "rowCount": len(rows),
            }
        )

    (output_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schemaVersion": "isv.fabric.v1",
                "source": "data/isv/registry.yaml",
                "tables": manifest_tables,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return written


def main() -> int:
    paths = export_fabric_tables()
    print(f"Exported {len(paths)} ISV Fabric tables to {OUTPUT_DIR}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
