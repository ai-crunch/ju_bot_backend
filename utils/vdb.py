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

    def retrieve(self, question: str):
        embedding = self.embedder.embed(question)
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=embedding,
            limit=5,
            with_payload=True,
        )
        return results
