from fastapi import APIRouter, Depends, HTTPException
from models.database import MongoDB
from routers.v2.admin.dependencies import get_current_admin
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/cache", tags=["admin-cache"])


@router.post("/flush")
async def flush_cache(user: dict = Depends(get_current_admin)):
    """
    Flush the semantic cache by removing embeddings from all historical user messages.
    This prevents future cache hits against old data without deleting chat history.
    """
    try:
        db = MongoDB.get_db()
        msgs = db["messages"]

        # Remove embeddings from user messages so they won't match anymore
        result = msgs.update_many(
            {"role": "user", "embedding": {"$exists": True}},
            {"$unset": {"embedding": ""}},
        )

        cleared = result.modified_count
        logger.info(f"Cache flushed by admin {user['user_id']}: {cleared} entries cleared")

        return {"message": "Cache flushed successfully", "cleared_entries": cleared}
    except Exception as e:
        logger.error(f"Error flushing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))
