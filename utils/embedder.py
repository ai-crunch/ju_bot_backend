from sentence_transformers import SentenceTransformer
import openai
import config
from utils.logger import get_logger

logger = get_logger(__name__)


class SparseEmbedder:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(SparseEmbedder, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_name: str = None):
        if self._initialized:
            return
        self.model_name = model_name or config.SPARSE_EMBEDDER["model_name"]
        self._model = None
        self._initialized = True

    def _load_model(self):
        if self._model is not None:
            return
        logger.info(f"Loading SparseEmbedder model {self.model_name}...")
        from fastembed import SparseTextEmbedding
        self._model = SparseTextEmbedding(model_name=self.model_name)
        logger.info("SparseEmbedder model loaded successfully")

    def embed(self, texts: list[str]) -> list[dict]:
        self._load_model()
        if isinstance(texts, str):
            texts = [texts]
        return list(self._model.embed(texts))


class Embedder:
    _instance = None

    # E5 model families that require explicit query/passage prefixes for
    # accurate cosine similarity.  Matching is done on a lowercase substring.
    _E5_MODEL_FAMILIES: tuple[str, ...] = ("e5",)

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Embedder, cls).__new__(cls)
            cls._instance._initialized = False
            cls._instance._model_loaded = False
        return cls._instance

    def __init__(self, provider: str = None, model_name: str = None):
        if self._initialized:
            return

        self.provider = provider or config.EMBEDDER["provider"]
        self.model_name = model_name or config.EMBEDDER["model_name"]
        self.dimension = config.EMBEDDER["dimension"]

        # Detect whether this model requires query/passage prefixes.
        self._requires_prefix = any(
            family in self.model_name.lower()
            for family in self._E5_MODEL_FAMILIES
        )

        logger.info(
            f"Embedder configured with provider {self.provider} and model "
            f"{self.model_name} (lazy load, requires_prefix={self._requires_prefix})"
        )

        self._initialized = True

    def _load_model(self):
        if self._model_loaded:
            return

        logger.info(
            f"Loading Embedder model {self.provider}/{self.model_name}..."
        )

        if self.provider == "huggingface":
            self.model = SentenceTransformer(self.model_name)
        elif self.provider == "openai":
            self.client = openai.OpenAI(api_key=config.OPENAI["api_key"])
        else:
            raise ValueError(f"Unsupported embedding provider: {self.provider}")

        self._model_loaded = True
        logger.info("Embedder model loaded successfully")

    def _apply_prefix(self, texts: list[str], is_query: bool) -> list[str]:
        """
        Prepend 'query: ' or 'passage: ' to each text for E5-family models.

        E5 models are trained with these prefixes and lose significant
        retrieval quality when they are omitted.  The prefix is only applied
        when ``self._requires_prefix`` is True (i.e. the model name contains
        'e5').  OpenAI embedding models do not require prefixes.
        """
        prefix = "query: " if is_query else "passage: "
        return [prefix + t for t in texts]

    @property
    def OUTPUT_SIZE(self) -> int:
        self._load_model()
        return self.dimension

    def embed(self, texts: list[str], is_query: bool = False) -> list[list[float]]:
        """
        Produce embedding vectors for a list of texts.

        Args:
            texts:    Strings to embed.
            is_query: Pass ``True`` when embedding a search query, ``False``
                      when embedding document passages for indexing.  This
                      controls the 'query: '/'passage: ' prefix for E5 models.
        """
        self._load_model()

        if isinstance(texts, str):
            texts = [texts]

        if self.provider == "huggingface":
            if self._requires_prefix:
                texts = self._apply_prefix(texts, is_query)
            embeddings = self.model.encode(texts, normalize_embeddings=True)
            return embeddings.tolist() if hasattr(embeddings, "tolist") else embeddings
        elif self.provider == "openai":
            # OpenAI models do not use query/passage prefixes.
            response = self.client.embeddings.create(input=texts, model=self.model_name)
            return [data.embedding for data in response.data]
        return []
