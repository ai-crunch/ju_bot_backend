from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class EmbeddingProvider(str, Enum):
    HUGGINGFACE = "huggingface"
    OPENAI = "openai"


class EmbeddingModel(str, Enum):
    # HuggingFace Models
    HF_E5_SMALL = "intfloat/multilingual-e5-small"
    HF_E5_LARGE = "intfloat/multilingual-e5-large"
    HF_E5_BASE = "intfloat/e5-base"
    HF_MINILM = "sentence-transformers/all-MiniLM-L6-v2"

    # OpenAI Models
    OA_TEXT_LARGE = "text-embedding-3-large"
    OA_TEXT_SMALL = "text-embedding-3-small"

    @property
    def dimension(self) -> int:
        dimensions = {
            EmbeddingModel.HF_E5_SMALL: 384,
            EmbeddingModel.HF_E5_LARGE: 1024,
            EmbeddingModel.HF_E5_BASE: 768,
            EmbeddingModel.HF_MINILM: 384,
            EmbeddingModel.OA_TEXT_LARGE: 3072,
            EmbeddingModel.OA_TEXT_SMALL: 1536,
        }
        return dimensions.get(self, 384)


class LLMProvider(str, Enum):
    OPENAI = "openai"


class LLMModel(str, Enum):
    GPT_4O = "gpt-4o"
    GPT_4O_MINI = "gpt-4o-mini"
    # GPT_4_TURBO = "gpt-4-turbo"
    # GPT_4 = "gpt-4"
    GPT_3_5_TURBO = "gpt-3.5-turbo"
    O1_MINI = "o1-mini"
    # O1_PREVIEW = "o1-preview"
    GPT_5_2 = "gpt-5.2"
    GPT_5 = "gpt-5"
    GPT_5_MINI = "gpt-5-mini"
    GPT_5_1 = "gpt-5.1"


class EmbeddingConfig(BaseModel):
    provider: EmbeddingProvider = EmbeddingProvider.HUGGINGFACE
    model_name: EmbeddingModel = EmbeddingModel.HF_E5_SMALL

    @classmethod
    def get_provider_options(cls) -> Dict[str, List[str]]:
        return {
            EmbeddingProvider.HUGGINGFACE: [
                EmbeddingModel.HF_E5_SMALL,
                EmbeddingModel.HF_E5_LARGE,
                EmbeddingModel.HF_E5_BASE,
                EmbeddingModel.HF_MINILM,
            ],
            EmbeddingProvider.OPENAI: [
                EmbeddingModel.OA_TEXT_LARGE,
                EmbeddingModel.OA_TEXT_SMALL,
            ],
        }


class RetrievalConfig(BaseModel):
    chunk_size: int = 300
    chunk_overlap: int = 50
    retrieved_chunks: int = 5
    chunk_threshold: int = 300


class LLMConfig(BaseModel):
    provider: LLMProvider = LLMProvider.OPENAI
    model: LLMModel = LLMModel.GPT_4O_MINI
    temperature: float = 0.0
    api_key: Optional[str] = None

    @classmethod
    def get_provider_options(cls) -> Dict[str, List[str]]:
        return {
            LLMProvider.OPENAI: [
                LLMModel.GPT_4O,
                LLMModel.GPT_4O_MINI,
                # LLMModel.GPT_4_TURBO,
                # LLMModel.GPT_4,
                # LLMModel.GPT_3_5_TURBO,
                # LLMModel.O1_MINI,
                # LLMModel.O1_PREVIEW,
                LLMModel.GPT_5_2,
                # LLMModel.GPT_5,
                # LLMModel.GPT_5_MINI,
                LLMModel.GPT_5_1,
            ],
        }


class VectorDBConfig(BaseModel):
    host: str = "localhost"
    port: int = 6333
    collection_name: str = "ju_bot_vdb_with_ocr_test_generator"


class SystemFlags(BaseModel):
    maintenance_mode: bool = False
    debug: bool = False
    enable_ocr: bool = False
    enable_reasoning: bool = False


class SystemConfig(BaseModel):
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    vector_db: VectorDBConfig = Field(default_factory=VectorDBConfig)
    system_flags: SystemFlags = Field(default_factory=SystemFlags)


def get_system_config_from_db() -> Dict[str, Any]:
    """
    Helper to fetch the current system configuration from MongoDB.
    Uses a local import to avoid circular dependencies with config.py.
    """
    try:
        from models.database import MongoDB

        db = MongoDB.get_db()
        config_doc = db["system_config"].find_one({"config_id": "main_config"})
        if config_doc:
            # Remove MongoDB internal _id
            config_doc.pop("_id", None)
            config_doc.pop("config_id", None)
            return config_doc
    except Exception as e:
        logger.error(f"Failed to fetch config from MongoDB: {e}")

    return {}


def load_config() -> SystemConfig:
    """
    Loads configuration from DB with safe defaults.
    """
    db_data = get_system_config_from_db()
    return SystemConfig(**db_data)


def update_system_config(config_data: Dict[str, Any]) -> bool:
    """
    Updates the system configuration in MongoDB.
    """
    try:
        from models.database import MongoDB

        db = MongoDB.get_db()
        # Filter out None values to avoid overwriting with nulls if not provided
        # But for settings, we usually want to replace the whole document or use model_dump
        db["system_config"].update_one(
            {"config_id": "main_config"}, {"$set": config_data}, upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Failed to update config in MongoDB: {e}")
        return False
