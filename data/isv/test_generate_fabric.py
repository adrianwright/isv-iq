from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

from generate_fabric import export_fabric_tables


def test_exports_every_ontology_collection(tmp_path: Path) -> None:
    paths = export_fabric_tables(output_dir=tmp_path)
    ontology = yaml.safe_load(Path(__file__).with_name("ontology.yaml").read_text(encoding="utf-8"))

    expected = {
        f"{definition['collection']}.csv"
        for definition in ontology["entities"].values()
    }
    assert {path.name for path in paths} == expected
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schemaVersion"] == "isv.fabric.v1"
    assert len(manifest["tables"]) == 15

    with (tmp_path / "accounts.csv").open(newline="", encoding="utf-8") as handle:
        account = next(csv.DictReader(handle))
    assert account["id"] == "ACC-1001"
    assert account["annual_recurring_revenue"] == "2400000"

    with (tmp_path / "interactions.csv").open(newline="", encoding="utf-8") as handle:
        interaction = next(csv.DictReader(handle))
    assert json.loads(interaction["participants"]) == [
        "CON-1001",
        "CON-1002",
        "EMP-1001",
        "EMP-1002",
    ]
