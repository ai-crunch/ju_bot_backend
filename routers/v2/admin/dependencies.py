from fastapi import HTTPException, status
from models.user import UserDB

user_db = UserDB()

async def get_current_admin(api_key: str):
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    user = user_db.get_user_by_api_key(api_key)
    if not user or (not user.get("is_admin") and user.get("role") != "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user

