import os
import fitz
import json
from typing import Any, List, Dict
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct
from qdrant_client.models import VectorParams, Distance

from utils.embedder import Embedder
from utils.splitter import TextSplitter

import config


class QdrantVDB:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        collection_name: str = config.QDRANT["collection_name"],
    ):
        print(
            f"Initializing QdrantVDB with host={host}, port={port}, collection_name={collection_name}"
        )
        self.client = QdrantClient(host=host, port=port)
        self.embedder = Embedder()
        self.splitter = TextSplitter(chunk_size=250, overlap=50)
        self.collection_name = collection_name
        if not self.collection_exists(collection_name):
            self.create_collection()

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
                size=Embedder.OUTPUT_SIZE, distance=Distance.COSINE
            ),
        )

    def embed_file(self, file_path: str, metadata: Any = None):
        text = self._read_pdf(file_path)
        chunks = self.splitter.split(text)
        embeddings = self.embedder.embed(chunks)
        points = [
            PointStruct(
                id=idx,
                vector=embedding,
                payload={"text": chunk, "file_path": file_path, "metadata": metadata},
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
            }

            points.append(
                PointStruct(
                    id=chunk.get("chunk_id", idx),
                    vector=embedding,
                    payload={
                        "text": chunk["content"],
                        "file_path": source_link,  # Use source link as file_path for compatibility
                        "metadata": enhanced_metadata,
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
                    },
                )
            )

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )
        return points

    def retrieve(self, question: str):
        embedding = self.embedder.embed(question)
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=embedding,
            limit=5,
            with_payload=True,
        )
        return results
