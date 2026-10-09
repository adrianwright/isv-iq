from __future__ import annotations

from pathlib import Path

from load_fabric_lakehouse import load_manifest


ROOT = Path(__file__).resolve().parents[3]


def test_manifest_selects_all_isv_tables() -> None:
    tables = load_manifest(ROOT / "data" / "isv" / "fabric" / "manifest.json")
    assert len(tables) == 15
    assert tables[0] == "accounts"
    assert "renewals" in tables
    assert "expansion_candidates" in tables
