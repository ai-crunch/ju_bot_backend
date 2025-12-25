"""
This script is used to generate the vector database for the Ju Bot.
It indexes the scraped web content and the OCR results.
"""

from utils.logger import get_logger
from utils.vdb import QdrantVDB
from utils.generator import Generator
from utils.splitter import TextSplitter
from models.scraped_web import ScrapedWebFiles

import config

logger = get_logger(__name__)


if __name__ == "__main__":
    logger.info("Starting the generator...")
    splitter = TextSplitter(
        chunk_size=config.CHUNK_SIZE,
        overlap=config.CHUNK_OVERLAP,
    )
    qdrant_vdb = QdrantVDB(
        host=config.QDRANT["host"],
        port=config.QDRANT["port"],
        collection_name=config.QDRANT["collection_name"],
    )
    generator = Generator(
        qdrant_vdb,
        splitter,
    )

    logger.info("Loading the scraped web files...")
    ju_regulation = ScrapedWebFiles(
        file_path="data/meaningful_chunks_with_metadata.json",
        source_link="https://units.ju.edu.jo/ar/LegalAffairs/Regulations.aspx",
        source_title="دائرة الشؤون القانونية - الأنظمة والتعليمات",
    )

    web_content = [ju_regulation]
    generator.index_web_content(web_content)

    data_path = config.DATA_DIR_PATH
    ocr_results_dir = config.OCR["results_dir"]
    generator.index_ocr_results(data_path, ocr_results_dir)
    logger.info("Generator completed successfully")
