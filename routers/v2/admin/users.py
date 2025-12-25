from fastapi import APIRouter, Depends, HTTPException, status
from models.user import UserDB
from models.database import MongoDB
from routers.v2.admin.dependencies import get_current_admin
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/users", tags=["admin-users"])

"""
Admin Users Router
Responsibility:
- Compute and provide usage analytics across all users.
- Manage administrative privileges (promote/demote users).
- Restrict access to administrative users only.
"""

user_db = UserDB()

@router.get("/")
async def get_users_analytics(user: dict = Depends(get_current_admin)):
    """
    Returns a list of all users with their computed engagement analytics.
    Requires administrative privileges.
    """
    try:
        db = MongoDB.get_db()
        
        # 1. Count chats per user
        chat_stats = list(db["chats"].aggregate([
            {
                "$group": {
                    "_id": "$user_id",
                    "total_chats": {"$sum": 1}
                }
            }
        ]))
        chat_map = {item["_id"]: item["total_chats"] for item in chat_stats}
        
        # 2. Count messages and feedback per user
        message_stats = list(db["messages"].aggregate([
            {
                "$group": {
                    "_id": "$user_id",
                    "total_messages": {"$sum": 1},
                    "thumbs_up": {
                        "$sum": {"$cond": [{"$eq": ["$feedback", 1]}, 1, 0]}
                    },
                    "thumbs_down": {
                        "$sum": {"$cond": [{"$eq": ["$feedback", -1]}, 1, 0]}
                    }
                }
            }
        ]))
        message_map = {item["_id"]: item for item in message_stats}
        
        # 3. Get all users and merge with stats
        users = user_db.get_all_users()
        
        analytics = []
        for u in users:
            uid = u["user_id"]
            m_stats = message_map.get(uid, {"total_messages": 0, "thumbs_up": 0, "thumbs_down": 0})
            
            total_messages = m_stats["total_messages"]
            thumbs_up = m_stats["thumbs_up"]
            thumbs_down = m_stats["thumbs_down"]
            
            # Calculate helpfulness ratio
            total_feedback = thumbs_up + thumbs_down
            ratio = (thumbs_up / total_feedback * 100) if total_feedback > 0 else 0
            
            analytics.append({
                "user_id": uid,
                "username": u["username"],
                "email": u["email"],
                "is_admin": u.get("is_admin", False),
                "total_chats": chat_map.get(uid, 0),
                "total_messages": total_messages,
                "thumbs_up_ratio": round(ratio, 1)
            })
            
        return analytics
        
    except Exception as e:
        logger.error(f"Error fetching user analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch user analytics: {str(e)}"
        )

@router.put("/{target_user_id}/toggle-admin")
async def toggle_user_admin(target_user_id: str, current_admin: dict = Depends(get_current_admin)):
    """
    Toggles the administrative status of a target user.
    Requires administrative privileges.
    """
    success = user_db.toggle_admin(target_user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found or status update failed"
        )
    
    updated_user = user_db.get_user_by_id(target_user_id)
    return {
        "message": f"User admin status toggled to {updated_user['is_admin']}",
        "is_admin": updated_user["is_admin"]
    }
