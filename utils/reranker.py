from typing import List, Tuple, Dict
from utils.logger import get_logger
import config

logger = get_logger(__name__)


class Reranker:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Reranker, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_name: str = None, device: str = None):
        if self._initialized:
            return
        self.model_name = model_name or config.RERANKER["model_name"]
        self.device = device or config.RERANKER["device"]
        self._model = None
        self._initialized = True

    def _load_model(self):
        if self._model is not None:
            return
        logger.info(f"Loading Reranker model {self.model_name} on {self.device}...")
        from FlagEmbedding import FlagReranker
        self._model = FlagReranker(
            self.model_name,
            use_fp16=(self.device == "cuda"),
            device=self.device,
        )
        logger.info("Reranker model loaded successfully")

    def rerank(
        self, query: str, documents: List[Dict], top_k: int = 5
    ) -> List[Tuple[Dict, float]]:
        if not config.RERANKER.get("enabled", True):
            return [(doc, 0.0) for doc in documents[:top_k]]
        if not documents:
            return []
        self._load_model()
        pairs = [(query, doc["text"]) for doc in documents]
        scores = self._model.compute_score(pairs, normalize=True)
        scored = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)
        return scored[:top_k]
