from pydantic import BaseModel
from typing import List, Literal, Optional


# ---------- Request Models ----------


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str

    def to_dict(self):
        return {
            "role": self.role,
            "content": self.content,
        }


class ChatRequest(BaseModel):
    messages: List[Message]
    chat_id: Optional[str] = None  # Optional chat_id for existing chats
    user_id: Optional[str] = None  # Optional user_id for existing users

    def to_dict(self):
        return {
            "messages": [message.to_dict() for message in self.messages],
            "chat_id": self.chat_id,
            "user_id": self.user_id,
        }


# ---------- Response Models ----------


class SourceMetadata(BaseModel):
    filename: Optional[str] = None
    source_title: Optional[str] = None
    source_link: Optional[str] = None
    is_web_source: bool = False
    source_type: Literal["pdf", "web", "document"] = "document"
    display_name: Optional[str] = None
    clickable: bool = False


class Source(BaseModel):
    text: str
    file_path: str
    metadata: Optional[SourceMetadata] = None


class ChatResponse(BaseModel):
    response: str
    sources: List[Source]
    chat_id: str  # Include chat_id in response
    message_id: Optional[str] = None  # assistant message_id for feedback tracking

    class Config:
        json_encoders = {
            # Ensure proper JSON serialization
        }
