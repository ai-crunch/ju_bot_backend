from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from pydantic import BaseModel
from typing import List
import os
import shutil
import io
import json
import base64
from datetime import datetime
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue
import fitz
from PIL import Image
from openai import OpenAI
import config
from routers.v2.department.dependencies import get_current_department_editor, verify_department_ownership
from utils.logger import get_logger
from utils.vdb import QdrantVDB

logger = get_logger(__name__)

router = APIRouter(prefix="/department/knowledge", tags=["department-knowledge"])

UPLOAD_BASE = os.path.join("data", "uploads")
OCR_RESULTS_DIR = "ocr_results"
os.makedirs(OCR_RESULTS_DIR, exist_ok=True)


def get_qdrant_client():
    return QdrantVDB().client


def pdf_to_images(pdf_path):
    doc = fitz.open(pdf_path)
    images = []
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        images.append((page_num + 1, img))
    doc.close()
    return images


def ocr_with_gpt(image, api_key, model="gpt-4o-mini"):
    client = OpenAI(api_key=api_key)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    image_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
    prompt = (
        "You are an expert OCR and visual document analyzer. "
        "Extract all text from this page accurately. "
        "If the page contains tables, charts, or images, describe them in natural language "
        "within their logical context. Keep structure consistent and readable."
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are a precise document transcription and summarization assistant.",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_data}"},
                    },
                ],
            },
        ],
    )
    return response.choices[0].message.content.strip()


def save_ocr_result(metadata, text):
    file_out = os.path.join(
        OCR_RESULTS_DIR, f"{metadata['file_name']}_page{metadata['page_number']}.json"
    )
    with open(file_out, "w", encoding="utf-8") as f:
        json.dump({"metadata": metadata, "text": text}, f, ensure_ascii=False, indent=2)
    return file_out


@router.get("/")
async def get_knowledge_base(user: dict = Depends(get_current_department_editor)):
    try:
        client = get_qdrant_client()
        collection_name = config.QDRANT["collection_name"]
        department_id = user.get("department_id")
        is_admin = user.get("is_admin", False) or user.get("role") == "admin"

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

                metadata = payload.get("metadata", {})
                source_dept = metadata.get("department_id")

                if not is_admin and source_dept != department_id:
                    continue

                if file_path not in unique_sources:
                    normalized_path = file_path
                    if normalized_path.startswith("data/data/"):
                        normalized_path = normalized_path.replace("data/data/", "data/", 1)

                    is_web = metadata.get("is_web_source", False)
                    title = (
                        metadata.get("source_title")
                        or metadata.get("file_name")
                        or os.path.basename(normalized_path)
                    )
                    source_type = "web" if is_web or normalized_path.startswith("http") else "pdf"
                    view_url = f"/api/document/{normalized_path}" if source_type == "pdf" else normalized_path
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
        logger.error(f"Error fetching department knowledge base: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch knowledge base: {str(e)}",
        )


@router.put("/toggle/{source_id}")
async def toggle_source_status(
    source_id: str,
    is_active: bool = True,
    user: dict = Depends(get_current_department_editor),
):
    try:
        client = get_qdrant_client()
        collection_name = config.QDRANT["collection_name"]

        scroll_result, _ = client.scroll(
            collection_name=collection_name,
            limit=1,
            with_payload=True,
            with_vectors=False,
            filter=Filter(
                must=[FieldCondition(key="file_path", match=MatchValue(value=source_id))]
            ),
        )

        if scroll_result:
            payload = scroll_result[0].payload
            if not verify_department_ownership(payload, user):
                raise HTTPException(status_code=403, detail="This source does not belong to your department")

        vdb = QdrantVDB()
        vdb.toggle_source_status(source_id, is_active)
        return {"status": "success", "id": source_id, "is_active": is_active}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling source status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to toggle source status: {str(e)}",
        )


@router.delete("/{file_path:path}")
async def delete_source(file_path: str, user: dict = Depends(get_current_department_editor)):
    try:
        client = get_qdrant_client()
        collection_name = config.QDRANT["collection_name"]

        scroll_result, _ = client.scroll(
            collection_name=collection_name,
            limit=1,
            with_payload=True,
            with_vectors=False,
            filter=Filter(
                must=[FieldCondition(key="file_path", match=MatchValue(value=file_path))]
            ),
        )

        if scroll_result:
            payload = scroll_result[0].payload
            if not verify_department_ownership(payload, user):
                raise HTTPException(status_code=403, detail="This source does not belong to your department")

        client.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="file_path", match=MatchValue(value=file_path))]
            ),
        )
        return {"status": "success", "message": f"Source {file_path} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting source: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete source: {str(e)}",
        )


@router.post("/upload")
async def upload_documents(
    files: List[UploadFile] = File(...), user: dict = Depends(get_current_department_editor)
):
    config.reload_config()
    api_key = config.OPENAI.get("api_key")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OpenAI API key is not configured in system settings.",
        )

    department_id = user.get("department_id")
    department_name = user.get("department_name", department_id)

    upload_dir = os.path.join(UPLOAD_BASE, department_id or "unknown")
    os.makedirs(upload_dir, exist_ok=True)

    results = []
    vdb = QdrantVDB()

    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            results.append(
                {"file": file.filename, "status": "skipped", "reason": "Not a PDF"}
            )
            continue

        file_path = os.path.join(upload_dir, file.filename)
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            pages = pdf_to_images(file_path)
            processed_pages = 0

            for page_num, image in pages:
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
                        "department_id": department_id,
                        "department_name": department_name,
                    }
                    save_ocr_result(metadata, text)
                    ocr_data = {"metadata": metadata, "text": text}

                merged_metadata = {
                    "path": file_path,
                    "source_title": file.filename,
                    "department_id": department_id,
                    "department_name": department_name,
                }
                vdb.embed_ocr_results(ocr_data, merged_metadata)
                processed_pages += 1

            results.append({
                "file": file.filename,
                "status": "success",
                "pages": processed_pages,
                "path": file_path,
            })

        except Exception as e:
            logger.error(f"Error processing file {file.filename}: {e}")
            results.append({"file": file.filename, "status": "error", "reason": str(e)})

    return {"results": results}


@router.get("/history")
async def get_upload_history(user: dict = Depends(get_current_department_editor)):
    department_id = user.get("department_id")
    is_admin = user.get("is_admin", False) or user.get("role") == "admin"

    history = []
    ocr_dir = OCR_RESULTS_DIR
    if not os.path.isdir(ocr_dir):
        return []

    for fname in os.listdir(ocr_dir):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(ocr_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            meta = data.get("metadata", {})
            file_dept = meta.get("department_id")

            if not is_admin and file_dept != department_id:
                continue

            history.append({
                "filename": fname,
                "file_name": meta.get("file_name"),
                "page_number": meta.get("page_number"),
                "timestamp": meta.get("timestamp"),
                "department_id": file_dept,
                "department_name": meta.get("department_name"),
            })
        except Exception:
            continue

    history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return history
