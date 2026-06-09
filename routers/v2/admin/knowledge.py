from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from pydantic import BaseModel
from typing import List
import os
import shutil
import json
from datetime import datetime
from qdrant_client.models import Filter, FieldCondition, MatchValue
import config
from routers.v2.admin.dependencies import get_current_admin
from utils.logger import get_logger
from utils.ocr import pdf_to_images, ocr_with_gpt
from utils.vdb import QdrantVDB

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/knowledge", tags=["admin-knowledge"])

# Ensure directories exist
UPLOAD_DIR = os.path.join("data", "uploads")
OCR_RESULTS_DIR = "ocr_results"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OCR_RESULTS_DIR, exist_ok=True)


def get_qdrant_client():
    return QdrantVDB().client



def save_ocr_result(metadata, text):
    """Save OCR output with metadata."""
    file_out = os.path.join(
        OCR_RESULTS_DIR, f"{metadata['file_name']}_page{metadata['page_number']}.json"
    )
    with open(file_out, "w", encoding="utf-8") as f:
        json.dump({"metadata": metadata, "text": text}, f, ensure_ascii=False, indent=2)
    return file_out


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
                offset=next_page_offset,
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
                        normalized_path = normalized_path.replace(
                            "data/data/", "data/", 1
                        )

                    metadata = payload.get("metadata", {})
                    is_web = metadata.get("is_web_source", False)

                    # Determine source title
                    title = (
                        metadata.get("source_title")
                        or metadata.get("file_name")
                        or os.path.basename(normalized_path)
                    )

                    # Determine type
                    source_type = (
                        "web" if is_web or normalized_path.startswith("http") else "pdf"
                    )

                    # Determine view/redirect URL
                    if source_type == "pdf":
                        view_url = f"/api/document/{normalized_path}"
                    else:
                        view_url = normalized_path  # Direct link for web

                    # Get status
                    is_active = payload.get("is_active", True)

                    unique_sources[file_path] = {
                        "id": file_path,
                        "title": title,
                        "type": source_type,
                        "path": normalized_path,
                        "url": view_url,
                        "is_web": is_web,
                        "is_active": is_active,
                        "metadata": metadata,
                    }

            if next_page_offset is None:
                break

        return list(unique_sources.values())

    except Exception as e:
        logger.error(f"Error fetching knowledge base: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch knowledge base: {str(e)}",
        )


class ToggleStatusRequest(BaseModel):
    id: str  # This is the file_path
    is_active: bool


@router.put("/toggle")
async def toggle_source_status(
    request: ToggleStatusRequest, user: dict = Depends(get_current_admin)
):
    """
    Toggle the inclusion status of a document in the knowledge base.
    """
    try:
        vdb = QdrantVDB()
        vdb.toggle_source_status(request.id, request.is_active)
        return {
            "status": "success",
            "id": request.id,
            "is_active": request.is_active,
        }
    except Exception as e:
        logger.error(f"Error toggling source status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to toggle source status: {str(e)}",
        )


@router.delete("/delete")
async def delete_source(source_id: str, user: dict = Depends(get_current_admin)):
    """
    Permanently remove all Qdrant points associated with a source from the
    knowledge base.  ``source_id`` is the ``file_path`` value used as the
    document identifier (URL for web sources, filesystem path for PDFs).
    """
    try:
        client = get_qdrant_client()
        collection_name = config.QDRANT["collection_name"]

        client.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="file_path",
                        match=MatchValue(value=source_id),
                    )
                ]
            ),
        )
        return {"status": "success", "message": f"Source {source_id} deleted"}
    except Exception as e:
        logger.error(f"Error deleting source: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete source: {str(e)}",
        )


@router.get("/qdrant-dashboard")
async def get_qdrant_dashboard(user: dict = Depends(get_current_admin)):
    """
    Returns the URL for the Qdrant management dashboard.
    Requires administrative privileges.
    """
    import os
    dashboard_host = os.getenv("QDRANT_EXTERNAL_HOST", "localhost")
    dashboard_port = os.getenv("QDRANT_EXTERNAL_PORT", config.QDRANT['port'])
    dashboard_url = f"http://{dashboard_host}:{dashboard_port}/dashboard"
    return {"url": dashboard_url}


@router.post("/upload")
async def upload_documents(
    files: List[UploadFile] = File(...),
    is_legal_document: bool = True,
    user: dict = Depends(get_current_admin),
):
    """
    Upload PDF files, perform OCR, and index them in the vector database.
    """
    config.reload_config()
    api_key = config.OPENAI.get("api_key")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OpenAI API key is not configured in system settings.",
        )

    results = []
    vdb = QdrantVDB()

    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            results.append(
                {"file": file.filename, "status": "skipped", "reason": "Not a PDF"}
            )
            continue

        file_path = os.path.join(UPLOAD_DIR, os.path.basename(file.filename))
        try:
            # Save the file
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # Process PDF
            pages = pdf_to_images(file_path)
            processed_pages = 0

            for page_num, image in pages:
                # Check if already OCRed
                ocr_filename = f"{file.filename}_page{page_num}.json"
                ocr_path = os.path.join(OCR_RESULTS_DIR, ocr_filename)

                if os.path.exists(ocr_path):
                    with open(ocr_path, "r", encoding="utf-8") as f:
                        ocr_data = json.load(f)
                else:
                    text = ocr_with_gpt(image, api_key)
                    metadata = {
                        "file_name": file.filename,
                        "file_path": file_path,
                        "page_number": page_num,
                        "timestamp": datetime.now().isoformat(),
                        "model": "gpt-4o-mini",
                    }
                    save_ocr_result(metadata, text)
                    ocr_data = {"metadata": metadata, "text": text}

                # Index in VDB
                vdb.embed_ocr_results(
                    ocr_data,
                    {
                        "path": file_path,
                        "source_title": file.filename,
                    },
                    use_semantic=is_legal_document,
                )
                processed_pages += 1

            results.append(
                {
                    "file": file.filename,
                    "status": "success",
                    "pages": processed_pages,
                    "path": file_path,
                }
            )

        except Exception as e:
            logger.error(f"Error processing file {file.filename}: {e}")
            results.append({"file": file.filename, "status": "error", "reason": str(e)})

    return {"results": results}
