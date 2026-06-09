from typing import Optional, Dict, Any

import config
from utils.logger import get_logger
from utils.semantic_splitter import LegalSemanticSplitter, SplitterSettings

logger = get_logger(__name__)


class TextSplitter:
    """
    Backward-compatible wrapper that defaults to the new LegalSemanticSplitter.

    If ``use_semantic=True`` (the default when chunk_size >= 300), the splitter
    will use the legal-aware semantic chunker that respects sentence boundaries,
    legal article headers, and injects hierarchical context.

    If ``use_semantic=False`` the legacy word-level sliding window is used.
    """

    def __init__(
        self,
        chunk_size: int = None,
        overlap: int = None,
        separator: str = " ",
        use_semantic: bool = True,
        semantic_settings: Optional[Dict[str, Any]] = None,
        document_hierarchy: Optional[str] = None,
    ):
        self.chunk_size = chunk_size or config.CHUNK_SIZE
        self.overlap = overlap if overlap is not None else config.CHUNK_OVERLAP
        self.separator = separator
        self.use_semantic = use_semantic
        self.document_hierarchy = document_hierarchy

        # If semantic settings are not provided, derive sensible defaults from
        # the legacy chunk_size / overlap values so that existing configs still work.
        if semantic_settings is None:
            semantic_settings = {
                "max_chunk_word_count": max(self.chunk_size, 600),
                "target_chunk_word_count": max(self.chunk_size - self.overlap, 350),
                "min_chunk_word_count": max(self.chunk_size // 4, 150),
                "enforce_sentence_boundaries": True,
                "context_injection_enabled": True,
            }

        self.semantic_splitter = LegalSemanticSplitter(SplitterSettings.from_dict(semantic_settings))

        logger.info(
            f"Initializing TextSplitter (semantic={self.use_semantic}) with "
            f"chunk_size={self.chunk_size}, overlap={self.overlap}"
        )

    def split(self, text: str) -> list[str]:
        """
        Returns a list of raw content strings.

        If semantic mode is enabled and the text looks like it contains legal
        articles (المادة / البند / الفقرة etc.) the legal semantic splitter is
        used.  Otherwise we fall back to the legacy word-level splitter so that
        general prose is still handled efficiently.
        """
        if self.use_semantic and self._looks_like_legal_text(text):
            return self.semantic_splitter.split_to_strings(text, self.document_hierarchy)

        # Legacy sliding-window word splitter
        words = text.split()
        chunks = []
        stride = max(1, self.chunk_size - self.overlap)
        for i in range(0, len(words), stride):
            chunk_words = words[i : i + self.chunk_size]
            if not chunk_words:
                break
            chunks.append(self.separator.join(chunk_words))
            if i + self.chunk_size >= len(words):
                break
        return chunks

    def split_structured(self, text: str) -> list[Dict[str, Any]]:
        """
        Returns full semantic chunks as dicts with metadata.
        This is the preferred API for new ingestion pipelines.
        """
        if self.use_semantic:
            return self.semantic_splitter.split(text, self.document_hierarchy)
        # If legacy mode, still wrap the strings in the same schema
        strings = self.split(text)
        return [
            {
                "chunk_id": idx + 1,
                "context_summary": "",
                "content": s,
                "metadata": {
                    "source_section": "",
                    "keywords": [],
                    "word_count": len(s.split()),
                },
            }
            for idx, s in enumerate(strings)
        ]

    @staticmethod
    def _looks_like_legal_text(text: str) -> bool:
        """Heuristic: does the text contain legal headers?"""
        # Quick check for common Arabic legal markers
        legal_markers = ["المادة", "البند", "الفقرة", "الفصل", "الباب", "القسم"]
        text_head = text[:5000]  # only inspect first 5k chars for speed
        return any(marker in text_head for marker in legal_markers)
