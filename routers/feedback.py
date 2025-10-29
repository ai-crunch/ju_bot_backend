from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Literal, Optional
from datetime import datetime
from pymongo import MongoClient
from models.chat_history import chat_history_db
import config

router = APIRouter(
    prefix="/api/feedback",
    tags=["feedback"],
)


# MongoDB connection
def get_mongodb_client():
    """Get MongoDB client connection with fallback authentication"""
    mongo_config = config.MONGODB

    # Try configured credentials first
    try:
        auth_connection = f"mongodb://{mongo_config['username']}:{mongo_config['password']}@{mongo_config['host']}:{mongo_config['port']}/{mongo_config['database']}?authSource=admin"
        client = MongoClient(auth_connection)
        client.admin.command("ping")
        return client
    except Exception:
        # Fallback to admin credentials
        try:
            admin_connection = f"mongodb://admin:password@{mongo_config['host']}:{mongo_config['port']}/{mongo_config['database']}?authSource=admin"
            client = MongoClient(admin_connection)
            client.admin.command("ping")
            return client
        except Exception:
            # Final fallback to no authentication
            try:
                simple_connection = (
                    f"mongodb://{mongo_config['host']}:{mongo_config['port']}"
                )
                client = MongoClient(simple_connection)
                client.admin.command("ping")
                return client
            except Exception as e:
                print(f"MongoDB connection failed: {e}")
                raise e


def get_feedback_collection():
    """Get feedback collection from MongoDB"""
    client = get_mongodb_client()
    db = client[config.MONGODB["database"]]
    return db[config.MONGODB["collection"]]


class FeedbackData(BaseModel):
    question: str
    answer: str
    feedback_type: Literal["thumbs_up", "thumbs_down", "feedback"]
    feedback_message: Optional[str] = None
    agent_used: bool = False
    sources: List[dict] = []
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    message_id: Optional[str] = None  # Add message_id for deduplication
    # New fields for chat history integration
    chat_id: Optional[str] = None
    message_index: Optional[int] = None  # Index of message in chat history


class FeedbackResponse(BaseModel):
    success: bool
    message: str
    feedback_id: Optional[str] = None


@router.post("/save", response_model=FeedbackResponse)
async def save_feedback(feedback: FeedbackData):
    """Save feedback data to MongoDB with deduplication and chat history integration"""
    try:
        # First, try to update chat history if chat_id and message_index are provided
        if feedback.chat_id is not None and feedback.message_index is not None:
            try:
                # Determine what to update based on feedback type
                feedback_value = None
                user_feedback_str = None
                thumbs_down_message_feedback = None

                if feedback.feedback_type == "thumbs_up":
                    feedback_value = 1
                elif feedback.feedback_type == "thumbs_down":
                    feedback_value = -1
                    # If there's a message with thumbs down, it's thumbs down specific feedback
                    if feedback.feedback_message:
                        thumbs_down_message_feedback = feedback.feedback_message
                elif feedback.feedback_type == "feedback":
                    # General feedback doesn't change the thumbs value, only adds text
                    user_feedback_str = feedback.feedback_message or ""

                # Update chat history with only the relevant fields
                success = chat_history_db.update_message_feedback(
                    chat_id=feedback.chat_id,
                    message_index=feedback.message_index,
                    feedback=feedback_value,
                    user_feedback_str=user_feedback_str,
                    thumbs_down_message_feedback=thumbs_down_message_feedback,
                )

                if success:
                    print(
                        f"Updated chat history feedback for chat {feedback.chat_id}, message {feedback.message_index}"
                    )
                else:
                    print(
                        f"Failed to update chat history feedback for chat {feedback.chat_id}"
                    )

            except Exception as e:
                print(f"Error updating chat history feedback: {e}")
                # Continue with legacy feedback system even if chat history fails

        # Continue with legacy feedback system for backward compatibility
        collection = get_feedback_collection()

        # Prepare feedback document
        feedback_doc = {
            "question": feedback.question,
            "answer": feedback.answer,
            "feedback_type": feedback.feedback_type,
            "feedback_message": feedback.feedback_message,
            "agent_used": feedback.agent_used,
            "sources": feedback.sources,
            "session_id": feedback.session_id,
            "user_id": feedback.user_id,
            "message_id": feedback.message_id,
            "chat_id": feedback.chat_id,
            "message_index": feedback.message_index,
            "timestamp": datetime.utcnow(),
            "created_at": datetime.utcnow().isoformat(),
        }

        # Handle deduplication based on message_id, question, and answer
        if feedback.message_id:
            # Use message_id for deduplication (preferred method)
            query = {"message_id": feedback.message_id}
        elif feedback.chat_id and feedback.message_index is not None:
            # Use chat_id and message_index for deduplication
            query = {
                "chat_id": feedback.chat_id,
                "message_index": feedback.message_index,
            }
        else:
            # Fallback to question+answer hash for deduplication
            import hashlib

            content_hash = hashlib.md5(
                f"{feedback.question}{feedback.answer}".encode()
            ).hexdigest()
            feedback_doc["content_hash"] = content_hash
            query = {"content_hash": content_hash}

        # Check if feedback already exists for this message/content
        existing_feedback = collection.find_one(query)

        if existing_feedback:
            # Update existing feedback with new data
            result = collection.replace_one(query, feedback_doc)
            return FeedbackResponse(
                success=True,
                message="Feedback updated successfully",
                feedback_id=str(existing_feedback["_id"]),
            )
        else:
            # Insert new feedback
            result = collection.insert_one(feedback_doc)
            return FeedbackResponse(
                success=True,
                message="Feedback saved successfully",
                feedback_id=str(result.inserted_id),
            )

    except Exception as e:
        print(f"Error saving feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to save feedback")


@router.get("/stats")
async def get_feedback_stats():
    """Get feedback statistics"""
    try:
        collection = get_feedback_collection()

        # Count different types of feedback
        total_feedback = collection.count_documents({})
        thumbs_up = collection.count_documents({"feedback_type": "thumbs_up"})
        thumbs_down = collection.count_documents({"feedback_type": "thumbs_down"})
        feedback_messages = collection.count_documents({"feedback_type": "feedback"})

        # Get recent feedback
        recent_feedback = list(collection.find({}).sort("timestamp", -1).limit(10))

        # Convert ObjectId to string for JSON serialization
        for feedback in recent_feedback:
            feedback["_id"] = str(feedback["_id"])
            if "timestamp" in feedback:
                feedback["timestamp"] = feedback["timestamp"].isoformat()

        return {
            "total_feedback": total_feedback,
            "thumbs_up": thumbs_up,
            "thumbs_down": thumbs_down,
            "feedback_messages": feedback_messages,
            "recent_feedback": recent_feedback,
        }

    except Exception as e:
        print(f"Error getting feedback stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get feedback statistics")


@router.get("/health")
async def health_check():
    """Check MongoDB connection health"""
    try:
        client = get_mongodb_client()
        # Test connection
        client.admin.command("ping")
        client.close()
        return {"status": "healthy", "message": "MongoDB connection successful"}
    except Exception as e:
        print(f"MongoDB health check failed: {e}")
        raise HTTPException(status_code=500, detail="MongoDB connection failed")
