from fastapi import APIRouter, HTTPException, Response, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Literal, Dict, Any, Optional
from urllib.parse import urlparse
from openai import OpenAI
import os
import urllib.parse

from utils.vdb import QdrantVDB
from utils.pdf_to_image import pdf_converter, get_pdf_page_count
from prompts.qa import QUESTION_PROMPT
from prompts.system import SYSTEM_PROMPT

import config


router = APIRouter(
    prefix="/api",
    tags=["chat"],
)
qdrant_vdb = QdrantVDB()
client = OpenAI(api_key=config.OPENAI["api_key"])


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class SourceMetadata(BaseModel):
    filename: Optional[str] = None
    source_title: Optional[str] = None
    source_link: Optional[str] = None
    is_web_source: bool = False
    source_type: Literal["pdf", "web", "document"] = "document"
    display_name: Optional[str] = None
    clickable: bool = False


class Source(BaseModel):
    text: str
    file_path: str
    metadata: Optional[SourceMetadata] = None


class ChatRequest(BaseModel):
    messages: List[Message]


class ChatResponse(BaseModel):
    response: str
    sources: List[Source]

    class Config:
        json_encoders = {
            # Ensure proper JSON serialization
        }


def get_llm_response(messages: List[dict]) -> str:
    response = client.chat.completions.create(
        model=config.OPENAI["model"],
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
    )
    return response.choices[0].message.content


def retrieve(question: str) -> List[Source]:
    results = qdrant_vdb.retrieve(question)
    sources = []
    for result in results:
        # Process the source data to enhance metadata
        enhanced_source = enhance_source_metadata(result.payload)
        sources.append(Source(**enhanced_source))
    return sources


def enhance_source_metadata(source_data: dict) -> dict:
    """Enhance source metadata for better frontend display"""
    file_path = source_data.get("file_path", "")
    metadata = source_data.get("metadata") or {}

    # Create enhanced metadata
    enhanced_metadata = SourceMetadata()

    # Determine if it's a web source
    parsed_url = urlparse(file_path)
    is_web_source = bool(parsed_url.scheme and parsed_url.netloc)

    if is_web_source:
        # Web source
        enhanced_metadata.is_web_source = True
        enhanced_metadata.source_type = "web"
        enhanced_metadata.source_link = file_path
        enhanced_metadata.clickable = True

        # Try to get title from metadata or create from URL
        if isinstance(metadata, dict) and metadata.get("source_title"):
            enhanced_metadata.source_title = metadata["source_title"]
            enhanced_metadata.display_name = metadata["source_title"]
        else:
            # Create a display name from URL
            domain = parsed_url.netloc
            enhanced_metadata.source_title = f"مصدر من {domain}"
            enhanced_metadata.display_name = f"مصدر من {domain}"
    else:
        # PDF or local file source
        enhanced_metadata.is_web_source = False
        enhanced_metadata.source_type = (
            "pdf" if file_path.lower().endswith(".pdf") else "document"
        )
        enhanced_metadata.clickable = file_path.lower().endswith(".pdf")

        # Extract filename and title
        if isinstance(metadata, dict):
            enhanced_metadata.filename = metadata.get("filename")
            enhanced_metadata.source_title = metadata.get("source_title")

        # Create display name
        if enhanced_metadata.source_title:
            enhanced_metadata.display_name = enhanced_metadata.source_title
        elif enhanced_metadata.filename:
            # Remove extension from filename for display
            display_name = enhanced_metadata.filename
            if "." in display_name:
                display_name = display_name.rsplit(".", 1)[0]
            enhanced_metadata.display_name = display_name
        else:
            enhanced_metadata.display_name = "مستند"

    # Return enhanced source data
    return {
        "text": source_data.get("text", ""),
        "file_path": file_path,
        "metadata": enhanced_metadata.model_dump(),
    }


def get_llm_answer(messages: List[dict], question: str, sources: List[Source]):
    sources_text = "\n".join(
        [f"Source {i+1}: {source.text}" for i, source in enumerate(sources)]
    )
    prompt = QUESTION_PROMPT.format(sources=sources_text, question=question)
    new_messages = messages + [{"role": "user", "content": prompt}]
    response = get_llm_response(new_messages)
    return response


def answer(messages: List[Message]) -> tuple[str, List[Source]]:
    question = messages[-1].content
    messages = [{"role": msg.role, "content": msg.content} for msg in messages[:-1]]
    sources = retrieve(question)
    response = get_llm_answer(messages, question, sources)
    return response, sources


@router.post("/chat")
def chat(request: ChatRequest):
    print("Hitting the chat endpoint | Question: ", request.messages[-1].content)

    try:
        messages = request.messages
        response, sources = answer(messages)
    except Exception as e:
        print("Error: ", e)
        response = (
            "I'm sorry, I'm having trouble answering your question. Please try again."
        )
        sources = []

    print("Response: ", response)
    print("Sources: ", sources)
    print("Returning the response")
    return ChatResponse(response=response, sources=sources)


@router.get("/document/{file_path:path}")
@router.head("/document/{file_path:path}")
def get_document(request: Request, file_path: str):
    """
    Serve PDF documents based on file_path.
    The file_path should be URL-encoded if it contains special characters.
    """
    print(f"Requesting document (raw): {file_path}")
    print(f"Request method: {request.method}")

    # URL decode the file path with proper UTF-8 handling
    try:
        decoded_file_path = urllib.parse.unquote(file_path, encoding="utf-8")
        print(f"Requesting document (decoded): {decoded_file_path}")
    except Exception as decode_error:
        print(f"Error decoding file path: {decode_error}")
        raise HTTPException(status_code=400, detail="Invalid file path encoding")

    # Convert to absolute path from the backend directory
    # This ensures we can find the file correctly
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    abs_file_path = os.path.join(backend_dir, decoded_file_path)
    abs_file_path = os.path.abspath(abs_file_path)

    print(f"Absolute file path: {abs_file_path}")

    # Ensure the file exists and is a PDF
    if not os.path.exists(abs_file_path):
        print(f"File not found: {abs_file_path}")
        raise HTTPException(status_code=404, detail="Document not found")

    if not abs_file_path.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF documents are supported")

    # Security check: ensure the file is within the backend data directory
    backend_data_dir = os.path.join(backend_dir, "data")
    if not abs_file_path.startswith(os.path.abspath(backend_data_dir)):
        print(f"Security violation: File not in allowed directory: {abs_file_path}")
        raise HTTPException(status_code=403, detail="Access denied")

    # CORS headers
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Expose-Headers": "*",
        "Access-Control-Max-Age": "86400",
    }

    # For HEAD requests, just return headers
    if request.method == "HEAD":
        try:
            file_size = os.path.getsize(abs_file_path)

            # Properly encode filename for Content-Disposition header
            filename = os.path.basename(decoded_file_path)
            # Use RFC 5987 encoding for Unicode filenames
            encoded_filename = urllib.parse.quote(filename.encode("utf-8"))
            content_disposition = f"inline; filename*=UTF-8''{encoded_filename}"

            return Response(
                status_code=200,
                headers={
                    **cors_headers,
                    "Content-Type": "application/pdf",
                    "Content-Length": str(file_size),
                    "Accept-Ranges": "bytes",
                    "Content-Disposition": content_disposition,
                },
            )
        except Exception as e:
            print(f"Error getting file size: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    # For GET requests, serve the file with streaming response
    try:

        def generate():
            with open(abs_file_path, "rb") as file_like:
                while chunk := file_like.read(8192):
                    yield chunk

        file_size = os.path.getsize(abs_file_path)

        # Properly encode filename for Content-Disposition header
        filename = os.path.basename(decoded_file_path)
        # Use RFC 5987 encoding for Unicode filenames
        encoded_filename = urllib.parse.quote(filename.encode("utf-8"))
        content_disposition = f"inline; filename*=UTF-8''{encoded_filename}"

        return StreamingResponse(
            generate(),
            media_type="application/pdf",
            headers={
                **cors_headers,
                "Content-Length": str(file_size),
                "Accept-Ranges": "bytes",
                "Content-Disposition": content_disposition,
            },
        )
    except Exception as e:
        print(f"Error serving file: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.options("/document/{file_path:path}")
def options_document(file_path: str):
    """
    Handle CORS preflight requests for PDF documents.
    """
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
    )


@router.get("/document-image/{file_path:path}")
def get_document_as_image(file_path: str, page: int = 0):
    """
    Convert a PDF document page to an image and return as base64.
    This is a fallback when PDF.js fails to load the document.

    Args:
        file_path: URL-encoded path to the PDF file
        page: Page number to convert (0-based, default: 0)
    """
    print(f"Converting PDF page to image: {file_path}, page: {page}")

    # URL decode the file path with proper UTF-8 handling
    try:
        decoded_file_path = urllib.parse.unquote(file_path, encoding="utf-8")
        print(f"Decoded file path: {decoded_file_path}")
    except Exception as decode_error:
        print(f"Error decoding file path: {decode_error}")
        raise HTTPException(status_code=400, detail="Invalid file path encoding")

    # Convert to absolute path
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    abs_file_path = os.path.join(backend_dir, decoded_file_path)
    abs_file_path = os.path.abspath(abs_file_path)

    print(f"Absolute file path: {abs_file_path}")

    # Security and validation checks
    if not os.path.exists(abs_file_path):
        print(f"File not found: {abs_file_path}")
        raise HTTPException(status_code=404, detail="Document not found")

    if not abs_file_path.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF documents are supported")

    backend_data_dir = os.path.join(backend_dir, "data")
    if not abs_file_path.startswith(os.path.abspath(backend_data_dir)):
        print(f"Security violation: File not in allowed directory: {abs_file_path}")
        raise HTTPException(status_code=403, detail="Access denied")

    # Get PDF info first
    pdf_info = pdf_converter.get_pdf_info(abs_file_path)
    if not pdf_info:
        raise HTTPException(status_code=500, detail="Failed to read PDF document")

    # Check if page number is valid
    if page < 0 or page >= pdf_info["page_count"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid page number. PDF has {pdf_info['page_count']} pages (0-indexed)",
        )

    # Convert PDF page to image
    try:
        base64_image = pdf_converter.convert_pdf_page_to_image(abs_file_path, page)
        if not base64_image:
            raise HTTPException(
                status_code=500, detail="Failed to convert PDF page to image"
            )

        # CORS headers
        cors_headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Expose-Headers": "*",
        }

        return Response(
            content=base64_image, media_type="text/plain", headers=cors_headers
        )

    except Exception as e:
        print(f"Error converting PDF to image: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to convert PDF page to image"
        )


@router.get("/document-info/{file_path:path}")
def get_document_info(file_path: str):
    """
    Get information about a PDF document (page count, title, etc.).

    Args:
        file_path: URL-encoded path to the PDF file
    """
    print(f"Getting PDF info: {file_path}")

    # URL decode the file path with proper UTF-8 handling
    try:
        decoded_file_path = urllib.parse.unquote(file_path, encoding="utf-8")
    except Exception as decode_error:
        print(f"Error decoding file path: {decode_error}")
        raise HTTPException(status_code=400, detail="Invalid file path encoding")

    # Convert to absolute path
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    abs_file_path = os.path.join(backend_dir, decoded_file_path)
    abs_file_path = os.path.abspath(abs_file_path)

    # Security and validation checks
    if not os.path.exists(abs_file_path):
        raise HTTPException(status_code=404, detail="Document not found")

    if not abs_file_path.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF documents are supported")

    backend_data_dir = os.path.join(backend_dir, "data")
    if not abs_file_path.startswith(os.path.abspath(backend_data_dir)):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get PDF info
    pdf_info = pdf_converter.get_pdf_info(abs_file_path)
    if not pdf_info:
        raise HTTPException(status_code=500, detail="Failed to read PDF document")

    # CORS headers
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }

    return Response(content=str(pdf_info), headers=cors_headers)


@router.options("/document-image/{file_path:path}")
def options_document_image(file_path: str):
    """Handle CORS preflight requests for PDF image conversion."""
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
    )


@router.options("/document-info/{file_path:path}")
def options_document_info(file_path: str):
    """Handle CORS preflight requests for PDF info."""
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
    )
