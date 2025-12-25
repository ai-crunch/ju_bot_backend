from fastapi import APIRouter, HTTPException, Depends, status
from typing import Any, Dict
from models.admin.system_config import (
    SystemConfig,
    update_system_config,
    load_config,
    EmbeddingConfig,
    LLMConfig,
    EmbeddingProvider,
    EmbeddingModel,
    LLMProvider,
    LLMModel,
)
from routers.v2.admin.dependencies import get_current_admin
import config

router = APIRouter(prefix="/admin", tags=["admin-config"])

"""
Admin Configuration Router
Responsibility:
- Provide endpoints for managing system-wide settings.
- Restrict access to administrative users only.
- Trigger system hot-reloads upon configuration changes.
"""


@router.get("/config")
async def get_config(user: dict = Depends(get_current_admin)):
    """
    Returns the current system configuration and available options for the UI.
    Requires administrative privileges.
    """
    current_config = load_config()

    return {
        "config": current_config.model_dump(),
        "options": {
            "embedding_providers": [p.value for p in EmbeddingProvider],
            "embedding_models": EmbeddingConfig.get_provider_options(),
            "llm_providers": [p.value for p in LLMProvider],
            "llm_models": LLMConfig.get_provider_options(),
        },
    }


@router.put("/config")
async def update_config(
    new_config: SystemConfig, user: dict = Depends(get_current_admin)
):
    """
    Updates the system configuration in MongoDB and triggers a hot-reload of the engine.
    Requires administrative privileges.
    """
    success = update_system_config(new_config.model_dump())
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update configuration in database",
        )

    # Trigger hot-reload across the backend application
    config.reload_config()

    return {
        "message": "Configuration updated and reloaded successfully",
        "config": load_config().model_dump(),
    }


@router.post("/config/reset")
async def reset_config(user: dict = Depends(get_current_admin)):
    """
    Resets all system parameters to their hardcoded defaults.
    Requires administrative privileges.
    """
    default_config = SystemConfig()
    success = update_system_config(default_config.model_dump())
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset configuration",
        )

    config.reload_config()
    return {
        "message": "Configuration reset to defaults",
        "config": default_config.model_dump(),
    }
