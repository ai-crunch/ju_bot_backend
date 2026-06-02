"""
LegalSemanticSplitter: Production-grade semantic chunking for Arabic legal
and academic university documents. Respects sentence boundaries, legal article
boundaries, and injects hierarchical context.

This module is designed to solve the core problem of the old word-based
sliding-window splitter: cutting legal articles and sentences in half,
losing referential pronouns and structural meaning.
"""

from __future__ import annotations

import re
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Arabic stop-words for lightweight keyword extraction
ARABIC_STOP_WORDS: set = {
    "في", "من", "إلى", "على", "أن", "التي", "الذي", "التي", "الذين",
    "و", "أو", "ثم", "بل", "لكن", "لذلك", "لهذا", "بسبب", "حيث", "إذا",
    "كما", "حتى", "عند", "بين", "بعد", "قبل", "تحت", "فوق", "دون",
    "جميع", "كل", "بعض", "غير", "لا", "لم", "لن", "ما", "لا", "ليس",
    "هذا", "هذه", "ذلك", "تلك", "هؤلاء", "أولئك", "هنا", "هناك",
    "أي", "إما", "سوى", "عما", "مما", "لما", "كيف", "متى", "أين", "منذ",
    "إن", "قد", "لقد", "كان", "يكون", "أصبح", "أضحى", "ظل", "ما زال",
    "لا يزال", "لا يزال", "بد", "يجب", "يجوز", "يحق", "يعتبر", "يمنع",
    "يسمح", "المادة", "البند", "الفقرة", "الجامعة", "النظام", "القانون",
    "أحكام", "أحكام", "أحكام", "حكم", "أحكام", "حكمه", "أحكام",
    "يجوز", "يجب", "لا يجوز", "لا يجب", "لا",
}

# Common Arabic academic/legal abbreviations that end with a dot but are NOT
# sentence boundaries.
ABBREVIATIONS: List[str] = [
    r"[دأ]\.?",           # د. / أ.
    r"[دم]\.?",           # د.م. / م.
    r"[دم]\.?[م]?\.?",    # د.م.م. / د.م.
    r"أ\.?[د]?\.?",      # أ.د.
    r"[تش]\.?[ن]?\.?",   # ت.ن / ش.ن
    r"ع\.?[ن]?\.?",      # ع.ن
    r"ص\.?[ن]?\.?",      # ص.ن
    r"ر\.?[ن]?\.?",      # ر.ن
    r"ر\.?[ق]?\.?م?\.?",  # رقم / ر.ق.
    r"س\.?[ن]?\.?",      # س.ن
    r"م\.?[ت]?\.?",      # م.ت
    r"ش\.?[ع]?\.?",      # ش.ع
    r"ط\.?[ب]?\.?",      # ط.ب
    r"و\.?[ر]?\.?",      # و.ر
]

# Regex to detect legal article / paragraph / section headers.
# Examples: "المادة (5)", "البند (أ)", "الفقرة (2)", "الفصل الأول", "الباب الثاني"
ARTICLE_HEADER_RE = re.compile(
    r"(?:^|\n)\s*(المادة|البند|الفقرة|الفصل|الباب|القسم|الشروط|التعريفات)"
    r"\s*[(\[]?\s*([٠١٢٣٤٥٦٧٨٩0-9\u0600-\u06FF]+)\s*[)\]]?"
    r"\s*[:\-]?",
    re.MULTILINE | re.UNICODE,
)

# Broader header for hierarchical extraction (can also catch roman numerals etc.)
SECTION_HEADER_RE = re.compile(
    r"(?:^|\n)\s*(الفصل|الباب|القسم|الشروط|التعريفات|المقدمة|الخاتمة)"
    r"\s*([٠-٩0-9\u0600-\u06FF\s]+)?\s*[:\-]?",
    re.MULTILINE | re.UNICODE,
)

# Sentence terminators in Arabic / mixed Arabic-English texts.
# We keep `:` as a weak terminator only when followed by a newline or bullet.
SENTENCE_TERMINATORS = r".؟!"

# Pattern to split sentences while protecting abbreviations.
# We build a negative lookbehind dynamically based on abbreviations.
_abbrev_pattern = "|".join(f"(?:{abbr})" for abbr in ABBREVIATIONS)

# The core sentence splitter regex.
# Because Python's re engine requires fixed-width lookbehinds, we handle
# abbreviation protection by temporarily replacing them with placeholders
# inside _split_to_sentences() instead of using a lookbehind here.
SENTENCE_SPLIT_RE = re.compile(
    rf"[{SENTENCE_TERMINATORS}](?=\s+\w)",
    re.UNICODE,
)

# Weak split on `؛` (semicolon) only when followed by newline or capital/start
SEMICOLON_SPLIT_RE = re.compile(
    r"؛\s*(?=\n|\s*[٠-٩0-9A-Z\u0600-\u06FF])",
    re.UNICODE,
)

# Bullet / numbered list markers
BULLET_RE = re.compile(
    r"(?:^|\n)\s*[-\*•\u2022\u25E6\u25AA]\s+",
    re.MULTILINE | re.UNICODE,
)
NUMBERED_LIST_RE = re.compile(
    r"(?:^|\n)\s*[(\[]?\s*([٠-٩0-9]+|[a-zA-Z]|[أ-ي])\s*[.\-)]\s+",
    re.MULTILINE | re.UNICODE,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SemanticChunk:
    """Represents a single semantic chunk ready for embedding and storage."""

    chunk_id: int
    context_summary: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "context_summary": self.context_summary,
            "content": self.content,
            "metadata": self.metadata,
        }


@dataclass
class SplitterSettings:
    """Dynamic settings for semantic splitting."""

    max_chunk_word_count: int = 600
    target_chunk_word_count: int = 350
    min_chunk_word_count: int = 150
    language_of_output: str = "Arabic"
    context_injection_enabled: bool = True
    hierarchy_delimiter: str = " -> "
    enforce_sentence_boundaries: bool = True

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SplitterSettings":
        return cls(
            max_chunk_word_count=d.get("max_chunk_word_count", 600),
            target_chunk_word_count=d.get("target_chunk_word_count", 350),
            min_chunk_word_count=d.get("min_chunk_word_count", 150),
            language_of_output=d.get("language_of_output", "Arabic"),
            context_injection_enabled=d.get("context_injection_enabled", True),
            hierarchy_delimiter=d.get("hierarchy_delimiter", " -> "),
            enforce_sentence_boundaries=d.get("enforce_sentence_boundaries", True),
        )


# ---------------------------------------------------------------------------
# Core splitter class
# ---------------------------------------------------------------------------

class LegalSemanticSplitter:
    """
    Splits raw Arabic/English university legal text into semantic chunks.

    Key guarantees:
    1. A legal article / paragraph smaller than max_chunk_word_count is NEVER cut.
    2. Sentence boundaries are respected when enforce_sentence_boundaries=True.
    3. Context injection prefixes each chunk with its hierarchical path.
    4. Keywords are extracted per chunk without any external LLM call.
    """

    def __init__(self, settings: Optional[SplitterSettings] = None):
        self.settings = settings or SplitterSettings()
        logger.info(
            f"LegalSemanticSplitter initialised: max={self.settings.max_chunk_word_count}, "
            f"target={self.settings.target_chunk_word_count}, min={self.settings.min_chunk_word_count}, "
            f"enforce_sentences={self.settings.enforce_sentence_boundaries}"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def split(
        self,
        text: str,
        document_hierarchy: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Main entry point.

        Args:
            text: Raw text from PDF / OCR / web scraping.
            document_hierarchy: Optional top-level hierarchy string, e.g.
                "الجامعة الأردنية -> نظام تأديب الطلبة".

        Returns:
            List of dicts compatible with the JSON schema required by Qdrant upsert.
        """
        if not text or not text.strip():
            return []

        # 1. Normalise whitespace
        text = self._normalise_whitespace(text)

        # 2. Detect legal articles / sections
        units = self._detect_legal_units(text)

        # 3. Build semantic chunks from units
        chunks = self._build_chunks(units, document_hierarchy or "")

        # 4. Post-process: ensure no sentence mid-cut, add metadata
        final_chunks = self._post_process_chunks(chunks)

        logger.info(
            f"Split {len(text.split())} words into {len(final_chunks)} semantic chunks."
        )
        return [c.to_dict() for c in final_chunks]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_whitespace(text: str) -> str:
        # Collapse multiple spaces/newlines but preserve paragraph breaks
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _detect_legal_units(self, text: str) -> List[Dict[str, Any]]:
        """
        Splits text into 'legal units' — each unit starts at a legal header
        (e.g. المادة 5) and ends just before the next legal header.
        Units that are NOT preceded by a header become a leading 'preamble' unit.
        """
        units: List[Dict[str, Any]] = []
        last_end = 0

        for match in ARTICLE_HEADER_RE.finditer(text):
            start = match.start()
            # Capture any text before this header as a preamble or previous unit tail
            if start > last_end:
                preamble = text[last_end:start].strip()
                if preamble:
                    units.append({
                        "type": "preamble",
                        "header": None,
                        "header_label": None,
                        "text": preamble,
                    })
            # This unit itself
            unit_text = text[start:]
            # Find where the NEXT header starts
            next_match = ARTICLE_HEADER_RE.search(unit_text, pos=1)
            if next_match:
                unit_text = unit_text[: next_match.start()].strip()
            else:
                unit_text = unit_text.strip()

            header_label = match.group(1)  # e.g. المادة
            header_number = match.group(2) or ""  # e.g. 5

            units.append({
                "type": "legal_unit",
                "header": f"{header_label} {header_number}".strip(),
                "header_label": header_label,
                "text": unit_text,
            })
            last_end = start + len(unit_text)

        # Tail
        if last_end < len(text):
            tail = text[last_end:].strip()
            if tail:
                units.append({
                    "type": "preamble",
                    "header": None,
                    "header_label": None,
                    "text": tail,
                })

        # If no legal headers were found, treat the whole text as one preamble unit
        if not units:
            units.append({
                "type": "preamble",
                "header": None,
                "header_label": None,
                "text": text,
            })

        return units

    def _build_chunks(
        self,
        units: List[Dict[str, Any]],
        document_hierarchy: str,
    ) -> List[SemanticChunk]:
        """
        Build SemanticChunk objects from legal units while respecting size bounds.
        """
        chunks: List[SemanticChunk] = []
        current_buffer: List[str] = []
        current_headers: List[str] = []
        current_word_count = 0
        chunk_counter = 1

        for unit in units:
            unit_text = unit["text"]
            unit_words = len(unit_text.split())
            unit_header = unit.get("header")

            # --- Rule 1: Unit fits entirely inside max_chunk_word_count ---
            if unit_words <= self.settings.max_chunk_word_count:
                # If adding it would exceed max, flush buffer first
                if current_buffer and (current_word_count + unit_words) > self.settings.max_chunk_word_count:
                    flushed = self._flush_buffer(
                        current_buffer, current_headers, document_hierarchy, chunk_counter
                    )
                    chunks.append(flushed)
                    chunk_counter += 1
                    current_buffer = []
                    current_headers = []
                    current_word_count = 0

                # Append unit to buffer
                current_buffer.append(unit_text)
                if unit_header:
                    current_headers.append(unit_header)
                current_word_count += unit_words

                # If buffer now exceeds target, consider flushing (but not below min)
                if current_word_count >= self.settings.target_chunk_word_count:
                    # Only flush if we are above target AND next unit would push us over max
                    # OR if we are well above target (>= max)
                    if current_word_count >= self.settings.max_chunk_word_count:
                        flushed = self._flush_buffer(
                            current_buffer, current_headers, document_hierarchy, chunk_counter
                        )
                        chunks.append(flushed)
                        chunk_counter += 1
                        current_buffer = []
                        current_headers = []
                        current_word_count = 0
                continue

            # --- Rule 2: Unit is longer than max -> sentence-level split ---
            # First flush any existing buffer
            if current_buffer:
                flushed = self._flush_buffer(
                    current_buffer, current_headers, document_hierarchy, chunk_counter
                )
                chunks.append(flushed)
                chunk_counter += 1
                current_buffer = []
                current_headers = []
                current_word_count = 0

            # Split oversized unit by sentences
            sentence_chunks = self._split_long_unit(unit_text, unit_header)
            for sent_chunk_text in sentence_chunks:
                sent_words = len(sent_chunk_text.split())
                # If a single sentence itself exceeds max, we have no choice but to keep it
                # as-is (better than cutting mid-sentence)
                if current_buffer and (current_word_count + sent_words) > self.settings.max_chunk_word_count:
                    flushed = self._flush_buffer(
                        current_buffer, current_headers, document_hierarchy, chunk_counter
                    )
                    chunks.append(flushed)
                    chunk_counter += 1
                    current_buffer = []
                    current_headers = []
                    current_word_count = 0

                current_buffer.append(sent_chunk_text)
                if unit_header:
                    current_headers.append(unit_header)
                current_word_count += sent_words

                # If we hit target, flush
                if current_word_count >= self.settings.target_chunk_word_count:
                    flushed = self._flush_buffer(
                        current_buffer, current_headers, document_hierarchy, chunk_counter
                    )
                    chunks.append(flushed)
                    chunk_counter += 1
                    current_buffer = []
                    current_headers = []
                    current_word_count = 0

        # Flush remaining buffer
        if current_buffer:
            flushed = self._flush_buffer(
                current_buffer, current_headers, document_hierarchy, chunk_counter
            )
            chunks.append(flushed)

        return chunks

    def _split_long_unit(self, text: str, header: Optional[str]) -> List[str]:
        """
        Split an oversized legal unit into sentence-level sub-chunks.
        If enforce_sentence_boundaries is True, we only cut at sentence ends.
        """
        if not self.settings.enforce_sentence_boundaries:
            # Fall back to word-level chunking for this unit (last resort)
            return self._word_chunk_text(text)

        # 1. Protect abbreviations, split by sentence terminators
        sentences = self._split_to_sentences(text)

        # 2. Group sentences into sub-chunks that stay within max
        sub_chunks: List[str] = []
        current_sentences: List[str] = []
        current_wc = 0

        for sent in sentences:
            sent_wc = len(sent.split())
            if sent_wc == 0:
                continue

            # If a single sentence is itself larger than max, we keep it whole
            # (cutting mid-sentence is worse than a slightly oversized chunk)
            if sent_wc > self.settings.max_chunk_word_count:
                if current_sentences:
                    sub_chunks.append(" ".join(current_sentences).strip())
                    current_sentences = []
                    current_wc = 0
                sub_chunks.append(sent.strip())
                continue

            if current_wc + sent_wc > self.settings.max_chunk_word_count and current_sentences:
                sub_chunks.append(" ".join(current_sentences).strip())
                current_sentences = [sent]
                current_wc = sent_wc
            else:
                current_sentences.append(sent)
                current_wc += sent_wc

        if current_sentences:
            sub_chunks.append(" ".join(current_sentences).strip())

        # 3. Add continuation prefix if header exists and we produced multiple chunks
        if header and len(sub_chunks) > 1:
            prefixed = []
            for idx, sub in enumerate(sub_chunks):
                if idx > 0:
                    sub = f"تابع {header}: {sub}"
                prefixed.append(sub)
            sub_chunks = prefixed

        return sub_chunks

    def _split_to_sentences(self, text: str) -> List[str]:
        """Split text into sentences using abbreviation-aware regex."""
        # Protect abbreviations by temporarily replacing them with placeholders
        placeholders: Dict[str, str] = {}
        counter = 0

        def _replace_abbr(match: re.Match) -> str:
            nonlocal counter
            placeholder = f"«ABBR{counter}»"
            placeholders[placeholder] = match.group(0)
            counter += 1
            return placeholder

        # Replace all abbreviations with placeholders
        protected = re.sub(_abbrev_pattern, _replace_abbr, text, flags=re.UNICODE)

        # Now split by sentence terminators
        parts = SENTENCE_SPLIT_RE.split(protected)
        # Also split on semicolons when they act as sentence separators
        expanded: List[str] = []
        for part in parts:
            expanded.extend(SEMICOLON_SPLIT_RE.split(part))

        sentences = [p.strip() for p in expanded if p.strip()]

        # Restore abbreviations
        restored = []
        for sent in sentences:
            for placeholder, original in placeholders.items():
                sent = sent.replace(placeholder, original)
            restored.append(sent)

        return restored

    def _word_chunk_text(self, text: str) -> List[str]:
        """Emergency fallback: split by words (old logic, but rarely used)."""
        words = text.split()
        stride = max(1, self.settings.max_chunk_word_count - 50)
        chunks = []
        for i in range(0, len(words), stride):
            chunk_words = words[i : i + self.settings.max_chunk_word_count]
            if not chunk_words:
                break
            chunks.append(" ".join(chunk_words))
            if i + self.settings.max_chunk_word_count >= len(words):
                break
        return chunks

    def _flush_buffer(
        self,
        buffer: List[str],
        headers: List[str],
        document_hierarchy: str,
        chunk_id: int,
    ) -> SemanticChunk:
        """Convert a buffer of text pieces into a final SemanticChunk."""
        raw_text = "\n\n".join(buffer).strip()

        # Build hierarchy path
        unique_headers = []
        seen = set()
        for h in headers:
            if h and h not in seen:
                seen.add(h)
                unique_headers.append(h)

        hierarchy_parts = []
        if document_hierarchy:
            hierarchy_parts.append(document_hierarchy)
        hierarchy_parts.extend(unique_headers)
        context_summary = self.settings.hierarchy_delimiter.join(hierarchy_parts) if hierarchy_parts else ""

        # Context injection
        if self.settings.context_injection_enabled and context_summary:
            content = f"[{context_summary}]\n\n{raw_text}"
        else:
            content = raw_text

        # Metadata
        source_section = unique_headers[-1] if unique_headers else ""
        keywords = self._extract_keywords(raw_text)

        return SemanticChunk(
            chunk_id=chunk_id,
            context_summary=context_summary,
            content=content,
            metadata={
                "source_section": source_section,
                "keywords": keywords,
                "word_count": len(raw_text.split()),
                "sentence_count": len(self._split_to_sentences(raw_text)),
            },
        )

    def _post_process_chunks(self, chunks: List[SemanticChunk]) -> List[SemanticChunk]:
        """
        Final safety pass:
        - Ensure no chunk ends mid-sentence if enforce_sentence_boundaries is on.
        - Ensure no chunk is below min_chunk_word_count unless it's the only chunk
          or it's a legal unit that is naturally short.
        """
        if not chunks:
            return chunks

        final: List[SemanticChunk] = []
        for idx, chunk in enumerate(chunks):
            text = chunk.content
            # If context injection prefix exists, strip it for boundary checks
            prefix_len = 0
            if text.startswith("[") and "]\n\n" in text:
                prefix_len = text.index("]\n\n") + 3
                body = text[prefix_len:]
            else:
                body = text

            # Trim trailing fragments (incomplete sentence trailing words)
            if self.settings.enforce_sentence_boundaries:
                body = self._trim_trailing_fragment(body)

            # If body became too short after trim, and it's not the only chunk,
            # try to merge with neighbour
            body_wc = len(body.split())
            if body_wc < self.settings.min_chunk_word_count and len(chunks) > 1:
                # Try to merge with previous chunk
                if final:
                    prev = final[-1]
                    merged_text = prev.content + "\n\n" + body
                    # Update metadata
                    merged_keywords = list(set(prev.metadata.get("keywords", []) + chunk.metadata.get("keywords", [])))
                    merged_section = prev.metadata.get("source_section", "")
                    if chunk.metadata.get("source_section") and chunk.metadata["source_section"] != merged_section:
                        merged_section += f", {chunk.metadata['source_section']}"
                    new_chunk = SemanticChunk(
                        chunk_id=prev.chunk_id,
                        context_summary=prev.context_summary,
                        content=merged_text,
                        metadata={
                            "source_section": merged_section,
                            "keywords": merged_keywords,
                            "word_count": len(merged_text.split()),
                            "sentence_count": prev.metadata.get("sentence_count", 0) + chunk.metadata.get("sentence_count", 0),
                        },
                    )
                    final[-1] = new_chunk
                    continue
                else:
                    # First chunk too short, merge forward if possible
                    if idx + 1 < len(chunks):
                        next_chunk = chunks[idx + 1]
                        merged_text = body + "\n\n" + next_chunk.content
                        # Update next chunk in-place so next iteration picks it up
                        chunks[idx + 1] = SemanticChunk(
                            chunk_id=chunk.chunk_id,
                            context_summary=chunk.context_summary,
                            content=merged_text,
                            metadata={
                                "source_section": chunk.metadata.get("source_section", ""),
                                "keywords": list(set(chunk.metadata.get("keywords", []) + next_chunk.metadata.get("keywords", []))),
                                "word_count": len(merged_text.split()),
                                "sentence_count": chunk.metadata.get("sentence_count", 0) + next_chunk.metadata.get("sentence_count", 0),
                            },
                        )
                        continue

            # Re-assemble with prefix
            if prefix_len > 0:
                text = text[:prefix_len] + body
            else:
                text = body

            final.append(SemanticChunk(
                chunk_id=chunk.chunk_id,
                context_summary=chunk.context_summary,
                content=text,
                metadata=chunk.metadata,
            ))

        # Re-number chunk_ids sequentially
        for i, c in enumerate(final, start=1):
            c.chunk_id = i
        return final

    def _trim_trailing_fragment(self, text: str) -> str:
        """
        If text ends with an incomplete sentence (no terminator in the last 10 words),
        try to cut back to the last sentence boundary. If none exists, return as-is.
        """
        words = text.split()
        if len(words) < 3:
            return text

        # Search backwards for last sentence terminator
        last_terminator = -1
        for i in range(len(text) - 1, -1, -1):
            if text[i] in ".؟!":
                # Make sure it's not inside an abbreviation (simple check)
                snippet = text[max(0, i - 5):i + 1]
                if re.search(r"[دأم]\.$", snippet):
                    continue
                last_terminator = i
                break

        if last_terminator > 0:
            trimmed = text[: last_terminator + 1].strip()
            # Ensure we didn't cut everything
            if len(trimmed.split()) >= self.settings.min_chunk_word_count // 2:
                return trimmed
        return text

    def _extract_keywords(self, text: str, top_n: int = 5) -> List[str]:
        """
        Lightweight keyword extraction via frequency after stop-word removal.
        No external LLM is called, ensuring fast ingestion.
        """
        # Normalise
        text = re.sub(r"[^\u0600-\u06FFa-zA-Z0-9\s]", "", text)
        words = text.split()
        freq: Dict[str, int] = {}
        for w in words:
            w = w.strip()
            if not w or w in ARABIC_STOP_WORDS or len(w) < 3:
                continue
            freq[w] = freq.get(w, 0) + 1
        # Sort by frequency then alphabetically for stability
        sorted_words = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
        return [w for w, _ in sorted_words[:top_n]]

    # ------------------------------------------------------------------
    # Compatibility bridge for legacy callers expecting list[str]
    # ------------------------------------------------------------------

    def split_to_strings(self, text: str, document_hierarchy: Optional[str] = None) -> List[str]:
        """Return only the content strings (for simple callers)."""
        chunks = self.split(text, document_hierarchy)
        return [c["content"] for c in chunks]


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def get_semantic_splitter(settings: Optional[Dict[str, Any]] = None) -> LegalSemanticSplitter:
    if settings:
        return LegalSemanticSplitter(SplitterSettings.from_dict(settings))
    return LegalSemanticSplitter()
