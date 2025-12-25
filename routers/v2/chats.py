from fastapi import APIRouter, HTTPException
from typing import List, Optional, Literal, Any
from pydantic import BaseModel
from datetime import datetime
from models.chat import ChatDB
from models.message import MessageDB
from models.user import UserDB
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v2/chats", tags=["chats"])
chat_db = ChatDB()
message_db = MessageDB()
user_db = UserDB()


class ChatListItem(BaseModel):
    chat_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    message_id: str
    role: str
    content: str
    model: Optional[str] = None
    type: Optional[str] = "rag"
    sources: Optional[List[dict]] = None
    feedback: Optional[int] = 0
    feedback_text: Optional[str] = None
    thumbs_down_feedback: Optional[str] = None
    timestamp: Any  # Use Any to be safe with different datetime representations


class FeedbackRequest(BaseModel):
    message_id: str
    feedback_type: Literal["thumbs_up", "thumbs_down", "feedback"]
    feedback_message: Optional[str] = None
    # Additional fields from frontend for analytics
    chat_id: Optional[str] = None
    user_id: Optional[str] = None
    message_index: Optional[int] = None
    session_id: Optional[str] = None


@router.get("/{user_id}", response_model=List[ChatListItem])
async def get_user_chats(user_id: str):
    """
    Retrieves all chats for a specific user, sorted by newest first.
    Titles are derived from the first user message of each chat.
    """
    try:
        # Get chats for the user
        chats = chat_db.get_user_chats(user_id)

        chat_list = []
        for chat in chats:
            chat_id = chat["chat_id"]

            # If the chat title is still "New Chat", try to update it from the first message
            title = chat.get("title", "New Chat")
            if title == "New Chat":
                # Get messages for this chat
                messages = message_db.get_chat_messages(chat_id)
                if messages:
                    # Find the first user message
                    first_user_msg = next(
                        (m for m in messages if m["role"] == "user"), None
                    )
                    if first_user_msg:
                        # Truncate title for display
                        full_content = first_user_msg["content"]
                        title = (
                            (full_content[:50] + "...")
                            if len(full_content) > 50
                            else full_content
                        )
                        # Update the chat title in the database so we don't do this every time
                        chat_db.update_chat_title(chat_id, title)

            chat_list.append(
                ChatListItem(
                    chat_id=chat_id,
                    title=title,
                    created_at=chat["created_at"],
                    updated_at=chat.get("updated_at", chat["created_at"]),
                )
            )

        return chat_list

    except Exception as e:
        logger.error(f"Error fetching chats for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{user_id}/{chat_id}/messages", response_model=List[MessageResponse])
async def get_chat_messages(user_id: str, chat_id: str):
    """
    Retrieves all messages for a specific chat.
    Validates that the chat belongs to the specified user.
    """
    try:
        logger.info(f"Fetching messages for user {user_id} and chat {chat_id}")
        # Validate chat ownership
        chat = chat_db.get_chat_by_id(chat_id)
        if not chat:
            logger.warning(f"Chat {chat_id} not found in database")
            raise HTTPException(status_code=404, detail="Chat not found")

        # Compare user IDs - allow access if it's the owner OR if requester is an admin
        is_owner = str(chat["user_id"]) == str(user_id)
        if not is_owner:
            # Check if the requesting user is an admin
            requester = user_db.get_user_by_id(user_id)
            is_admin = requester.get("is_admin", False) if requester else False

            if not is_admin:
                logger.warning(
                    f"Access denied: Chat {chat_id} belongs to {chat['user_id']}, not {user_id} (and user is not admin)"
                )
                raise HTTPException(
                    status_code=403,
                    detail="Access denied: Chat does not belong to this user",
                )
            else:
                logger.info(
                    f"Admin {user_id} is accessing chat {chat_id} owned by {chat['user_id']}"
                )

        # Get messages for the chat
        messages = message_db.get_chat_messages(chat_id)
        logger.info(f"Found {len(messages)} messages for chat {chat_id}")

        # Map to response model with explicit None handling and robustness
        response_messages = []
        for msg in messages:
            try:
                # Basic validation
                if (
                    not msg.get("message_id")
                    or not msg.get("role")
                    or not msg.get("content")
                ):
                    logger.warning(f"Skipping malformed message in chat {chat_id}")
                    continue

                response_messages.append(
                    MessageResponse(
                        message_id=str(msg["message_id"]),
                        role=str(msg["role"]),
                        content=str(msg["content"]),
                        model=msg.get("model"),
                        type=str(msg.get("type", "rag")),
                        sources=msg.get("sources"),
                        feedback=(
                            msg.get("feedback")
                            if msg.get("feedback") is not None
                            else 0
                        ),
                        feedback_text=msg.get("feedback_text"),
                        thumbs_down_feedback=msg.get("thumbs_down_feedback"),
                        timestamp=msg.get("timestamp", datetime.utcnow()),
                    )
                )
            except Exception as val_error:
                logger.error(
                    f"Validation error for message {msg.get('message_id')}: {val_error}"
                )

        return response_messages

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching messages for chat {chat_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{user_id}/{chat_id}")
async def delete_chat(user_id: str, chat_id: str):
    """
    Soft deletes a chat for a specific user.
    """
    try:
        # Validate chat ownership
        chat = chat_db.get_chat_by_id(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        if str(chat["user_id"]) != str(user_id):
            raise HTTPException(
                status_code=403,
                detail="Access denied: Chat does not belong to this user",
            )

        success = chat_db.soft_delete_chat(chat_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete chat")

        return {"success": True, "message": "Chat deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/feedback")
async def save_feedback(request: FeedbackRequest):
    """
    Saves or updates feedback for a specific message.
    Supports thumbs_up, thumbs_down, and detailed text feedback.
    """
    try:
        feedback_val = None
        feedback_text = None
        thumbs_down_feedback = None

        if request.feedback_type == "thumbs_up":
            feedback_val = 1
        elif request.feedback_type == "thumbs_down":
            feedback_val = -1
            thumbs_down_feedback = request.feedback_message
        elif request.feedback_type == "feedback":
            # For general feedback, we preserve the existing thumbs status
            # by not sending a feedback_val
            feedback_text = request.feedback_message

        success = message_db.update_feedback(
            message_id=request.message_id,
            feedback=feedback_val,
            feedback_text=feedback_text,
            thumbs_down_feedback=thumbs_down_feedback,
        )

        if not success:
            raise HTTPException(status_code=404, detail="Message not found")

        return {"success": True, "message": "Feedback saved successfully"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error saving feedback for message {request.message_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
