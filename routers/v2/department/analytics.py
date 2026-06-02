from fastapi import APIRouter, Depends, HTTPException, status
from models.database import MongoDB
from models.user import UserDB
from routers.v2.department.dependencies import get_current_department_editor
from utils.logger import get_logger
from utils.vdb import QdrantVDB
import config

logger = get_logger(__name__)

router = APIRouter(prefix="/department/analytics", tags=["department-analytics"])

user_db = UserDB()


@router.get("/summary")
async def get_summary(user: dict = Depends(get_current_department_editor)):
    try:
        department_id = user.get("department_id")
        is_admin = user.get("is_admin", False) or user.get("role") == "admin"

        # --- Qdrant source stats ---
        client = QdrantVDB().client
        collection_name = config.QDRANT["collection_name"]

        total_sources = 0
        active_sources = 0
        inactive_sources = 0
        pdf_count = 0
        web_count = 0
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
                    total_sources += 1

                    is_active = payload.get("is_active", True)
                    if is_active:
                        active_sources += 1
                    else:
                        inactive_sources += 1

                    is_web = metadata.get("is_web_source", False)
                    if is_web:
                        web_count += 1
                    else:
                        pdf_count += 1

            if next_page_offset is None:
                break

        # --- User stats from MongoDB ---
        db = MongoDB.get_db()
        dept_user_ids = []

        if is_admin and not department_id:
            all_users = user_db.get_all_users()
            dept_user_ids = [u["user_id"] for u in all_users]
        else:
            all_users = user_db.get_all_users()
            dept_user_ids = [
                u["user_id"]
                for u in all_users
                if u.get("department_id") == department_id
            ]

        unique_users = len(dept_user_ids)

        total_chats = 0
        total_messages = 0

        if dept_user_ids:
            chat_count_pipeline = [
                {"$match": {"user_id": {"$in": dept_user_ids}}},
                {"$count": "total"},
            ]
            chat_result = list(db["chats"].aggregate(chat_count_pipeline))
            total_chats = chat_result[0]["total"] if chat_result else 0

            msg_count_pipeline = [
                {"$match": {"user_id": {"$in": dept_user_ids}}},
                {"$count": "total"},
            ]
            msg_result = list(db["messages"].aggregate(msg_count_pipeline))
            total_messages = msg_result[0]["total"] if msg_result else 0

        # --- Upload history count ---
        total_uploads = 0
        import os

        ocr_dir = "ocr_results"
        if os.path.isdir(ocr_dir):
            for fname in os.listdir(ocr_dir):
                if not fname.endswith(".json"):
                    continue
                total_uploads += 1

        return {
            "total_sources": total_sources,
            "active_sources": active_sources,
            "inactive_sources": inactive_sources,
            "source_types": {"pdf": pdf_count, "web": web_count},
            "total_uploads": total_uploads,
            "unique_users": unique_users,
            "total_chats": total_chats,
            "total_messages": total_messages,
        }

    except Exception as e:
        logger.error(f"Error fetching department analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch department analytics: {str(e)}",
        )
