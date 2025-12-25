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
    feedback: int = 0  # 1: thumbs up, -1: thumbs down, 0: no feedback
    feedback_text: Optional[str] = None
    thumbs_down_feedback: Optional[str] = None
    session_id: Optional[str] = None
    message_index: Optional[int] = None
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

    def delete_chat_messages(self, chat_id: str) -> int:
        result = self.collection.delete_many({"chat_id": chat_id})
        return result.deleted_count
