"""
Shared OCR utilities used by the admin and department knowledge upload routers.

Keeping these functions in one place ensures that any improvement to OCR quality
or vision model prompting propagates to both upload paths automatically.
"""

import io
import base64

import fitz  # PyMuPDF
from PIL import Image
from openai import OpenAI


def pdf_to_images(pdf_path: str) -> list[tuple[int, Image.Image]]:
    """
    Render every page of a PDF as a PIL Image at 200 DPI.

    Returns a list of ``(page_number, image)`` tuples where ``page_number``
    is 1-indexed.
    """
    doc = fitz.open(pdf_path)
    images = []
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        images.append((page_num + 1, img))
    doc.close()
    return images


def ocr_with_gpt(image: Image.Image, api_key: str, model: str = "gpt-4o-mini") -> str:
    """
    Extract text from a page image using an OpenAI vision model.

    Tables, charts, and embedded images are described in natural language
    within their logical context so the extracted text remains coherent for
    downstream chunking and retrieval.
    """
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
