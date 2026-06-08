import os
import fitz  # PyMuPDF
from PIL import Image
from openai import OpenAI
from tqdm import tqdm
from datetime import datetime
import json
import io
import base64


# -----------------------------
# CONFIGURATION
# -----------------------------
PDF_DIR = "data"  # Root directory containing PDFs (and subdirs)
OUTPUT_DIR = os.path.join("ocr_results", "system")  # System OCR only — never mixed with upload cache
MODEL = "gpt-4o-mini"  # Vision-capable model

# -----------------------------
# INITIALIZE CLIENT
# -----------------------------
client = OpenAI()


# -----------------------------
# UTILITIES
# -----------------------------
def pdf_to_images(pdf_path):
    """Convert each PDF page into a PIL Image."""
    doc = fitz.open(pdf_path)
    images = []
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        images.append((page_num + 1, img))
    doc.close()
    return images


def ocr_with_gpt(image, file_name, page_num):
    """Send image to OpenAI Vision model with descriptive OCR prompt."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)

    # Encode image data as base64
    image_data = base64.b64encode(buffer.getvalue()).decode("utf-8")

    prompt = (
        "You are an expert OCR and visual document analyzer. "
        "Extract all text from this page accurately. "
        "If the page contains tables, charts, or images, describe them in natural language "
        "within their logical context. Keep structure consistent and readable."
    )

    response = client.chat.completions.create(
        model=MODEL,
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

    text = response.choices[0].message.content.strip()
    return text


def save_result(metadata, text):
    """Save OCR output with metadata."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    file_out = os.path.join(
        OUTPUT_DIR, f"{metadata['file_name']}_page{metadata['page_number']}.json"
    )
    with open(file_out, "w", encoding="utf-8") as f:
        json.dump({"metadata": metadata, "text": text}, f, ensure_ascii=False, indent=2)


# -----------------------------
# MAIN PROCESS
# -----------------------------
def process_pdfs(root_dir):
    # First, collect all PDF files to show total progress
    pdf_files = []
    for root, _, files in os.walk(root_dir):
        for file in files:
            if file.lower().endswith(".pdf"):
                pdf_path = os.path.join(root, file)
                pdf_files.append((pdf_path, file))

    # Process each PDF with progress bar
    for pdf_path, file in tqdm(pdf_files, desc="Processing PDFs"):
        print(f"📄 Processing: {pdf_path}")
        try:
            pages = pdf_to_images(pdf_path)
            for page_num, image in tqdm(pages, desc=f"OCR {file}", leave=False):
                # Check if the page already OCRed
                if os.path.exists(
                    os.path.join(OUTPUT_DIR, f"{file}_page{page_num}.json")
                ):
                    print(f"✅ {file} page {page_num} already OCRed")
                    continue
                text = ocr_with_gpt(image, file, page_num)
                metadata = {
                    "file_name": file,
                    "file_path": pdf_path,
                    "page_number": page_num,
                    "timestamp": datetime.now().isoformat(),
                    "model": MODEL,
                }
                save_result(metadata, text)
        except Exception as e:
            print(f"❌ Failed {file}: {e}")


if __name__ == "__main__":
    process_pdfs(PDF_DIR)
    print("✅ OCR extraction complete. Results saved in:", OUTPUT_DIR)
