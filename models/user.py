from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal, Optional, List
import uuid
from .database import MongoDB
import bcrypt


class User(BaseModel):
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    username: str
    email: str
    hashed_password: str
    role: Literal["user", "department_editor", "admin"] = "user"
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    is_admin: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def resolved_role(self) -> str:
        if self.is_admin:
            return "admin"
        return self.role

    class Config:
        populate_by_name = True

    @staticmethod
    def hash_password(password: str) -> str:
        # bcrypt requires bytes
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        # bcrypt requires bytes for both
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )


class UserDB:
    def __init__(self):
        self.db = MongoDB.get_db()
        self.collection = self.db["users"]
        self._create_indexes()

    def _create_indexes(self):
        self.collection.create_index("user_id", unique=True)
        self.collection.create_index("username", unique=True)
        self.collection.create_index("email", unique=True)

    def create_user(self, user: User) -> str:
        user_dict = user.model_dump()
        self.collection.insert_one(user_dict)
        return user.user_id

    def get_user_by_id(self, user_id: str) -> Optional[dict]:
        return self.collection.find_one({"user_id": user_id}, {"_id": 0})

    def get_user_by_username(self, username: str) -> Optional[dict]:
        return self.collection.find_one({"username": username}, {"_id": 0})

    def get_user_by_email(self, email: str) -> Optional[dict]:
        return self.collection.find_one({"email": email}, {"_id": 0})

    def get_all_users(self) -> List[dict]:
        return list(self.collection.find({}, {"_id": 0}))

    def toggle_admin(self, user_id: str) -> bool:
        user = self.get_user_by_id(user_id)
        if not user:
            return False

        new_status = not user.get("is_admin", False)
        update = {"$set": {"is_admin": new_status}}
        if new_status:
            update["$set"]["role"] = "admin"
        elif user.get("role") == "admin":
            update["$set"]["role"] = "user"
        result = self.collection.update_one(
            {"user_id": user_id}, update
        )
        return result.modified_count > 0

    def set_user_role(self, user_id: str, role: str, department_id: Optional[str] = None, department_name: Optional[str] = None) -> bool:
        update = {
            "$set": {
                "role": role,
                "is_admin": role == "admin",
            }
        }
        if department_id is not None:
            update["$set"]["department_id"] = department_id
        if department_name is not None:
            update["$set"]["department_name"] = department_name

        result = self.collection.update_one({"user_id": user_id}, update)
        return result.modified_count > 0
