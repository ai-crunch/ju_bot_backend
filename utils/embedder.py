from sentence_transformers import SentenceTransformer


class Embedder:

    OUTPUT_SIZE = 384

    def __init__(self, model_name: str = "intfloat/multilingual-e5-small"):
        print(f"Initializing Embedder with model {model_name}")
        self.model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        print(f"Embedding {len(texts)} texts")
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        print(f"Embedded {len(embeddings)} texts")
        return embeddings
