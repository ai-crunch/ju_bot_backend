from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Literal
import uuid
from .database import MongoDB


class Message(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    chat_id: str
    role: Literal["user", "assistant"]
    content: str
    model: Optional[str] = None
    type: Literal["rag", "agent"] = "rag"
    sources: Optional[List[dict]] = None
    # Legacy single-feedback field (1=up, -1=down, 0=none)
    feedback: int = 0
    # Crowdsourced feedback counters for cache validation
    likes_count: int = 0
    dislikes_count: int = 0
    feedback_text: Optional[str] = None
    thumbs_down_feedback: Optional[str] = None
    session_id: Optional[str] = None
    message_index: Optional[int] = None
    embedding: Optional[List[float]] = None  # semantic cache vector
    # If this assistant message was returned from cache, track the source question
    cached_from_message_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


class MessageDB:
    def __init__(self):
        self.db = MongoDB.get_db()
        self.collection = self.db["messages"]
        self._create_indexes()

    def _create_indexes(self):
        self.collection.create_index("message_id", unique=True)
        self.collection.create_index("chat_id")
        self.collection.create_index("user_id")
        self.collection.create_index([("timestamp", 1)])

    def add_message(self, message: Message) -> str:
        message_dict = message.model_dump()
        self.collection.insert_one(message_dict)

        # Update the chat's updated_at timestamp
        self.db["chats"].update_one(
            {"chat_id": message.chat_id}, {"$set": {"updated_at": datetime.utcnow()}}
        )
        return message.message_id

    def get_chat_messages(self, chat_id: str) -> List[dict]:
        return list(
            self.collection.find({"chat_id": chat_id}, {"_id": 0}).sort("timestamp", 1)
        )

    def update_feedback(
        self,
        message_id: str,
        feedback: Optional[int] = None,
        feedback_text: Optional[str] = None,
        thumbs_down_feedback: Optional[str] = None,
    ) -> bool:
        update_data = {}
        if feedback is not None:
            update_data["feedback"] = feedback
        if feedback_text is not None:
            update_data["feedback_text"] = feedback_text
        if thumbs_down_feedback is not None:
            update_data["thumbs_down_feedback"] = thumbs_down_feedback

        if not update_data:
            return True

        result = self.collection.update_one(
            {"message_id": message_id}, {"$set": update_data}
        )
        return result.modified_count > 0

    def increment_feedback_counters(
        self,
        message_id: str,
        likes_delta: int = 0,
        dislikes_delta: int = 0,
    ) -> bool:
        """
        Atomically increment likes_count / dislikes_count for a message.
        Uses MongoDB $inc for safe concurrent updates.
        """
        inc_data = {}
        if likes_delta:
            inc_data["likes_count"] = likes_delta
        if dislikes_delta:
            inc_data["dislikes_count"] = dislikes_delta

        if not inc_data:
            return True

        result = self.collection.update_one(
            {"message_id": message_id}, {"$inc": inc_data}
        )
        return result.modified_count > 0

    def get_message_feedback_counts(self, message_id: str) -> dict:
        """Return current likes_count and dislikes_count for a message."""
        msg = self.collection.find_one(
            {"message_id": message_id},
            {"_id": 0, "likes_count": 1, "dislikes_count": 1},
        )
        if msg:
            return {
                "likes_count": msg.get("likes_count", 0),
                "dislikes_count": msg.get("dislikes_count", 0),
            }
        return {"likes_count": 0, "dislikes_count": 0}

    def delete_chat_messages(self, chat_id: str) -> int:
        result = self.collection.delete_many({"chat_id": chat_id})
        return result.deleted_count

    # ------------------------------------------------------------------
    # Semantic-cache helpers
    # ------------------------------------------------------------------

    def get_user_question_messages(
        self,
        user_id: str,
        since: datetime,
        limit: int = 200,
        type_filter: Optional[str] = None,
        exclude_message_id: Optional[str] = None,
    ) -> List[dict]:
        """
        Retrieve recent user (role='user') messages that have an embedding stored.
        Used by the semantic cache to find historically similar questions.
        """
        query = {
            "user_id": user_id,
            "role": "user",
            "timestamp": {"$gte": since},
            "embedding": {"$exists": True},
        }
        if type_filter:
            query["type"] = type_filter
        if exclude_message_id:
            query["message_id"] = {"$ne": exclude_message_id}

        return list(
            self.collection.find(query, {"_id": 0})
            .sort("timestamp", -1)
            .limit(limit)
        )

    def get_next_assistant_message(
        self,
        chat_id: str,
        after_timestamp: datetime,
        type_filter: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Fetch the first assistant message in a chat that occurs strictly after the given timestamp.
        This retrieves the cached response that corresponds to a matched historical question.
        """
        query = {
            "chat_id": chat_id,
            "role": "assistant",
            "timestamp": {"$gt": after_timestamp},
        }
        if type_filter:
            query["type"] = type_filter

        return self.collection.find_one(
            query,
            {"_id": 0},
            sort=[("timestamp", 1)],
        )
