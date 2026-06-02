from fastapi import HTTPException, status
from models.user import UserDB

user_db = UserDB()


async def get_current_department_editor(api_key: str):
    if not api_key:
        raise HTTPException(status_code=401, detail="Authentication required")

    user = user_db.get_user_by_api_key(api_key)
    if not user:
        raise HTTPException(status_code=403, detail="User not found")
    
    role = user.get("role", "user")
    is_admin = user.get("is_admin", False)
    
    if role == "admin" or is_admin:
        return user
    
    if role != "department_editor":
        raise HTTPException(status_code=403, detail="Department editor access required")
    
    if not user.get("department_id"):
        raise HTTPException(status_code=403, detail="User has no assigned department")
    
    return user


def verify_department_ownership(source_payload: dict, user: dict):
    """
    تتحقق أن المصدر يخص قسم المستخدم (لـ department_editor فقط)
    """
    role = user.get("role", "user")
    if role == "admin" or user.get("is_admin"):
        return True  # Admin يشوف كل شيء
    
    source_department = source_payload.get("metadata", {}).get("department_id")
    user_department = user.get("department_id")
    
    if not source_department:
        return False  # المصادر بدون قسم ما يقدر يشوفها department_editor
    
    return source_department == user_department
