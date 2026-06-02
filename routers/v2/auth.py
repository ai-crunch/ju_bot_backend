from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from models.user import User, UserDB
from typing import Optional

router = APIRouter(prefix="/v2", tags=["auth"])
user_db = UserDB()


def get_current_user(api_key: str) -> dict:
    if not api_key:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = user_db.get_user_by_api_key(api_key)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


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
    api_key: str = ""
    requires_2fa: bool = False
    temp_token: Optional[str] = None
    department_id: Optional[str] = None
    department_name: Optional[str] = None


class TwoFactorRequest(BaseModel):
    temp_token: str
    code: str


@router.post("/user/2fa/setup")
async def setup_2fa(user: dict = Depends(get_current_user)):
    import pyotp, base64
    secret = pyotp.random_base32()
    user_db.collection.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"totp_secret": secret}},
    )
    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=user["email"], issuer_name="JU Assistant"
    )
    return {"secret": secret, "uri": uri}


@router.post("/user/2fa/verify")
async def verify_2fa(code: str, user: dict = Depends(get_current_user)):
    import pyotp
    secret = user.get("totp_secret")
    if not secret:
        raise HTTPException(status_code=400, detail="2FA not set up")
    totp = pyotp.TOTP(secret)
    if not totp.verify(code):
        raise HTTPException(status_code=400, detail="Invalid code")
    user_db.collection.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"two_factor_enabled": True}},
    )
    return {"message": "2FA enabled successfully"}


@router.post("/user/2fa/disable")
async def disable_2fa(user: dict = Depends(get_current_user)):
    user_db.collection.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"totp_secret": None, "two_factor_enabled": False}},
    )
    return {"message": "2FA disabled"}


@router.post("/signup", response_model=AuthResponse)
async def signup(request: SignupRequest):
    if user_db.get_user_by_username(request.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )
    if user_db.get_user_by_email(request.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    hashed_password = User.hash_password(request.password)
    token = str(__import__("uuid").uuid4())
    user = User(
        username=request.username,
        email=request.email,
        hashed_password=hashed_password,
        role="user",
        is_admin=False,
        verification_token=token,
    )

    logger = __import__("logging").getLogger("auth")
    logger.info(
        f"Verification link (dev): http://localhost:8000/v2/verify-email?token={token}"
    )

    user_id = user_db.create_user(user)
    created = user_db.get_user_by_id(user_id)

    return AuthResponse(
        user_id=user_id,
        username=user.username,
        is_admin=user.is_admin,
        role=user.role,
        api_key=created["api_key"],
        department_id=user.department_id,
        department_name=user.department_name,
    )


class UpdateProfileRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class UpdateProfileResponse(BaseModel):
    user_id: str
    username: str
    email: str


@router.put("/user", response_model=UpdateProfileResponse)
async def update_profile(request: UpdateProfileRequest, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]

    if not request.username and not request.email:
        raise HTTPException(status_code=400, detail="Nothing to update")

    success = user_db.update_user(
        user_id,
        username=request.username,
        email=request.email,
    )
    if not success:
        raise HTTPException(
            status_code=400, detail="Username or email already taken"
        )

    updated = user_db.get_user_by_id(user_id)
    return UpdateProfileResponse(
        user_id=updated["user_id"],
        username=updated["username"],
        email=updated["email"],
    )


@router.post("/user/change-password")
async def change_password(request: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    user_id = user["user_id"]

    if not User.verify_password(request.old_password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    new_hashed = User.hash_password(request.new_password)
    user_db.change_password(user_id, new_hashed)
    return {"message": "Password changed successfully"}


@router.get("/verify-email")
async def verify_email(token: str):
    user_data = user_db.collection.find_one({"verification_token": token})
    if not user_data:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    user_db.collection.update_one(
        {"user_id": user_data["user_id"]},
        {"$set": {"email_verified": True, "verification_token": None}},
    )

    logger = __import__("logging").getLogger("auth")
    logger.info(f"Email verified for user {user_data['user_id']}")
    return {"message": "Email verified successfully"}


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    user_data = user_db.get_user_by_username(request.username_or_email)
    if not user_data:
        user_data = user_db.get_user_by_email(request.username_or_email)

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    if not User.verify_password(request.password, user_data["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    role = user_data.get("role", "user")
    if user_data.get("is_admin") and role != "admin":
        role = "admin"

    if user_data.get("two_factor_enabled"):
        temp_token = str(__import__("uuid").uuid4())
        user_db.collection.update_one(
            {"user_id": user_data["user_id"]},
            {"$set": {"temp_token": temp_token}},
        )
        return AuthResponse(
            user_id=user_data["user_id"],
            username=user_data["username"],
            is_admin=user_data.get("is_admin", False),
            role=role,
            requires_2fa=True,
            temp_token=temp_token,
        )

    api_key = user_db.ensure_api_key(user_data["user_id"])

    return AuthResponse(
        user_id=user_data["user_id"],
        username=user_data["username"],
        is_admin=user_data.get("is_admin", False),
        role=role,
        api_key=api_key,
        department_id=user_data.get("department_id"),
        department_name=user_data.get("department_name"),
    )


@router.post("/login/2fa", response_model=AuthResponse)
async def login_2fa(request: TwoFactorRequest):
    user_data = user_db.collection.find_one({"temp_token": request.temp_token})
    if not user_data:
        raise HTTPException(status_code=400, detail="Invalid or expired temp token")

    import pyotp
    secret = user_data.get("totp_secret")
    if not secret:
        raise HTTPException(status_code=400, detail="2FA not configured")

    totp = pyotp.TOTP(secret)
    if not totp.verify(request.code):
        raise HTTPException(status_code=400, detail="Invalid 2FA code")

    user_db.collection.update_one(
        {"user_id": user_data["user_id"]},
        {"$set": {"temp_token": None}},
    )

    api_key = user_db.ensure_api_key(user_data["user_id"])
    role = user_data.get("role", "user")
    if user_data.get("is_admin") and role != "admin":
        role = "admin"

    return AuthResponse(
        user_id=user_data["user_id"],
        username=user_data["username"],
        is_admin=user_data.get("is_admin", False),
        role=role,
        api_key=api_key,
        department_id=user_data.get("department_id"),
        department_name=user_data.get("department_name"),
    )


@router.post("/logout")
async def logout(user: dict = Depends(get_current_user)):
    user_db.rotate_api_key(user["user_id"])
    return {"message": "Logged out successfully"}
