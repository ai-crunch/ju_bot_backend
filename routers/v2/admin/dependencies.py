from fastapi import HTTPException, status
from models.user import UserDB

user_db = UserDB()

async def get_current_admin(user_id: str):
    """
    Dependency to verify if a user has administrative privileges.
    
    Responsibility:
    - Ensure only authenticated admin users can access administrative endpoints.
    - Throw 401 if user_id is missing.
    - Throw 403 if user is not found or is not an admin.
    """
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    
    user = user_db.get_user_by_id(user_id)
    if not user or not user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user

