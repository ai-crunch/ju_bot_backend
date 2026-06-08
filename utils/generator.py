"""
This class is used to generate the vector database for the Ju Bot.
It indexes the scraped web content and the OCR results.
"""

import os
import json
from typing import List, Dict, Any

from utils.vdb import QdrantVDB
from utils.logger import get_logger
from models.scraped_web import ScrapedWebFiles
from utils.splitter import TextSplitter

logger = get_logger(__name__)


class Generator:
    """
    This class is used to generate the vector database for the Ju Bot.
    It indexes the scraped web content and the OCR results.
    """

    def __init__(
        self,
        qdrant_vdb: QdrantVDB,
        splitter: TextSplitter,
    ):
        logger.info("Initializing the generator...")
        self.qdrant = qdrant_vdb
        self.splitter = splitter

    def _open_json_file(self, file_path: str):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def index_web_content(self, web_content: List[ScrapedWebFiles]):
        """
        Index the web content into the vector database.

        Args:
            web_content: A list of ScrapedWebFiles objects.
        """
        logger.info("Indexing the web content...")
        for content in web_content:
            file_path = content.file_path
            source_link = content.source_link
            source_title = content.source_title
            raw_chunks = self._open_json_file(file_path)

            # If the JSON already contains structured chunks with content, use them directly.
            # Otherwise, run the semantic splitter over the raw text.
            if raw_chunks and isinstance(raw_chunks, list) and isinstance(raw_chunks[0], dict) and "content" in raw_chunks[0]:
                self.qdrant.upsert_web_source(raw_chunks, source_link, source_title)
            else:
                # Fallback: treat the whole loaded data as a single text blob
                text = json.dumps(raw_chunks, ensure_ascii=False) if not isinstance(raw_chunks, str) else raw_chunks
                self.splitter.document_hierarchy = source_title
                structured = self.splitter.split_structured(text)
                self.qdrant.upsert_structured_chunks(structured, source_link, source_title)
        logger.info("Web content indexed successfully")

    def index_ocr_results(self, data_path: str, ocr_results_dir: str):
        """
        Index the OCR results into the vector database.

        Args:
            data_path: The path to the data directory.
            ocr_results_dir: The path to the OCR results directory.
        """
        logger.info("Indexing the OCR results...")
        if not os.path.exists(ocr_results_dir):
            logger.error(f"OCR results directory not found at: {ocr_results_dir}")
            return

        ocr_files = [
            os.path.join(ocr_results_dir, file)
            for file in os.listdir(ocr_results_dir)
            if file.endswith(".json")
        ]
        logger.info(f"Found {len(ocr_files)} OCR result files")

        uploads_prefix = os.path.join(data_path, "uploads")

        for file_path in ocr_files:
            json_file = self._open_json_file(file_path)
            metadata = json_file.get("metadata", {})

            # Belt-and-suspenders: skip any OCR file that belongs to an API upload.
            # These files should never reach this code path because the generator
            # is now directed at ocr_results/system/, but guard explicitly in case
            # a file is misplaced.
            if metadata.get("department_id"):
                logger.warning(
                    f"Skipping department upload OCR file (should not be in system dir): {file_path}"
                )
                continue
            original_pdf_path = metadata.get("file_path", "")
            if original_pdf_path.startswith(uploads_prefix):
                logger.warning(
                    f"Skipping admin upload OCR file (should not be in system dir): {file_path}"
                )
                continue

            if not original_pdf_path:
                logger.error(f"No PDF found in OCR metadata for: {file_path}")
                continue

            # Ensure we don't double the data/ prefix
            if original_pdf_path.startswith(data_path + os.sep) or original_pdf_path.startswith(data_path + "/"):
                file_path = original_pdf_path
            else:
                file_path = os.path.join(data_path, original_pdf_path)
            
            file_name = os.path.basename(file_path)
            source_title = file_name.replace(".pdf", "")
            file_metadata = {
                "filename": file_name,
                "path": file_path,
                "source_title": source_title,
                "is_web_source": False,
                "page_number": metadata.get("page_number", 0),
                "timestamp": metadata.get("timestamp", ""),
                "model": metadata.get("model", ""),
            }

            text = json_file.get("text", "")
            # Use the structured semantic splitter (returns dicts with metadata)
            self.splitter.document_hierarchy = source_title
            structured_chunks = self.splitter.split_structured(text)
            self.qdrant.upsert_structured_ocr(structured_chunks, file_metadata)

        logger.info("OCR results indexed successfully")
