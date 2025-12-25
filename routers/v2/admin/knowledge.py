from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any
import os
from qdrant_client import QdrantClient
from qdrant_client.http.models import ScrollRequest
import config
from routers.v2.admin.dependencies import get_current_admin
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/knowledge", tags=["admin-knowledge"])

"""
Admin Knowledge Base Router
Responsibility:
- Audit and manage documents indexed in the vector database.
- Provide administrative access to the Qdrant dashboard.
- Restrict access to administrative users only.
"""

def get_qdrant_client():
    return QdrantClient(host=config.QDRANT["host"], port=config.QDRANT["port"])

@router.get("/")
async def get_knowledge_base(user: dict = Depends(get_current_admin)):
    """
    Returns a list of all unique documents indexed in the knowledge base.
    Requires administrative privileges.
    """
    try:
        client = get_qdrant_client()
        collection_name = config.QDRANT["collection_name"]
        
        unique_sources = {}
        
        next_page_offset = None
        while True:
            scroll_result, next_page_offset = client.scroll(
                collection_name=collection_name,
                limit=100,
                with_payload=True,
                with_vectors=False,
                offset=next_page_offset
            )
            
            for point in scroll_result:
                payload = point.payload
                if not payload:
                    continue
                
                file_path = payload.get("file_path")
                if not file_path:
                    continue
                
                if file_path not in unique_sources:
                    # Normalize path: remove redundant data/ prefix if it exists
                    normalized_path = file_path
                    if normalized_path.startswith("data/data/"):
                        normalized_path = normalized_path.replace("data/data/", "data/", 1)
                    
                    metadata = payload.get("metadata", {})
                    is_web = metadata.get("is_web_source", False)
                    
                    # Determine source title
                    title = metadata.get("source_title") or metadata.get("file_name") or os.path.basename(normalized_path)
                    
                    # Determine type
                    source_type = "web" if is_web or normalized_path.startswith("http") else "pdf"
                    
                    # Determine view/redirect URL
                    if source_type == "pdf":
                        view_url = f"/api/document/{normalized_path}"
                    else:
                        view_url = normalized_path # Direct link for web
                    
                    unique_sources[file_path] = {
                        "id": file_path,
                        "title": title,
                        "type": source_type,
                        "path": normalized_path,
                        "url": view_url,
                        "is_web": is_web,
                        "metadata": metadata
                    }
            
            if next_page_offset is None:
                break
                
        return list(unique_sources.values())
        
    except Exception as e:
        logger.error(f"Error fetching knowledge base: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch knowledge base: {str(e)}"
        )

@router.get("/qdrant-dashboard")
async def get_qdrant_dashboard(user: dict = Depends(get_current_admin)):
    """
    Returns the URL for the Qdrant management dashboard.
    Requires administrative privileges.
    """
    dashboard_url = f"http://{config.QDRANT['host']}:{config.QDRANT['port']}/dashboard"
    return {"url": dashboard_url}
