from pathlib import Path

import pytest

from app.config import Settings, SettingsConfigurationError

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_anonymous_mock_requires_local_environment_and_no_live_components() -> None:
    local = Settings(_env_file=None, APP_ENVIRONMENT="development")
    production = Settings(_env_file=None, APP_ENVIRONMENT="production")
    live_local = Settings(
        _env_file=None,
        APP_ENVIRONMENT="development",
        USE_LIVE_ISV_FOUNDRY=True,
    )

    assert local.anonymous_mock_enabled is True
    assert local.mode == "mock"
    assert production.anonymous_mock_enabled is False
    assert production.mode == "live"
    assert live_local.anonymous_mock_enabled is False


def test_production_requires_auth_coordinates() -> None:
    settings = Settings(
        _env_file=None,
        APP_ENVIRONMENT="production",
        AZURE_TENANT_ID="your-tenant-id",
        API_AUDIENCE="api://your-api-client-id",
    )

    with pytest.raises(
        SettingsConfigurationError,
        match="API_AUDIENCE.*AZURE_TENANT_ID",
    ):
        settings.validate_runtime_configuration()


def test_connected_fabric_requires_isolated_coordinates() -> None:
    settings = Settings(
        _env_file=None,
        APP_ENVIRONMENT="production",
        USE_LIVE_ISV_FABRIC=True,
        AZURE_TENANT_ID="00000000-0000-0000-0000-000000000001",
        API_AUDIENCE="api://00000000-0000-0000-0000-000000000002",
        ISV_FABRIC_WORKSPACE_ID="00000000-0000-0000-0000-000000000003",
        ISV_FABRIC_DATA_AGENT_ID="00000000-0000-0000-0000-000000000004",
    )

    settings.validate_runtime_configuration()
    assert settings.ISV_FABRIC_WORKSPACE_ID in settings.isv_fabric_mcp_url
    assert settings.ISV_FABRIC_DATA_AGENT_ID in settings.isv_fabric_mcp_url


def test_connected_foundry_and_native_web_require_isolated_configuration() -> None:
    settings = Settings(
        _env_file=None,
        APP_ENVIRONMENT="production",
        USE_LIVE_ISV_FOUNDRY=True,
        USE_LIVE_ISV_WEB=True,
        AZURE_TENANT_ID="00000000-0000-0000-0000-000000000001",
        API_AUDIENCE="api://00000000-0000-0000-0000-000000000002",
        ISV_SEARCH_ENDPOINT="https://isv-search.search.windows.net",
        ISV_FOUNDRY_KB_NAME="isv-renewal-kb",
        ISV_WEB_IQ_API_KEY="test-web-key",
    )

    settings.validate_runtime_configuration()


def test_connected_work_accepts_injected_pfx() -> None:
    settings = Settings(
        _env_file=None,
        APP_ENVIRONMENT="production",
        USE_LIVE_ISV_WORK=True,
        AZURE_TENANT_ID="00000000-0000-0000-0000-000000000001",
        API_AUDIENCE="api://00000000-0000-0000-0000-000000000002",
        WORK_IQ_CLIENT_ID="00000000-0000-0000-0000-000000000003",
        WORK_IQ_CLIENT_CERTIFICATE_PFX="base64-pfx",
    )

    settings.validate_runtime_configuration()


def test_connected_work_requires_a_certificate_source() -> None:
    settings = Settings(
        _env_file=None,
        APP_ENVIRONMENT="production",
        USE_LIVE_ISV_WORK=True,
        AZURE_TENANT_ID="00000000-0000-0000-0000-000000000001",
        API_AUDIENCE="api://00000000-0000-0000-0000-000000000002",
        WORK_IQ_CLIENT_ID="00000000-0000-0000-0000-000000000003",
    )

    with pytest.raises(SettingsConfigurationError, match="AZURE_CLIENT_ID"):
        settings.validate_runtime_configuration()


def test_dev_script_disables_all_connected_iq_providers() -> None:
    script = (REPO_ROOT / "scripts" / "dev.ps1").read_text(encoding="utf-8")
    for name in (
        "USE_LIVE_ISV_FABRIC",
        "USE_LIVE_ISV_FOUNDRY",
        "USE_LIVE_ISV_WEB",
        "USE_LIVE_ISV_WORK",
    ):
        assert f'{name} = "false"' in script
    assert 'APP_ENVIRONMENT = "development"' in script
    assert 'VITE_ENTRA_TENANT_ID = ""' in script
    assert 'VITE_ENTRA_CLIENT_ID = ""' in script
    assert 'VITE_API_SCOPE = ""' in script
