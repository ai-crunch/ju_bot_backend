import dotenv
import os

dotenv.load_dotenv()

# --- Static Config (Required for Bootstrap) ---
DATA_DIR_PATH = os.path.join("data")

LOGGER = {
    "path": os.path.join("logs"),
}

MONGODB = {
    "host": os.getenv("MONGO_HOST", "localhost"),
    "port": int(os.getenv("MONGO_PORT", 27017)),  # Default to standard MongoDB port
    "username": os.getenv("MONGO_ROOT_USERNAME", "admin"),
    "password": os.getenv("MONGO_ROOT_PASSWORD", "password"),
    "database": os.getenv("MONGO_DATABASE", "ju_bot_feedback"),
    "collection": "feedback_data",
}
MONGO_CONNECTION_STRING = f"mongodb://{MONGODB['username']}:{MONGODB['password']}@{MONGODB['host']}:{MONGODB['port']}/{MONGODB['database']}?authSource=admin"

# --- Dynamic Config (Loaded from MongoDB) ---


def _load_dynamic_config():
    """
    Loads dynamic configuration from MongoDB with safe defaults.
    """
    try:
        from models.admin.system_config import load_config

        return load_config()
    except Exception as e:
        # This can happen during initial setup or if MongoDB is not reachable
        print(f"⚠️ Warning: Failed to load dynamic config from DB: {e}. Using defaults.")
        try:
            from models.admin.system_config import SystemConfig

            return SystemConfig()
        except ImportError:
            # Fallback if even the model cannot be imported
            return None


def reload_config():
    """
    Hot-reloads the configuration from MongoDB.
    """
    global _config, QDRANT, EMBEDDER, OPENAI, OCR, CHUNK_SIZE, CHUNK_OVERLAP, RETRIEVED_CHUNKS, SYSTEM_FLAGS, ENABLE_REASONING, SEMANTIC_CACHE, SYSTEM_INSTRUCTIONS, MAX_TOKENS, SEMANTIC_CHUNKING, HYBRID_TOP_K, RERANK_TOP_K, RERANKER, SPARSE_EMBEDDER

    _config = _load_dynamic_config()

    if _config:
        # Legacy Structure Mapping (for backward compatibility)
        # Prioritize environment variables for host/port (needed for Docker service names)
        QDRANT = {
            "host": os.getenv("QDRANT_HOST", _config.vector_db.host),
            "port": int(os.getenv("QDRANT_PORT", str(_config.vector_db.port))),
            "collection_name": os.getenv("QDRANT_COLLECTION_NAME", _config.vector_db.collection_name),
        }

        # Ensure Enum values are converted to raw strings/values
        EMBEDDER = {
            "provider": str(_config.embedding.provider.value),
            "model_name": str(_config.embedding.model_name.value),
            "dimension": (
                _config.embedding.model_name.dimension
                if hasattr(_config.embedding.model_name, "dimension")
                else 384
            ),
        }

        OPENAI = {
            "provider": str(_config.llm.provider.value),
            "model": str(_config.llm.model.value),
            "temperature": _config.llm.temperature,
            "api_key": _config.llm.api_key or os.getenv("OPENAI_API_KEY"),
        }

        OCR = {
            "results_dir": "ocr_results",
            "chunk_threshold": _config.retrieval.chunk_threshold,
        }

        CHUNK_SIZE = _config.retrieval.chunk_size
        CHUNK_OVERLAP = _config.retrieval.chunk_overlap
        RETRIEVED_CHUNKS = _config.retrieval.retrieved_chunks
        HYBRID_TOP_K = _config.retrieval.hybrid_top_k
        RERANK_TOP_K = _config.retrieval.rerank_top_k
        RERANKER = {
            "enabled": _config.retrieval.enable_reranker,
            "model_name": os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3"),
            "device": os.getenv("RERANKER_DEVICE", "cpu"),
        }
        SPARSE_EMBEDDER = {
            "provider": "fastembed",
            "model_name": os.getenv("SPARSE_EMBEDDER_MODEL", "Qdrant/bm25"),
        }

        # Semantic Chunking (new legal-aware pipeline)
        SEMANTIC_CHUNKING = (
            _config.semantic_chunking.model_dump()
            if hasattr(_config.semantic_chunking, "model_dump")
            else _config.semantic_chunking.dict()
        )

        # System Flags
        SYSTEM_FLAGS = (
            _config.system_flags.model_dump()
            if hasattr(_config.system_flags, "model_dump")
            else _config.system_flags.dict()
        )
        ENABLE_REASONING = _config.system_flags.enable_reasoning

        # Semantic Cache
        SEMANTIC_CACHE = {
            "enabled": _config.semantic_cache.enabled,
            "similarity_threshold": _config.semantic_cache.similarity_threshold,
            "feedback_ratio": _config.semantic_cache.feedback_ratio,
        }

        # Agent / LLM extras
        SYSTEM_INSTRUCTIONS = _config.system_instructions
        MAX_TOKENS = _config.llm.max_tokens
    else:
        # Hardcoded defaults as a last resort
        QDRANT = {
            "host": os.getenv("QDRANT_HOST", "localhost"),
            "port": int(os.getenv("QDRANT_PORT", 6333)),
            "collection_name": os.getenv("QDRANT_COLLECTION_NAME", "ju_bot_vdb_with_ocr_test_generator"),
        }
        EMBEDDER = {
            "provider": "huggingface",
            "model_name": "intfloat/multilingual-e5-small",
            "dimension": 384,
        }
        OPENAI = {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.0,
            "api_key": os.getenv("OPENAI_API_KEY"),
        }
        OCR = {
            "results_dir": "ocr_results",
            "chunk_threshold": 300,
        }
        CHUNK_SIZE = 500
        CHUNK_OVERLAP = 50
        RETRIEVED_CHUNKS = 20
        HYBRID_TOP_K = 20
        RERANK_TOP_K = 5
        RERANKER = {"enabled": True, "model_name": "BAAI/bge-reranker-v2-m3", "device": "cpu"}
        SPARSE_EMBEDDER = {"provider": "fastembed", "model_name": "Qdrant/bm25"}
        SEMANTIC_CHUNKING = {
            "enabled": True,
            "max_chunk_word_count": 600,
            "target_chunk_word_count": 350,
            "min_chunk_word_count": 150,
            "language_of_output": "Arabic",
            "context_injection_enabled": True,
            "hierarchy_delimiter": " -> ",
            "enforce_sentence_boundaries": True,
        }
        SYSTEM_FLAGS = {"enable_reasoning": False}
        ENABLE_REASONING = False
        SEMANTIC_CACHE = {
            "enabled": True,
            "similarity_threshold": 0.90,
            "feedback_ratio": 1.30,
        }
        SYSTEM_INSTRUCTIONS = None
        MAX_TOKENS = 4096


# Initialize dynamic config
_config = None
reload_config()
