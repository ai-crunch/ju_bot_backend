from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from pymongo import MongoClient
from bson import ObjectId
import uuid
import config


class QADict(BaseModel):
    """Model for individual question-answer pairs in chat history"""

    question: str
    answer: str
    feedback: int = 0  # 0: no feedback, 1: thumbs up, -1: thumbs down
    user_feedback_str: str = ""  # User's written feedback (general feedback)
    thumbs_down_message_feedback: str = (
        ""  # Specific feedback when user clicks thumbs down
    )
    prompt: str  # The prompt sent to the LLM/Agent
    references: List[Dict[str, Any]] = []  # List of references/sources
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatHistory(BaseModel):
    """Model for chat history document in MongoDB"""

    chat_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    chat_history: List[QADict] = []
    no_messages: bool = True
    thumb_ratio: float = 0.0  # Ratio of positive feedback
    first_message_time: Optional[datetime] = None
    last_message_time: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class ChatHistoryDB:
    """Database operations for chat history"""

    def __init__(self):
        self.client = None
        self.db = None
        self.collection = None
        self._connect()

    def _connect(self):
        """Establish MongoDB connection"""
        try:
            self.client = self._get_mongodb_client()
            mongo_config = config.MONGODB
            self.db = self.client[mongo_config["database"]]
            self.collection = self.db["chat_history"]  # New collection for chat history

            # Test connection
            self.client.admin.command("ping")
            print("✅ Connected to MongoDB for chat history")

        except Exception as e:
            print(f"❌ Failed to connect to MongoDB: {e}")
            raise e

    def _get_mongodb_client(self):
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

    def create_new_chat(self) -> str:
        """Create a new chat session and return chat_id"""
        try:
            chat_history = ChatHistory()
            chat_doc = chat_history.model_dump()

            # Convert datetime objects to proper format
            chat_doc["created_at"] = datetime.utcnow()
            chat_doc["updated_at"] = datetime.utcnow()

            result = self.collection.insert_one(chat_doc)
            print(f"✅ Created new chat with ID: {chat_history.chat_id}")
            return chat_history.chat_id

        except Exception as e:
            print(f"❌ Error creating new chat: {e}")
            raise e

    def add_message_to_chat(self, chat_id: str, qa_dict: QADict) -> bool:
        """Add a new message to existing chat"""
        try:
            # Convert QADict to dict
            qa_data = qa_dict.model_dump()
            qa_data["timestamp"] = datetime.utcnow()

            # Update the chat document
            update_data = {
                "$push": {"chat_history": qa_data},
                "$set": {
                    "no_messages": False,
                    "last_message_time": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                },
            }

            # Set first_message_time if this is the first message
            existing_chat = self.collection.find_one({"chat_id": chat_id})
            if existing_chat and existing_chat.get("no_messages", True):
                update_data["$set"]["first_message_time"] = datetime.utcnow()

            result = self.collection.update_one({"chat_id": chat_id}, update_data)

            if result.modified_count > 0:
                # Update thumb ratio
                self._update_thumb_ratio(chat_id)
                print(f"✅ Added message to chat {chat_id}")
                return True
            else:
                print(f"❌ Chat {chat_id} not found")
                return False

        except Exception as e:
            print(f"❌ Error adding message to chat: {e}")
            raise e

    def update_message_feedback(
        self,
        chat_id: str,
        message_index: int,
        feedback: int = None,
        user_feedback_str: str = None,
        thumbs_down_message_feedback: str = None,
    ) -> bool:
        """Update feedback for a specific message in chat - merges data instead of overwriting"""
        try:
            # Build update data only for fields that are provided
            update_data = {"updated_at": datetime.utcnow()}

            # Only update feedback value if provided
            if feedback is not None:
                update_data[f"chat_history.{message_index}.feedback"] = feedback

            # Only update general feedback if provided
            if user_feedback_str is not None:
                update_data[f"chat_history.{message_index}.user_feedback_str"] = (
                    user_feedback_str
                )

            # Only update thumbs down feedback if provided
            if thumbs_down_message_feedback is not None:
                update_data[
                    f"chat_history.{message_index}.thumbs_down_message_feedback"
                ] = thumbs_down_message_feedback

            result = self.collection.update_one(
                {"chat_id": chat_id}, {"$set": update_data}
            )

            if result.modified_count > 0:
                # Update thumb ratio
                self._update_thumb_ratio(chat_id)
                print(
                    f"✅ Updated feedback for message {message_index} in chat {chat_id}"
                )
                return True
            else:
                print(f"❌ Failed to update feedback for chat {chat_id}")
                return False

        except Exception as e:
            print(f"❌ Error updating message feedback: {e}")
            raise e

    def _update_thumb_ratio(self, chat_id: str):
        """Calculate and update thumb ratio for a chat"""
        try:
            chat = self.collection.find_one({"chat_id": chat_id})
            if not chat or not chat.get("chat_history"):
                return

            messages = chat["chat_history"]
            total_feedback = sum(1 for msg in messages if msg.get("feedback", 0) != 0)
            positive_feedback = sum(
                1 for msg in messages if msg.get("feedback", 0) == 1
            )

            thumb_ratio = (
                positive_feedback / total_feedback if total_feedback > 0 else 0.0
            )

            self.collection.update_one(
                {"chat_id": chat_id},
                {"$set": {"thumb_ratio": thumb_ratio, "updated_at": datetime.utcnow()}},
            )

        except Exception as e:
            print(f"❌ Error updating thumb ratio: {e}")

    def get_chat_history(self, chat_id: str) -> Optional[Dict]:
        """Get chat history by chat_id"""
        try:
            chat = self.collection.find_one({"chat_id": chat_id})
            if chat:
                # Convert ObjectId to string
                chat["_id"] = str(chat["_id"])
                return chat
            return None

        except Exception as e:
            print(f"❌ Error getting chat history: {e}")
            raise e

    def get_chat_stats(self) -> Dict:
        """Get overall chat statistics"""
        try:
            total_chats = self.collection.count_documents({})
            active_chats = self.collection.count_documents({"no_messages": False})

            # Get average thumb ratio
            pipeline = [
                {"$match": {"no_messages": False}},
                {"$group": {"_id": None, "avg_thumb_ratio": {"$avg": "$thumb_ratio"}}},
            ]
            avg_result = list(self.collection.aggregate(pipeline))
            avg_thumb_ratio = avg_result[0]["avg_thumb_ratio"] if avg_result else 0.0

            # Get total messages
            pipeline = [
                {"$match": {"no_messages": False}},
                {"$project": {"message_count": {"$size": "$chat_history"}}},
                {"$group": {"_id": None, "total_messages": {"$sum": "$message_count"}}},
            ]
            msg_result = list(self.collection.aggregate(pipeline))
            total_messages = msg_result[0]["total_messages"] if msg_result else 0

            return {
                "total_chats": total_chats,
                "active_chats": active_chats,
                "total_messages": total_messages,
                "average_thumb_ratio": round(avg_thumb_ratio, 3),
            }

        except Exception as e:
            print(f"❌ Error getting chat stats: {e}")
            raise e

    def close_connection(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()


# Global instance
chat_history_db = ChatHistoryDB()
