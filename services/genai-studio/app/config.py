"""Runtime configuration for the AI Studio service, sourced from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name) or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Immutable view of service configuration."""

    # Service
    port: int = field(default_factory=lambda: _env_int("STUDIO_PORT", 8090))
    internal_service_key: str = field(default_factory=lambda: _env("STUDIO_INTERNAL_SERVICE_KEY"))
    max_steps: int = field(default_factory=lambda: _env_int("STUDIO_MAX_STEPS", 8))
    message_max_chars: int = field(default_factory=lambda: _env_int("STUDIO_MESSAGE_MAX_CHARS", 1000))

    # OCI Generative AI
    genai_model_id: str = field(default_factory=lambda: _env("OCI_GENAI_MODEL_ID"))
    genai_compartment_id: str = field(default_factory=lambda: _env("OCI_GENAI_COMPARTMENT_ID"))
    genai_endpoint: str = field(default_factory=lambda: _env("OCI_GENAI_ENDPOINT"))
    oci_auth_type: str = field(default_factory=lambda: _env("OCI_AUTH_TYPE", "INSTANCE_PRINCIPAL"))
    oci_config_profile: str = field(default_factory=lambda: _env("OCI_CONFIG_PROFILE", "DEFAULT"))
    genai_temperature: float = field(default_factory=lambda: _env_float("GENAI_TEMPERATURE", 0.2))
    genai_max_tokens: int = field(default_factory=lambda: _env_int("GENAI_MAX_TOKENS", 800))

    # Observability — OTEL -> OCI APM
    otel_service_name: str = field(default_factory=lambda: _env("OTEL_SERVICE_NAME", "octo-genai-studio"))
    service_namespace: str = field(default_factory=lambda: _env("SERVICE_NAMESPACE", "octo-drone-shop"))
    app_version: str = field(default_factory=lambda: _env("APP_VERSION", "0.1.0"))
    apm_endpoint: str = field(default_factory=lambda: _env("OCI_APM_ENDPOINT"))
    apm_private_data_key: str = field(default_factory=lambda: _env("OCI_APM_PRIVATE_DATA_KEY"))

    # Data access (Sales Analyst)
    db_kind: str = field(default_factory=lambda: _env("STUDIO_DB_KIND", "none").lower())
    db_dsn: str = field(default_factory=lambda: _env("STUDIO_DB_DSN"))
    db_user: str = field(default_factory=lambda: _env("STUDIO_DB_USER"))
    db_password: str = field(default_factory=lambda: _env("STUDIO_DB_PASSWORD"))
    oracle_wallet_dir: str = field(default_factory=lambda: _env("STUDIO_ORACLE_WALLET_DIR"))

    # Evidence agent
    web_search_enabled: bool = field(default_factory=lambda: _env_bool("STUDIO_WEB_SEARCH_ENABLED", False))

    @property
    def genai_configured(self) -> bool:
        return bool(self.genai_model_id and self.genai_compartment_id and self.genai_endpoint)

    @property
    def apm_configured(self) -> bool:
        return bool(self.apm_endpoint and self.apm_private_data_key)

    @property
    def db_configured(self) -> bool:
        return self.db_kind in {"oracle", "postgres"} and bool(self.db_dsn)


@lru_cache
def get_settings() -> Settings:
    """Return process-wide settings (cached)."""
    return Settings()
