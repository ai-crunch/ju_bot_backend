from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

from models.chat_history import ChatHistoryDB, QADict, chat_history_db

router = APIRouter(
    prefix="/api/chat-history",
    tags=["chat-history"],
)


class NewChatResponse(BaseModel):
    """Response model for new chat creation"""

    success: bool
    chat_id: str
    message: str


class UpdateFeedbackRequest(BaseModel):
    """Request model for updating message feedback"""

    chat_id: str
    message_index: int
    feedback: Optional[int] = None  # -1, 0, or 1 (optional to allow partial updates)
    user_feedback_str: Optional[str] = None  # General feedback (optional)
    thumbs_down_message_feedback: Optional[str] = (
        None  # Thumbs down specific feedback (optional)
    )


class UpdateFeedbackResponse(BaseModel):
    """Response model for feedback update"""

    success: bool
    message: str


class ChatStatsResponse(BaseModel):
    """Response model for chat statistics"""

    total_chats: int
    active_chats: int
    total_messages: int
    average_thumb_ratio: float


@router.post("/new-chat", response_model=NewChatResponse)
async def create_new_chat():
    """Create a new chat session and return chat_id"""
    try:
        chat_id = chat_history_db.create_new_chat()
        return NewChatResponse(
            success=True, chat_id=chat_id, message="New chat created successfully"
        )
    except Exception as e:
        print(f"Error creating new chat: {e}")
        raise HTTPException(status_code=500, detail="Failed to create new chat")


@router.get("/chat/{chat_id}")
async def get_chat_history(chat_id: str):
    """Get chat history by chat_id"""
    try:
        chat_history = chat_history_db.get_chat_history(chat_id)
        if not chat_history:
            raise HTTPException(status_code=404, detail="Chat not found")

        return {"success": True, "chat_history": chat_history}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting chat history: {e}")
        raise HTTPException(status_code=500, detail="Failed to get chat history")


@router.post("/update-feedback", response_model=UpdateFeedbackResponse)
async def update_message_feedback(request: UpdateFeedbackRequest):
    """Update feedback for a specific message in chat"""
    try:
        # Validate feedback value if provided
        if request.feedback is not None and request.feedback not in [-1, 0, 1]:
            raise HTTPException(status_code=400, detail="Feedback must be -1, 0, or 1")

        success = chat_history_db.update_message_feedback(
            chat_id=request.chat_id,
            message_index=request.message_index,
            feedback=request.feedback,
            user_feedback_str=request.user_feedback_str,
            thumbs_down_message_feedback=request.thumbs_down_message_feedback,
        )

        if success:
            return UpdateFeedbackResponse(
                success=True, message="Feedback updated successfully"
            )
        else:
            raise HTTPException(status_code=404, detail="Chat or message not found")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to update feedback")


@router.get("/stats", response_model=ChatStatsResponse)
async def get_chat_stats():
    """Get overall chat statistics"""
    try:
        stats = chat_history_db.get_chat_stats()
        return ChatStatsResponse(**stats)
    except Exception as e:
        print(f"Error getting chat stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get chat statistics")


@router.get("/health")
async def health_check():
    """Check chat history database connection health"""
    try:
        # Test connection by getting stats
        stats = chat_history_db.get_chat_stats()
        return {
            "status": "healthy",
            "message": "Chat history database connection successful",
            "stats": stats,
        }
    except Exception as e:
        print(f"Chat history health check failed: {e}")
        raise HTTPException(
            status_code=500, detail="Chat history database connection failed"
        )
