from fastapi import APIRouter, HTTPException, Depends, status
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
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
from models.database import MongoDB
from utils.logger import get_logger
import config

logger = get_logger(__name__)
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


# Alias endpoints for /api/admin/settings compatibility
@router.get("/settings")
async def get_settings(user: dict = Depends(get_current_admin)):
    """
    Alias for GET /admin/config. Returns current system configuration.
    """
    return await get_config(user)


@router.put("/settings")
async def update_settings(
    new_config: SystemConfig, user: dict = Depends(get_current_admin)
):
    """
    Alias for PUT /admin/config. Updates system configuration.
    """
    return await update_config(new_config, user)


@router.post("/cache/flush")
async def flush_cache(user: dict = Depends(get_current_admin)):
    """
    Clears the semantic cache by removing cached embeddings from recent messages.
    Requires administrative privileges.
    """
    try:
        db = MongoDB.get_db()
        # Remove embeddings from messages to effectively flush the semantic cache
        # while preserving chat history
        result = db["messages"].update_many(
            {"embedding": {"$exists": True}},
            {"$unset": {"embedding": ""}}
        )
        logger.info(f"Semantic cache flushed by admin. {result.modified_count} message embeddings cleared.")
        return {
            "message": "Semantic cache flushed successfully",
            "cleared_entries": result.modified_count,
        }
    except Exception as e:
        logger.error(f"Failed to flush cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to flush cache: {str(e)}",
        )


@router.get("/analytics/flagged")
async def get_flagged_answers(
    limit: int = 50,
    min_dislikes: int = 1,
    user: dict = Depends(get_current_admin),
):
    """
    Returns assistant messages with high dislikes (poisoned / disputed answers)
    for admin audit and review.
    Requires administrative privileges.
    """
    try:
        db = MongoDB.get_db()
        pipeline = [
            {
                "$match": {
                    "role": "assistant",
                    "$or": [
                        {"dislikes_count": {"$gte": min_dislikes}},
                        {"feedback": -1},
                    ],
                }
            },
            {"$sort": {"dislikes_count": -1, "timestamp": -1}},
            {"$limit": limit},
            {
                "$lookup": {
                    "from": "chats",
                    "localField": "chat_id",
                    "foreignField": "chat_id",
                    "as": "chat_info",
                }
            },
            {
                "$project": {
                    "message_id": 1,
                    "chat_id": 1,
                    "content": 1,
                    "timestamp": 1,
                    "likes_count": 1,
                    "dislikes_count": 1,
                    "feedback": 1,
                    "sources": 1,
                    "chat_title": {"$arrayElemAt": ["$chat_info.title", 0]},
                }
            },
        ]
        flagged = list(db["messages"].aggregate(pipeline))
        return {"flagged": flagged, "count": len(flagged)}
    except Exception as e:
        logger.error(f"Failed to fetch flagged answers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch flagged answers: {str(e)}",
        )


@router.get("/analytics/cache-stats")
async def get_cache_stats(user: dict = Depends(get_current_admin)):
    """
    Returns semantic cache statistics including hits, total lookups,
    and cost savings estimation.
    Requires administrative privileges.
    """
    try:
        db = MongoDB.get_db()

        # Count messages with embeddings (cacheable entries)
        cacheable = db["messages"].count_documents({"embedding": {"$exists": True}})

        # Count total assistant messages (LLM calls)
        total_llm_calls = db["messages"].count_documents({"role": "assistant"})

        # Count cache hits (messages that reference a cached_from_message_id)
        cache_hits = db["messages"].count_documents(
            {"role": "assistant", "cached_from_message_id": {"$exists": True, "$ne": None}}
        )

        # Estimate cost savings: assume average $0.002 per LLM call
        avg_cost_per_call = 0.002
        estimated_savings = round(cache_hits * avg_cost_per_call, 4)

        # Recent hit rate (last 7 days)
        since = datetime.utcnow() - timedelta(days=7)
        recent_calls = db["messages"].count_documents(
            {"role": "assistant", "timestamp": {"$gte": since}}
        )
        recent_hits = db["messages"].count_documents(
            {
                "role": "assistant",
                "cached_from_message_id": {"$exists": True, "$ne": None},
                "timestamp": {"$gte": since},
            }
        )
        hit_rate = round((recent_hits / recent_calls) * 100, 2) if recent_calls > 0 else 0

        return {
            "total_cacheable_entries": cacheable,
            "total_llm_calls": total_llm_calls,
            "total_cache_hits": cache_hits,
            "estimated_cost_savings_usd": estimated_savings,
            "recent_hit_rate_percent": hit_rate,
            "recent_llm_calls": recent_calls,
            "recent_cache_hits": recent_hits,
            "cache_config": config.SEMANTIC_CACHE,
        }
    except Exception as e:
        logger.error(f"Failed to fetch cache stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch cache stats: {str(e)}",
        )
