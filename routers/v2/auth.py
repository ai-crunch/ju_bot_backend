from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from models.user import User, UserDB
from typing import Optional

router = APIRouter(prefix="/v2", tags=["auth"])
user_db = UserDB()


class SignupRequest(BaseModel):
    username: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    username_or_email: str
    password: str


class AuthResponse(BaseModel):
    user_id: str
    username: str
    is_admin: bool
    role: str = "user"
    department_id: Optional[str] = None
    department_name: Optional[str] = None


@router.post("/signup", response_model=AuthResponse)
async def signup(request: SignupRequest):
    # ... check existing ...
    if user_db.get_user_by_username(request.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )
    if user_db.get_user_by_email(request.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    # Hash password and create user
    hashed_password = User.hash_password(request.password)
    user = User(
        username=request.username,
        email=request.email,
        hashed_password=hashed_password,
        role="user",
        is_admin=False,
    )

    user_id = user_db.create_user(user)

    return AuthResponse(
        user_id=user_id,
        username=user.username,
        is_admin=user.is_admin,
        role=user.role,
        department_id=user.department_id,
        department_name=user.department_name,
    )


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    # ... find user ...
    user_data = user_db.get_user_by_username(request.username_or_email)
    if not user_data:
        user_data = user_db.get_user_by_email(request.username_or_email)

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    # Verify password
    if not User.verify_password(request.password, user_data["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    role = user_data.get("role", "user")
    if user_data.get("is_admin") and role != "admin":
        role = "admin"

    return AuthResponse(
        user_id=user_data["user_id"],
        username=user_data["username"],
        is_admin=user_data.get("is_admin", False),
        role=role,
        department_id=user_data.get("department_id"),
        department_name=user_data.get("department_name"),
    )
