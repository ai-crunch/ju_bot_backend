import numpy as np
from typing import Optional, List
from datetime import datetime, timedelta

from models.message import MessageDB
from utils.embedder import Embedder
from utils.logger import get_logger

logger = get_logger(__name__)


class SemanticCache:
    """
    Production-grade feedback-driven semantic caching layer.

    Goal: eliminate unnecessary OpenAI API token costs by returning cached
    answers when a semantically similar question has already been answered
    and the community has validated that answer.

    Workflow:
        1. Embed the incoming question (local E5 model — zero cost).
        2. Query MongoDB for the user's recent historical questions with
           stored embedding vectors.
        3. Compute cosine similarity between the new question and each
           historical question.
        4. Find the best match. If score < threshold → cache miss.
        5. If score >= threshold, fetch the corresponding assistant response
           and its crowdsourced feedback metrics (likes / dislikes).
        6. Feedback-driven validation:
            a) Case 1 — New / Uncontested:  dislikes_count == 0
               → Return cached response immediately (100% cost saving).
            b) Case 2 — Tested & Trusted:   likes_count >= dislikes_count * 1.3
               → Return cached response (100% cost saving).
            c) Case 3 — Poisoned / Disputed: likes_count < dislikes_count * 1.3
               → Treat as cache miss and invoke the full agno + OpenAI pipeline.
        7. On cache miss, proceed to standard RAG and save the new pair.

    Why cosine similarity on embeddings instead of string metrics:
        - Embeddings capture semantic meaning, synonyms, and paraphrases.
        - String metrics (Jaccard / Levenshtein) are purely lexical and fail
          on rephrased questions.
        - We reuse the existing Embedder (HuggingFace or OpenAI) for consistency
          with the RAG pipeline.
    """

    def __init__(
        self,
        threshold: Optional[float] = None,
        lookback_days: int = 30,
        max_history: int = 200,
        trust_ratio: Optional[float] = None,
    ):
        # Read defaults from live config if not explicitly provided
        import config

        self.threshold = threshold if threshold is not None else config.SEMANTIC_CACHE.get("similarity_threshold", 0.90)
        self.trust_ratio = trust_ratio if trust_ratio is not None else config.SEMANTIC_CACHE.get("feedback_ratio", 1.30)
        self.lookback_days = lookback_days
        self.max_history = max_history
        self.message_db = MessageDB()
        self.embedder = Embedder()

    @staticmethod
    def _normalize(vector: List[float]) -> np.ndarray:
        """L2-normalize a vector so cosine similarity becomes a simple dot product."""
        arr = np.array(vector, dtype=np.float32)
        norm = np.linalg.norm(arr)
        if norm == 0:
            return arr
        return arr / norm

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        a_norm = self._normalize(a)
        b_norm = self._normalize(b)
        return float(np.dot(a_norm, b_norm))

    def _is_trusted(self, likes: int, dislikes: int) -> bool:
        """
        Determine whether a cached answer is trusted enough to serve again.

        Case 1: No dislikes yet → trusted (new / uncontested).
        Case 2: Enough likes vs dislikes → trusted.
        Case 3: Not enough likes → poisoned / disputed.
        """
        if dislikes == 0:
            return True
        if likes >= dislikes * self.trust_ratio:
            return True
        return False

    def lookup(
        self,
        user_id: str,
        question: str,
        question_embedding: Optional[List[float]] = None,
        type_filter: Optional[str] = None,
        exclude_message_id: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Look up a semantically similar historical question with feedback validation.

        Args:
            user_id: The user identifier.
            question: The raw incoming question text.
            question_embedding: Pre-computed embedding vector (optional).
            type_filter: "rag" or "agent" to restrict the search.
            exclude_message_id: Message ID to exclude from search.

        Returns:
            A dict with keys:
                response (str), sources (List[dict]), score (float),
                matched_question (str), likes_count (int), dislikes_count (int),
                cached_from_message_id (str)
            or None if no trusted match exceeds the threshold.
        """
        # 1. Embed the incoming question if not provided
        if question_embedding is None:
            question_embedding = self.embedder.embed([question], is_query=True)[0]

        # 2. Query recent user messages that have embeddings stored
        since = datetime.utcnow() - timedelta(days=self.lookback_days)
        user_messages = self.message_db.get_user_question_messages(
            user_id=user_id,
            since=since,
            limit=self.max_history,
            type_filter=type_filter,
            exclude_message_id=exclude_message_id,
        )

        if not user_messages:
            return None

        # 3. Compute similarity scores
        best_match = None
        best_score = -1.0

        for msg in user_messages:
            embedding = msg.get("embedding")
            if not embedding:
                continue

            score = self._cosine_similarity(question_embedding, embedding)
            if score > best_score:
                best_score = score
                best_match = msg

        if not best_match or best_score < self.threshold:
            logger.info(
                f"Semantic cache MISS for user {user_id} | best_score={best_score:.4f} | "
                f"candidates_checked={len(user_messages)}"
            )
            return None

        # 4. Fetch the assistant response that follows the matched user message
        assistant_msg = self.message_db.get_next_assistant_message(
            chat_id=best_match["chat_id"],
            after_timestamp=best_match["timestamp"],
            type_filter=type_filter,
        )

        if not assistant_msg:
            return None

        likes = assistant_msg.get("likes_count", 0)
        dislikes = assistant_msg.get("dislikes_count", 0)

        # 5. Feedback-driven validation
        if self._is_trusted(likes, dislikes):
            logger.info(
                f"Semantic cache HIT (trusted) for user {user_id} | "
                f"score={best_score:.4f} | likes={likes} | dislikes={dislikes} | "
                f"matched_question='{best_match['content']}'"
            )
            return {
                "response": assistant_msg.get("content", ""),
                "sources": assistant_msg.get("sources", []),
                "score": best_score,
                "matched_question": best_match["content"],
                "likes_count": likes,
                "dislikes_count": dislikes,
                "cached_from_message_id": best_match["message_id"],
            }

        # Case 3 — Poisoned cache: match found but community doesn't trust it
        logger.info(
            f"Semantic cache POISONED for user {user_id} | "
            f"score={best_score:.4f} | likes={likes} | dislikes={dislikes} | "
            f"matched_question='{best_match['content']}' — bypassing cache"
        )
        return None
