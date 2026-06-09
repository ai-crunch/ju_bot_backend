import hashlib
from typing import Any, List, Dict
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct, Record
from qdrant_client.models import (
    VectorParams,
    Distance,
    SparseVector,
    SparseVectorParams,
    SparseIndexParams,
    Filter,
    FieldCondition,
    MatchValue,
    Prefetch,
    FusionQuery,
    Fusion,
)
from utils.embedder import Embedder, SparseEmbedder
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
        # splitter is NOT cached here — it is constructed on-demand inside
        # embed_ocr_results so it always picks up the current config values
        # after a config.reload_config() call.
        self.collection_name = collection_name
        if not self.collection_exists(collection_name):
            self.create_collection()

        self._initialized = True

    def collection_exists(self, collection_name: str) -> bool:
        return self.client.collection_exists(collection_name)

    def _embed_both(self, chunks_text, is_query: bool = False):
        """Embed chunks for both dense and sparse indices.

        Pass ``is_query=True`` when embedding a search query so E5-family
        models receive the correct 'query: ' prefix instead of 'passage: '.
        """
        dense = self.embedder.embed(chunks_text, is_query=is_query)
        sparse = SparseEmbedder().embed(chunks_text)
        return dense, sparse

    @staticmethod
    def _dense_to_list(vec: Any) -> Any:
        return vec.tolist() if hasattr(vec, "tolist") else vec

    @staticmethod
    def _sparse_to_qdrant(vec: Any) -> Any:
        """
        fastembed returns SparseEmbedding objects; Qdrant expects SparseVector.
        Accept dicts as well to keep call-sites flexible.
        """
        if isinstance(vec, SparseVector):
            return vec
        if isinstance(vec, dict) and "indices" in vec and "values" in vec:
            return SparseVector(
                indices=list(vec["indices"]),
                values=list(vec["values"]),
            )
        if hasattr(vec, "indices") and hasattr(vec, "values"):
            indices = vec.indices.tolist() if hasattr(vec.indices, "tolist") else list(vec.indices)
            values = vec.values.tolist() if hasattr(vec.values, "tolist") else list(vec.values)
            return SparseVector(indices=indices, values=values)
        return vec

    @staticmethod
    def _stable_id(id_string: str) -> int:
        """
        Derive a deterministic 64-bit integer point ID from an arbitrary string.

        Uses the first 16 hex digits of SHA-256, which gives a stable unsigned
        64-bit value that is independent of PYTHONHASHSEED.  This means the same
        logical document always maps to the same Qdrant point ID across server
        restarts, making upsert idempotent and toggle/delete reliable.
        """
        return int(hashlib.sha256(id_string.encode()).hexdigest()[:16], 16)

    def create_collection(self):
        try:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.embedder.OUTPUT_SIZE, distance=Distance.COSINE
                ),
                sparse_vectors_config={
                    "sparse": SparseVectorParams(
                        index=SparseIndexParams(on_disk=True)
                    )
                },
            )
        except Exception as e:
            if "already exists" in str(e):
                logger.info(
                    f"Collection '{self.collection_name}' already exists — skipping creation."
                )
            else:
                raise

    def upsert_web_source(
        self,
        chunks: List[Dict],
        source_link: str,
        source_title: str,
    ):
        """
        Upsert web source data into the collection.
        """
        logger.info(f"Upserting web source data into collection {self.collection_name}")
        chunks_text = [chunk["content"] for chunk in chunks]
        embeddings, sparse_embeddings = self._embed_both(chunks_text)
        points = []

        for idx, (chunk, embedding, sparse) in enumerate(zip(chunks, embeddings, sparse_embeddings)):
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
                vector={
                    "": self._dense_to_list(embedding),
                    "sparse": self._sparse_to_qdrant(sparse),
                },
                payload={
                    "text": chunk["content"],
                    "file_path": source_link,
                    "metadata": metadata,
                    "is_active": True,
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

    def embed_ocr_results(
        self,
        ocr_data: Dict,
        file_metadata: Dict,
        chunk_threshold: int = None,
        use_semantic: bool = True,
    ):
        """
        Embed OCR results with chunking based on word count threshold.

        ``chunk_threshold`` defaults to ``config.OCR["chunk_threshold"]`` so it
        always reflects the current dynamic config after a reload_config() call.
        Callers may override it explicitly for testing or one-off ingestion.

        ``use_semantic`` controls whether the LegalSemanticSplitter is eligible
        for this document.  Pass ``False`` for non-legal department uploads so
        files that accidentally contain Arabic legal markers are not chunked as
        regulations.  The ``_looks_like_legal_text`` heuristic still acts as a
        second gate when ``use_semantic=True``.
        """
        if chunk_threshold is None:
            chunk_threshold = config.OCR["chunk_threshold"]

        text = ocr_data.get("text", "")
        ocr_metadata = ocr_data.get("metadata", {})

        word_count = len(text.split())

        if word_count <= chunk_threshold:
            chunks = [text]
        else:
            # Fresh instance on every call so chunk_size/overlap always reflect
            # the current config values, even after config.reload_config().
            # document_hierarchy feeds the LegalSemanticSplitter's context
            # injection when use_semantic=True.
            splitter = TextSplitter(
                chunk_size=config.CHUNK_SIZE,
                overlap=config.CHUNK_OVERLAP,
                use_semantic=use_semantic,
                document_hierarchy=file_metadata.get("source_title"),
            )
            chunks = splitter.split(text)

        embeddings, sparse_embeddings = self._embed_both(chunks)

        # Canonical document path: always taken from the caller-supplied file_metadata so
        # it is independent of whatever path was baked into the OCR cache file.
        canonical_file_path = file_metadata.get("path") or ocr_metadata.get("file_path", "")

        points = []
        for idx, (chunk, embedding, sparse) in enumerate(zip(chunks, embeddings, sparse_embeddings)):
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

            # Deterministic ID derived from stable fields only (no timestamp) so that
            # re-uploading the same file upserts existing points rather than creating
            # duplicates.  SHA-256-based so the value is stable across restarts
            # regardless of PYTHONHASHSEED.
            unique_id = self._stable_id(
                f"{canonical_file_path}_{ocr_metadata.get('page_number', 1)}_{idx}"
            )

            points.append(
                PointStruct(
                    id=unique_id,
                    vector={
                        "": self._dense_to_list(embedding),
                        "sparse": self._sparse_to_qdrant(sparse),
                    },
                    payload={
                        "text": chunk,
                        "file_path": canonical_file_path,
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


    def upsert_structured_chunks(
        self,
        structured_chunks: List[Dict[str, Any]],
        source_link: str,
        source_title: str,
    ):
        """
        Upsert semantic chunks (dicts with chunk_id, content, metadata, etc.)
        produced by LegalSemanticSplitter.
        """
        chunks_text = [chunk["content"] for chunk in structured_chunks]
        embeddings, sparse_embeddings = self._embed_both(chunks_text)
        points = []

        for idx, (chunk, embedding, sparse) in enumerate(zip(structured_chunks, embeddings, sparse_embeddings)):
            chunk_meta = chunk.get("metadata", {})
            enhanced_metadata = {
                **chunk_meta,
                "source_link": source_link,
                "source_title": source_title,
                "chunk_title": chunk_meta.get("source_section", f"Chunk {chunk.get('chunk_id', idx + 1)}"),
                "is_web_source": True,
                "is_active": True,
            }

            point = PointStruct(
                id=chunk.get("chunk_id", idx),
                vector={
                    "": self._dense_to_list(embedding),
                    "sparse": self._sparse_to_qdrant(sparse),
                },
                payload={
                    "text": chunk["content"],
                    "file_path": source_link,
                    "metadata": enhanced_metadata,
                    "is_active": True,
                },
            )
            points.append(point)

        logger.info(
            f"Upserting {len(points)} structured semantic chunks into collection {self.collection_name}"
        )
        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )
        return points

    def upsert_structured_ocr(
        self,
        structured_chunks: List[Dict[str, Any]],
        file_metadata: Dict,
    ):
        """
        Upsert semantic chunks from OCR results.
        """
        chunks_text = [chunk["content"] for chunk in structured_chunks]
        embeddings, sparse_embeddings = self._embed_both(chunks_text)
        points = []

        for idx, (chunk, embedding, sparse) in enumerate(zip(structured_chunks, embeddings, sparse_embeddings)):
            chunk_meta = chunk.get("metadata", {})
            unique_id = self._stable_id(
                f"{file_metadata.get('path', '')}_page_{file_metadata.get('page_number', 0)}_chunk_{chunk.get('chunk_id', idx)}"
            )

            enhanced_metadata = {
                **file_metadata,
                **chunk_meta,
                "chunk_index": chunk.get("chunk_id", idx),
                "total_chunks": len(structured_chunks),
                "is_active": True,
            }

            point = PointStruct(
                id=unique_id,
                vector={
                    "": self._dense_to_list(embedding),
                    "sparse": self._sparse_to_qdrant(sparse),
                },
                payload={
                    "text": chunk["content"],
                    "file_path": file_metadata.get("path", ""),
                    "metadata": enhanced_metadata,
                    "is_active": True,
                },
            )
            points.append(point)

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )
        return points

    def retrieve(self, query: str, limit: int = None) -> List[Record]:
        """
        Hybrid (dense + sparse) retrieval with optional reranking.

        The ``limit`` parameter acts as the final cap on returned results.
        When the reranker is active it also bounds how many candidates the
        reranker considers.  When the reranker is disabled, the raw RRF list is
        sliced to ``limit`` directly.

        The internal ``HYBRID_TOP_K`` config value controls how many candidates
        Qdrant returns before reranking; it should always be >= limit so the
        reranker has enough diversity to pick from.
        """
        if limit is None:
            limit = config.RETRIEVED_CHUNKS

        dense_vec = self.embedder.embed(query, is_query=True)
        if dense_vec and isinstance(dense_vec, list) and isinstance(dense_vec[0], list):
            dense_vec = dense_vec[0]

        sparse_vec = SparseEmbedder().embed(query)[0]
        sparse_vec = self._sparse_to_qdrant(sparse_vec)

        query_filter = Filter(
            must_not=[
                FieldCondition(
                    key="is_active",
                    match=MatchValue(value=False),
                )
            ]
        )

        # Fetch enough candidates for the reranker to have diversity.
        # Use the larger of HYBRID_TOP_K and the requested limit so callers
        # asking for more results than the default are handled correctly.
        hybrid_limit = max(config.HYBRID_TOP_K, limit)
        prefetch_limit = max(hybrid_limit // 2, 1)

        results = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=[
                Prefetch(query=dense_vec, using="", limit=prefetch_limit),
                Prefetch(query=sparse_vec, using="sparse", limit=prefetch_limit),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=hybrid_limit,
            with_payload=True,
            query_filter=query_filter,
        ).points

        # Reranker cap is bounded by both config.RERANK_TOP_K and the caller's
        # requested limit so the tool's limit parameter is finally respected.
        rerank_top_k = min(config.RERANK_TOP_K, limit)
        if config.RERANKER.get("enabled", True) and len(results) > rerank_top_k:
            from utils.reranker import Reranker
            reranker = Reranker()
            docs = [{"id": r.id, "text": r.payload.get("text", "")} for r in results]
            reranked = reranker.rerank(query, docs, top_k=rerank_top_k)
            reranked_ids = {doc["id"] for doc, _ in reranked}
            ordered = [r for r in results if r.id in reranked_ids]
            id_order = {doc["id"]: i for i, (doc, _) in enumerate(reranked)}
            ordered.sort(key=lambda r: id_order.get(r.id, 999))
            results = ordered
        else:
            results = results[:rerank_top_k]

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
