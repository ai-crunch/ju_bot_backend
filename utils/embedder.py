from sentence_transformers import SentenceTransformer
import openai
import config
from utils.logger import get_logger

logger = get_logger(__name__)


class Embedder:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Embedder, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, provider: str = None, model_name: str = None):
        if self._initialized:
            return

        self.provider = provider or config.EMBEDDER["provider"]
        self.model_name = model_name or config.EMBEDDER["model_name"]
        self.dimension = config.EMBEDDER["dimension"]

        logger.info(
            f"Initializing Embedder with provider {self.provider} and model {self.model_name}"
        )

        if self.provider == "huggingface":
            self.model = SentenceTransformer(self.model_name)
        elif self.provider == "openai":
            self.client = openai.OpenAI(api_key=config.OPENAI["api_key"])
        else:
            raise ValueError(f"Unsupported embedding provider: {self.provider}")

        self._initialized = True

    @property
    def OUTPUT_SIZE(self) -> int:
        return self.dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        if isinstance(texts, str):
            texts = [texts]

        if self.provider == "huggingface":
            embeddings = self.model.encode(texts, normalize_embeddings=True)
            return embeddings.tolist() if hasattr(embeddings, "tolist") else embeddings
        elif self.provider == "openai":
            response = self.client.embeddings.create(input=texts, model=self.model_name)
            return [data.embedding for data in response.data]
        return []
