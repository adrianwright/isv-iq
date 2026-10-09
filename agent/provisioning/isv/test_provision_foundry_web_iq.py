from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "agent" / "provisioning" / "isv" / "provision_foundry_web_iq.ps1"


def test_foundry_web_provisioner_is_isv_scoped() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "data\\isv\\foundry_docs" in text
    assert "KnowledgeSourceName" in text
    assert "WebKnowledgeBaseName" in text
    assert "project=microsoft-iq-isv" in text
    assert "healthcare protocol" not in text.casefold()
