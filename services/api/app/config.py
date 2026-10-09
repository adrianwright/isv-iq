from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsConfigurationError(RuntimeError):
    """Raised when connected or production settings are incomplete."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_data_dir() -> Path:
    return _repo_root() / "data"


def _is_operator_value(value: str) -> bool:
    normalized = value.strip().casefold()
    return bool(
        normalized
        and "your-" not in normalized
        and "${" not in normalized
        and not normalized.startswith("<")
        and ".example.invalid" not in normalized
        and normalized != "00000000-0000-0000-0000-000000000000"
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    APP_ENVIRONMENT: str = "production"
    CORS_ORIGINS: str = "http://localhost:5173"
    DATA_DIR: Path = Field(default_factory=_default_data_dir)

    USE_LIVE_ISV_FABRIC: bool = False
    USE_LIVE_ISV_FOUNDRY: bool = False
    USE_LIVE_ISV_WEB: bool = False
    USE_LIVE_ISV_WORK: bool = False
    USE_LIVE_ISV_NARRATION: bool = False

    ISV_OPENAI_ENDPOINT: str = ""
    ISV_OPENAI_DEPLOYMENT: str = "gpt-5-5"
    ISV_OPENAI_API_VERSION: str = "2025-04-01-preview"
    ISV_NARRATION_TIMEOUT_SECONDS: float = 60.0

    ISV_FABRIC_WORKSPACE_ID: str = ""
    ISV_FABRIC_DATA_AGENT_ID: str = ""
    ISV_FABRIC_LAKEHOUSE_ID: str = ""
    ISV_FABRIC_ONTOLOGY_ID: str = ""
    FABRIC_API_SCOPE: str = "https://api.fabric.microsoft.com/.default"

    ISV_SEARCH_ENDPOINT: str = ""
    ISV_FOUNDRY_KB_NAME: str = ""
    ISV_WEB_KB_NAME: str = ""
    ISV_SEARCH_API_VERSION: str = "2026-05-01-preview"
    ISV_WEB_IQ_ENDPOINT: str = "https://api.microsoft.ai/v3/search/web"
    ISV_WEB_IQ_API_KEY: str = ""

    AZURE_SUBSCRIPTION_ID: str = ""
    FABRIC_CAPACITY_RG: str = ""
    FABRIC_CAPACITY_NAME: str = ""
    FABRIC_ARM_API_VERSION: str = "2023-11-01"
    ARM_SCOPE: str = "https://management.azure.com/.default"
    ARM_ENDPOINT: str = "https://management.azure.com"

    AZURE_TENANT_ID: str = ""
    API_AUDIENCE: str = ""
    API_REQUIRED_SCOPE: str = "access_as_user"
    AUTH_HTTP_TIMEOUT_SECONDS: float = 10.0
    AZURE_CLIENT_ID: str = ""

    WORK_IQ_ENDPOINT: str = "https://workiq.svc.cloud.microsoft/a2a/"
    WORK_IQ_SCOPE: str = "api://workiq.svc.cloud.microsoft/.default"
    WORK_IQ_CLIENT_ID: str = ""
    WORK_IQ_KEY_VAULT_URL: str = ""
    WORK_IQ_CLIENT_CERTIFICATE_SECRET_NAME: str = ""
    WORK_IQ_CLIENT_CERTIFICATE_PFX: str = ""
    WORK_IQ_CLIENT_CERTIFICATE: str = ""
    WORK_IQ_CLIENT_CERTIFICATE_THUMBPRINT: str = ""
    WORK_IQ_CLIENT_PUBLIC_CERTIFICATE: str = ""
    WORK_IQ_CERTIFICATE_CACHE_SECONDS: float = 300.0
    WORK_IQ_CERTIFICATE_REFRESH_RETRY_SECONDS: float = 30.0
    WORK_IQ_TIMEOUT_SECONDS: float = 240.0
    WORK_IQ_TIMEZONE: str = "America/Chicago"
    WORK_IQ_TIMEZONE_OFFSET_MINUTES: int = -300

    @property
    def live_components_enabled(self) -> bool:
        return any(
            (
                self.USE_LIVE_ISV_FABRIC,
                self.USE_LIVE_ISV_FOUNDRY,
                self.USE_LIVE_ISV_WEB,
                self.USE_LIVE_ISV_WORK,
            )
        )

    @property
    def anonymous_mock_enabled(self) -> bool:
        local_environment = self.APP_ENVIRONMENT.strip().casefold() in {
            "development",
            "dev",
            "local",
            "test",
        }
        return local_environment and not self.live_components_enabled

    @computed_field
    @property
    def mode(self) -> Literal["mock", "live"]:
        return "mock" if self.anonymous_mock_enabled else "live"

    def validate_runtime_configuration(self) -> None:
        if self.anonymous_mock_enabled:
            return

        required = {"AZURE_TENANT_ID", "API_AUDIENCE", "API_REQUIRED_SCOPE"}
        if self.USE_LIVE_ISV_FABRIC:
            required.update({"ISV_FABRIC_WORKSPACE_ID", "ISV_FABRIC_DATA_AGENT_ID"})
        if self.USE_LIVE_ISV_FOUNDRY:
            required.update({"ISV_SEARCH_ENDPOINT", "ISV_FOUNDRY_KB_NAME"})
        if self.USE_LIVE_ISV_WEB:
            if self.ISV_WEB_IQ_API_KEY.strip():
                required.add("ISV_WEB_IQ_ENDPOINT")
            else:
                required.update({"ISV_SEARCH_ENDPOINT", "ISV_WEB_KB_NAME"})
        if self.USE_LIVE_ISV_NARRATION:
            required.update({"ISV_OPENAI_ENDPOINT", "ISV_OPENAI_DEPLOYMENT"})
        if self.USE_LIVE_ISV_WORK:
            required.update({"WORK_IQ_CLIENT_ID", "WORK_IQ_ENDPOINT", "WORK_IQ_SCOPE"})
            if self.APP_ENVIRONMENT.strip().casefold() == "production":
                if not self.WORK_IQ_CLIENT_CERTIFICATE_PFX.strip():
                    required.update(
                        {
                            "AZURE_CLIENT_ID",
                            "WORK_IQ_KEY_VAULT_URL",
                            "WORK_IQ_CLIENT_CERTIFICATE_SECRET_NAME",
                        }
                    )
            else:
                required.update(
                    {
                        "WORK_IQ_CLIENT_CERTIFICATE",
                        "WORK_IQ_CLIENT_CERTIFICATE_THUMBPRINT",
                    }
                )

        missing = sorted(
            name for name in required if not _is_operator_value(str(getattr(self, name)))
        )
        if missing:
            raise SettingsConfigurationError(
                "Live/production configuration is incomplete or still uses public placeholders: "
                + ", ".join(missing)
            )

    @property
    def isv_fabric_mcp_url(self) -> str:
        return (
            "https://api.fabric.microsoft.com/v1/mcp/workspaces/"
            f"{self.ISV_FABRIC_WORKSPACE_ID}/dataagents/"
            f"{self.ISV_FABRIC_DATA_AGENT_ID}/agent"
        )

    @property
    def isv_fabric_portal_url(self) -> str:
        if not self.ISV_FABRIC_WORKSPACE_ID.strip():
            return ""
        return f"https://app.fabric.microsoft.com/groups/{self.ISV_FABRIC_WORKSPACE_ID}"

    @property
    def fabric_capacity_resource_id(self) -> str:
        return (
            f"/subscriptions/{self.AZURE_SUBSCRIPTION_ID}"
            f"/resourceGroups/{self.FABRIC_CAPACITY_RG}"
            f"/providers/Microsoft.Fabric/capacities/{self.FABRIC_CAPACITY_NAME}"
        )

    @property
    def fabric_capacity_arm_url(self) -> str:
        return (
            f"{self.ARM_ENDPOINT}{self.fabric_capacity_resource_id}"
            f"?api-version={self.FABRIC_ARM_API_VERSION}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def token_issuer(self) -> str:
        return f"https://login.microsoftonline.com/{self.AZURE_TENANT_ID}/v2.0"

    @property
    def token_audiences(self) -> tuple[str, ...]:
        audience = self.API_AUDIENCE.strip()
        app_id = audience.removeprefix("api://")
        try:
            UUID(app_id)
        except ValueError:
            return (audience,)
        return (app_id, f"api://{app_id}")

    @property
    def jwks_url(self) -> str:
        return (
            f"https://login.microsoftonline.com/{self.AZURE_TENANT_ID}"
            "/discovery/v2.0/keys"
        )

    @property
    def obo_authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.AZURE_TENANT_ID}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime_configuration()
    return settings
