import os
import uuid
import fitz
import json
from typing import Any, List, Dict
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct, Record
from qdrant_client.models import (
    VectorParams,
    Distance,
    Filter,
    FieldCondition,
    MatchValue,
)
from agno.tools import tool

from utils.embedder import Embedder
from utils.splitter import TextSplitter
from utils.logger import get_logger

import config

logger = get_logger(__name__)


class QdrantVDB:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(QdrantVDB, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        host: str = None,
        port: int = None,
        collection_name: str = None,
    ):
        if self._initialized:
            return

        host = host or config.QDRANT["host"]
        port = port or config.QDRANT["port"]
        collection_name = collection_name or config.QDRANT["collection_name"]

        logger.info(
            f"Initializing QdrantVDB with host={host}, port={port}, collection_name={collection_name}"
        )
        
        # Retry logic for Qdrant connection
        import time
        max_retries = 10
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                self.client = QdrantClient(host=host, port=port)
                # Test connection by checking if we can get collections
                _ = self.client.get_collections()
                logger.info(f"Successfully connected to Qdrant on attempt {attempt + 1}")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Failed to connect to Qdrant (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Failed to connect to Qdrant after {max_retries} attempts: {e}")
                    raise
        
        self.embedder = Embedder()
        self.splitter = TextSplitter(
            chunk_size=config.CHUNK_SIZE, overlap=config.CHUNK_OVERLAP
        )
        self.collection_name = collection_name
        if not self.collection_exists(collection_name):
            self.create_collection()

        self._initialized = True

    def _read_pdf(self, pdf_path):
        text = ""
        try:
            with fitz.open(pdf_path) as doc:
                for page in doc:
                    text += page.get_text()
        except fitz.FileNotFoundError:
            return "Error: PDF file not found."
        return text

    def collection_exists(self, collection_name: str) -> bool:
        return self.client.collection_exists(collection_name)

    def create_collection(self):
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=self.embedder.OUTPUT_SIZE, distance=Distance.COSINE
            ),
        )

    def upsert_web_source(
        self,
        chunks: List[Dict],
        source_link: str,
        source_title: str,
    ):
        """
        Upsert web source data into the collection.

        Args:
            chunks: List of chunk dictionaries with 'content', 'title', 'metadata'
            source_link: URL source of the content
            source_title: Title for the source (used in frontend)
        """
        logger.info(f"Upserting web source data into collection {self.collection_name}")
        chunks_text = [chunk["content"] for chunk in chunks]
        embeddings = self.embedder.embed(chunks_text)
        points = []

        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            metadata = {
                **(chunk.get("metadata", {})),
                "source_link": source_link,
                "source_title": source_title,
                "chunk_title": chunk.get(
                    "title", f"Chunk {chunk.get('chunk_id', idx + 1)}"
                ),
                "is_web_source": True,
                "is_active": True,
            }

            point = PointStruct(
                id=chunk.get("chunk_id", idx),
                vector=embedding,
                payload={
                    "text": chunk["content"],
                    "file_path": source_link,
                    "metadata": metadata,
                },
            )

            points.append(point)

        logger.info(
            f"Upserting {len(points)} points into collection {self.collection_name} with source {source_link} and title {source_title}"
        )
        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )
        return points

    def upsert_extracted_ocr(self, chunks: List[str], file_metadata: Dict):
        embeddings = self.embedder.embed(chunks)
        points = []

        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            metadata = {
                **file_metadata,
                "chunk_index": idx,
                "total_chunks": len(chunks),
                "word_count": len(chunk.split()),
                "is_active": True,
            }

            unique_id = abs(
                hash(
                    f"{file_metadata.get('path', '')}_page_{file_metadata.get('page_number', 0)}_chunk_{idx}"
                )
            ) % (2**31)
            point = PointStruct(
                id=unique_id,
                vector=embedding,
                payload={
                    "text": chunk,
                    "file_path": file_metadata.get("path", ""),
                    "metadata": metadata,
                },
            )
            points.append(point)

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )
        return points

    def embed_file(self, file_path: str, metadata: Any = None):
        text = self._read_pdf(file_path)
        chunks = self.splitter.split(text)
        embeddings = self.embedder.embed(chunks)

        # Ensure metadata is a dict and add is_active
        enhanced_metadata = metadata if isinstance(metadata, dict) else {}
        enhanced_metadata["is_active"] = True

        points = [
            PointStruct(
                id=idx,
                vector=embedding,
                payload={
                    "text": chunk,
                    "file_path": file_path,
                    "metadata": enhanced_metadata,
                    "is_active": True,
                },
            )
            for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]
        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )
        return points

    def embed_json_chunks(
        self, json_chunks: List[Dict], source_link: str, source_title: str
    ):
        """
        Embed pre-chunked data from JSON file.

        Args:
            json_chunks: List of chunk dictionaries with 'content', 'title', 'metadata'
            source_link: URL source of the content
            source_title: Title for the source (used in frontend)
        """
        chunks_text = [chunk["content"] for chunk in json_chunks]
        embeddings = self.embedder.embed(chunks_text)

        points = []
        for idx, (chunk, embedding) in enumerate(zip(json_chunks, embeddings)):
            # Merge the original chunk metadata with source info
            enhanced_metadata = {
                **(chunk.get("metadata", {})),
                "source_link": source_link,
                "source_title": source_title,
                "chunk_title": chunk.get(
                    "title", f"Chunk {chunk.get('chunk_id', idx + 1)}"
                ),
                "is_web_source": True,
                "is_active": True,
            }

            points.append(
                PointStruct(
                    id=chunk.get("chunk_id", idx),
                    vector=embedding,
                    payload={
                        "text": chunk["content"],
                        "file_path": source_link,  # Use source link as file_path for compatibility
                        "metadata": enhanced_metadata,
                        "is_active": True,
                    },
                )
            )

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )
        return points

    def embed_ocr_results(
        self, ocr_data: Dict, file_metadata: Dict, chunk_threshold: int = 300
    ):
        """
        Embed OCR results with chunking based on word count threshold.

        Args:
            ocr_data: Dictionary containing OCR metadata and text
            file_metadata: Additional metadata extracted from file path
            chunk_threshold: Word count threshold for chunking text
        """
        text = ocr_data.get("text", "")
        ocr_metadata = ocr_data.get("metadata", {})

        # Count words in the text
        word_count = len(text.split())

        if word_count <= chunk_threshold:
            # Text is small enough, embed as single chunk
            chunks = [text]
        else:
            # Text is too large, split into chunks
            chunks = self.splitter.split(text)

        embeddings = self.embedder.embed(chunks)

        points = []
        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            # Combine OCR metadata with file metadata
            enhanced_metadata = {
                **file_metadata,
                "file_name": ocr_metadata.get("file_name", ""),
                "original_file_path": ocr_metadata.get("file_path", ""),
                "page_number": ocr_metadata.get("page_number", 1),
                "timestamp": ocr_metadata.get("timestamp", ""),
                "ocr_model": ocr_metadata.get("model", ""),
                "chunk_index": idx,
                "total_chunks": len(chunks),
                "word_count": len(chunk.split()),
                "is_web_source": False,
                "is_active": True,
            }

            # Generate unique ID based on file path and page number and chunk index
            # Use abs() to ensure positive ID and add timestamp to avoid collisions
            unique_id = abs(
                hash(
                    f"{ocr_metadata.get('file_path', '')}_{ocr_metadata.get('page_number', 1)}_{idx}_{ocr_metadata.get('timestamp', '')}"
                )
            ) % (2**63 - 1)

            points.append(
                PointStruct(
                    id=unique_id,
                    vector=embedding,
                    payload={
                        "text": chunk,
                        "file_path": ocr_metadata.get("file_path", ""),
                        "metadata": enhanced_metadata,
                        "is_active": True,
                    },
                )
            )

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )
        return points

    def retrieve(self, query: str, limit: int = None) -> List[Record]:
        """
        Retrieve sources from the collection based on the query.

        Args:
            query: The query to search for
            limit: The maximum number of results to return
        """
        if limit is None:
            limit = config.RETRIEVED_CHUNKS

        embedding = self.embedder.embed(query)

        # embedder.embed returns a list of embeddings [[]].
        # For search, we need a single embedding [].
        if embedding and isinstance(embedding, list) and isinstance(embedding[0], list):
            embedding = embedding[0]

        # Filter out points that are explicitly marked as inactive
        # Using must_not with is_active: False ensures we include points where is_active is True or missing
        query_filter = Filter(
            must_not=[
                FieldCondition(
                    key="is_active",
                    match=MatchValue(value=False),
                )
            ]
        )

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=embedding,
            limit=limit,
            with_payload=True,
            query_filter=query_filter,
        ).points
        return results

    def get_sources(self, sources_ids: List[int]) -> List[Record]:
        results = self.client.retrieve(
            collection_name=self.collection_name,
            ids=sources_ids,
            with_payload=True,
        )
        return results

    def toggle_source_status(self, file_path: str, is_active: bool):
        """
        Toggle the is_active status for all points associated with a file_path.
        """
        logger.info(f"Toggling status for {file_path} to is_active={is_active}")
        self.client.set_payload(
            collection_name=self.collection_name,
            payload={"is_active": is_active},
            points=Filter(
                must=[
                    FieldCondition(
                        key="file_path",
                        match=MatchValue(value=file_path),
                    )
                ]
            ),
        )
        return True
