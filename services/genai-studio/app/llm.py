"""ChatOCIGenAI factory — OCI Generative AI via the langchain-oci SDK.

Distilled from oci-coordinator-oke/src/llm/factory.py, OCI-only. Resolves auth
(API key / instance principal / resource principal) and returns a LangChain
``BaseChatModel`` the agents invoke inside ``llm_span`` for gen_ai.* telemetry.
"""

from __future__ import annotations

import importlib
import logging
from functools import lru_cache
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from app.config import get_settings

logger = logging.getLogger(__name__)


def _import_chat_oci_genai() -> type[Any]:
    """Import ChatOCIGenAI, preferring the official ``langchain-oci`` package."""
    for module_name in ("langchain_oci", "langchain_oci.chat_models"):
        try:
            module = importlib.import_module(module_name)
            return module.ChatOCIGenAI
        except (AttributeError, ImportError):
            continue
    # Community fallback for older local environments.
    from langchain_community.chat_models.oci_generative_ai import ChatOCIGenAI  # type: ignore

    return ChatOCIGenAI


def _auth_kwargs(auth_type: str, profile: str) -> dict[str, Any]:
    """Map our auth-type string to ChatOCIGenAI auth kwargs."""
    normalized = (auth_type or "INSTANCE_PRINCIPAL").strip().upper().replace("-", "_")
    if normalized == "API_KEY":
        return {"auth_type": "API_KEY", "auth_profile": profile or "DEFAULT"}
    if normalized == "RESOURCE_PRINCIPAL":
        return {"auth_type": "RESOURCE_PRINCIPAL"}
    return {"auth_type": "INSTANCE_PRINCIPAL"}


@lru_cache
def get_llm() -> BaseChatModel:
    """Build the shared ChatOCIGenAI model from settings. Cached per process."""
    settings = get_settings()
    if not settings.genai_configured:
        raise RuntimeError(
            "OCI GenAI is not configured (OCI_GENAI_MODEL_ID / COMPARTMENT_ID / ENDPOINT)"
        )

    chat_cls = _import_chat_oci_genai()
    kwargs: dict[str, Any] = {
        "model_id": settings.genai_model_id,
        "compartment_id": settings.genai_compartment_id,
        "service_endpoint": settings.genai_endpoint,
        "model_kwargs": {
            "temperature": settings.genai_temperature,
            "max_tokens": settings.genai_max_tokens,
        },
        **_auth_kwargs(settings.oci_auth_type, settings.oci_config_profile),
    }
    logger.info(
        "ChatOCIGenAI ready (model=%s, auth=%s)", settings.genai_model_id, settings.oci_auth_type
    )
    return chat_cls(**kwargs)


def provider_family(model_id: str) -> str:
    """Resolve a provider label for gen_ai.* telemetry from the model id."""
    model = (model_id or "").lower()
    if model.startswith("cohere."):
        return "cohere"
    if model.startswith("meta."):
        return "meta"
    if model.startswith("google.") or "gemini" in model:
        return "google"
    return "oracle"
