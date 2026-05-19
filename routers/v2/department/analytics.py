from fastapi import APIRouter, Depends, HTTPException, status
from models.database import MongoDB
from routers.v2.department.dependencies import get_current_department_editor
from utils.logger import get_logger
from utils.vdb import QdrantVDB
import config

logger = get_logger(__name__)

router = APIRouter(prefix="/department/analytics", tags=["department-analytics"])


@router.get("/summary")
async def get_summary(user: dict = Depends(get_current_department_editor)):
    try:
        department_id = user.get("department_id")
        is_admin = user.get("is_admin", False) or user.get("role") == "admin"

        client = QdrantVDB().client
        collection_name = config.QDRANT["collection_name"]

        total_sources = 0
        seen_paths = set()

        next_page_offset = None
        while True:
            scroll_result, next_page_offset = client.scroll(
                collection_name=collection_name,
                limit=100,
                with_payload=True,
                with_vectors=False,
                offset=next_page_offset,
            )

            for point in scroll_result:
                payload = point.payload
                if not payload:
                    continue

                metadata = payload.get("metadata", {})
                source_dept = metadata.get("department_id")

                if not is_admin and source_dept != department_id:
                    continue

                file_path = payload.get("file_path")
                if file_path and file_path not in seen_paths:
                    seen_paths.add(file_path)

            if next_page_offset is None:
                break

        total_sources = len(seen_paths)

        return {
            "total_sources": total_sources,
        }

    except Exception as e:
        logger.error(f"Error fetching department analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch department analytics: {str(e)}",
        )
