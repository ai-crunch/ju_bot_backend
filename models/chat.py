from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
import uuid
from .database import MongoDB


class Chat(BaseModel):
    chat_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    title: str = "New Chat"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_deleted: bool = False

    class Config:
        populate_by_name = True


class ChatDB:
    def __init__(self):
        self.db = MongoDB.get_db()
        self.collection = self.db["chats"]
        self._create_indexes()

    def _create_indexes(self):
        self.collection.create_index("chat_id", unique=True)
        self.collection.create_index("user_id")
        self.collection.create_index("is_deleted")

    def create_chat(self, user_id: str, title: str = "New Chat") -> str:
        chat = Chat(user_id=user_id, title=title)
        chat_dict = chat.model_dump()
        self.collection.insert_one(chat_dict)
        return chat.chat_id

    def get_chat_by_id(self, chat_id: str) -> Optional[dict]:
        return self.collection.find_one(
            {"chat_id": chat_id, "is_deleted": {"$ne": True}}, {"_id": 0}
        )

    def get_user_chats(self, user_id: str) -> List[dict]:
        return list(
            self.collection.find(
                {"user_id": user_id, "is_deleted": {"$ne": True}}, {"_id": 0}
            ).sort("updated_at", -1)
        )

    def update_chat_title(self, chat_id: str, title: str) -> bool:
        result = self.collection.update_one(
            {"chat_id": chat_id},
            {"$set": {"title": title, "updated_at": datetime.utcnow()}},
        )
        return result.modified_count > 0

    def soft_delete_chat(self, chat_id: str) -> bool:
        result = self.collection.update_one(
            {"chat_id": chat_id},
            {"$set": {"is_deleted": True, "updated_at": datetime.utcnow()}},
        )
        return result.modified_count > 0

    def delete_chat(self, chat_id: str) -> bool:
        result = self.collection.delete_one({"chat_id": chat_id})
        return result.deleted_count > 0
