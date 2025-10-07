"""
PDF to Image converter utility
Converts PDF pages to images for display when PDF.js fails to load the document.
"""

import os
import base64
from io import BytesIO
from typing import List, Optional, Tuple
import fitz  # PyMuPDF
from PIL import Image


class PDFToImageConverter:
    def __init__(self, max_width: int = 800, quality: int = 85):
        """
        Initialize the PDF to Image converter.

        Args:
            max_width: Maximum width for the converted images
            quality: Image quality (1-100, where 100 is best quality)
        """
        self.max_width = max_width
        self.quality = quality

    def convert_pdf_page_to_image(
        self, pdf_path: str, page_number: int = 0
    ) -> Optional[str]:
        """
        Convert a single PDF page to base64 encoded image.

        Args:
            pdf_path: Path to the PDF file
            page_number: Page number to convert (0-based)

        Returns:
            Base64 encoded image string or None if conversion fails
        """
        try:
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")

            # Open the PDF document
            doc = fitz.open(pdf_path)

            if page_number >= doc.page_count:
                doc.close()
                raise ValueError(
                    f"Page {page_number} doesn't exist. PDF has {doc.page_count} pages."
                )

            # Get the page
            page = doc[page_number]

            # Calculate zoom factor to maintain aspect ratio
            page_rect = page.rect
            zoom_factor = self.max_width / page_rect.width
            matrix = fitz.Matrix(zoom_factor, zoom_factor)

            # Render page to image
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            img_data = pix.tobytes("png")

            # Convert to PIL Image for additional processing if needed
            img = Image.open(BytesIO(img_data))

            # Save to BytesIO with specified quality
            output_buffer = BytesIO()
            img.save(output_buffer, format="JPEG", quality=self.quality, optimize=True)
            img_bytes = output_buffer.getvalue()

            # Encode to base64
            img_base64 = base64.b64encode(img_bytes).decode("utf-8")

            # Cleanup
            doc.close()

            return f"data:image/jpeg;base64,{img_base64}"

        except Exception as e:
            print(f"Error converting PDF page to image: {e}")
            return None

    def convert_pdf_to_images(
        self, pdf_path: str, max_pages: Optional[int] = None
    ) -> List[str]:
        """
        Convert all pages of a PDF to base64 encoded images.

        Args:
            pdf_path: Path to the PDF file
            max_pages: Maximum number of pages to convert (None for all pages)

        Returns:
            List of base64 encoded image strings
        """
        images = []

        try:
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")

            doc = fitz.open(pdf_path)
            total_pages = doc.page_count
            pages_to_convert = min(max_pages or total_pages, total_pages)

            for page_num in range(pages_to_convert):
                try:
                    page = doc[page_num]

                    # Calculate zoom factor
                    page_rect = page.rect
                    zoom_factor = self.max_width / page_rect.width
                    matrix = fitz.Matrix(zoom_factor, zoom_factor)

                    # Render page
                    pix = page.get_pixmap(matrix=matrix, alpha=False)
                    img_data = pix.tobytes("png")

                    # Convert to PIL Image and optimize
                    img = Image.open(BytesIO(img_data))
                    output_buffer = BytesIO()
                    img.save(
                        output_buffer,
                        format="JPEG",
                        quality=self.quality,
                        optimize=True,
                    )
                    img_bytes = output_buffer.getvalue()

                    # Encode to base64
                    img_base64 = base64.b64encode(img_bytes).decode("utf-8")
                    images.append(f"data:image/jpeg;base64,{img_base64}")

                except Exception as e:
                    print(f"Error converting page {page_num}: {e}")
                    continue

            doc.close()

        except Exception as e:
            print(f"Error processing PDF: {e}")

        return images

    def get_pdf_info(self, pdf_path: str) -> Optional[dict]:
        """
        Get basic information about a PDF file.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Dictionary with PDF information or None if error
        """
        try:
            if not os.path.exists(pdf_path):
                return None

            doc = fitz.open(pdf_path)
            info = {
                "page_count": doc.page_count,
                "title": doc.metadata.get("title", ""),
                "author": doc.metadata.get("author", ""),
                "subject": doc.metadata.get("subject", ""),
                "creator": doc.metadata.get("creator", ""),
                "producer": doc.metadata.get("producer", ""),
            }
            doc.close()
            return info

        except Exception as e:
            print(f"Error getting PDF info: {e}")
            return None


# Global converter instance
pdf_converter = PDFToImageConverter(max_width=800, quality=85)


def convert_pdf_page_to_base64(pdf_path: str, page_number: int = 0) -> Optional[str]:
    """
    Convenience function to convert a PDF page to base64 image.

    Args:
        pdf_path: Path to the PDF file
        page_number: Page number to convert (0-based)

    Returns:
        Base64 encoded image string or None if conversion fails
    """
    return pdf_converter.convert_pdf_page_to_image(pdf_path, page_number)


def get_pdf_page_count(pdf_path: str) -> int:
    """
    Get the number of pages in a PDF.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Number of pages in the PDF, or 0 if error
    """
    info = pdf_converter.get_pdf_info(pdf_path)
    return info.get("page_count", 0) if info else 0
