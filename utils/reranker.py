from typing import List, Tuple, Dict
from utils.logger import get_logger
import config

logger = get_logger(__name__)


class Reranker:
    """
    Cross-encoder reranker backed by sentence_transformers.CrossEncoder.

    Uses CrossEncoder instead of FlagEmbedding.FlagReranker to avoid the
    ``XLMRobertaTokenizer has no attribute prepare_for_model`` error that
    appears with newer versions of the transformers library.  CrossEncoder
    supports the same BAAI/bge-reranker-v2-m3 checkpoint and produces
    identical scores.
    """

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
        from sentence_transformers import CrossEncoder
        self._model = CrossEncoder(
            self.model_name,
            device=self.device,
            model_kwargs={"ignore_mismatched_sizes": True},
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
        raw_scores = self._model.predict(pairs)
        # Normalise to [0, 1] via sigmoid so scores are comparable across runs.
        import math
        def _sigmoid(x: float) -> float:
            return 1.0 / (1.0 + math.exp(-x))
        scores = [_sigmoid(float(s)) for s in raw_scores]
        scored = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)
        return scored[:top_k]
