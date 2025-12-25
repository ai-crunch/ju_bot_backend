import config
from utils.logger import get_logger

logger = get_logger(__name__)


class TextSplitter:
    def __init__(
        self,
        chunk_size: int = None,
        overlap: int = None,
        separator: str = " ",
    ):
        self.chunk_size = chunk_size or config.CHUNK_SIZE
        self.overlap = overlap if overlap is not None else config.CHUNK_OVERLAP
        self.separator = separator
        
        logger.info(
            f"Initializing TextSplitter with chunk_size={self.chunk_size}, overlap={self.overlap}, separator={self.separator}"
        )

    def split(self, text: str) -> list[str]:
        words = text.split()
        chunks = []
        # Calculate stride as chunk_size - overlap to ensure overlap between chunks
        stride = max(1, self.chunk_size - self.overlap)
        
        for i in range(0, len(words), stride):
            chunk_words = words[i : i + self.chunk_size]
            if not chunk_words:
                break
            chunks.append(self.separator.join(chunk_words))
            # If we've reached the end of the words, stop
            if i + self.chunk_size >= len(words):
                break
        return chunks
