import os

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from routers.chat import router as chat_router
from routers.feedback import router as feedback_router
from routers.chat_history import router as chat_history_router
from routers.v2.agent import router as agent_router
from routers.v2.rag import router as rag_router
from routers.v2.auth import router as auth_router
from routers.v2.chats import router as chats_v2_router
from routers.v2.admin.config import router as admin_config_router
from routers.v2.admin.knowledge import router as admin_knowledge_router
from routers.v2.admin.users import router as admin_users_router
from routers.v2.admin.analytics import router as admin_analytics_router
from routers.v2.admin.cache import router as admin_cache_router
from routers.v2.department.knowledge import router as department_knowledge_router
from routers.v2.department.analytics import router as department_analytics_router

import config


_CORS_ORIGINS_RAW = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
CORS_ALLOWED_ORIGINS = (
    [o.strip() for o in _CORS_ORIGINS_RAW.split(",") if o.strip()]
    if _CORS_ORIGINS_RAW
    else ["*"]
)
_ALLOW_CREDENTIALS = CORS_ALLOWED_ORIGINS != ["*"]


class CORSHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        origin = request.headers.get("origin")
        if CORS_ALLOWED_ORIGINS == ["*"]:
            response.headers["Access-Control-Allow-Origin"] = "*"
        elif origin and origin in CORS_ALLOWED_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"

        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, PUT, DELETE, OPTIONS, HEAD"
        )
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "*"

        # Add private network access headers for Chrome's security policy
        response.headers["Access-Control-Allow-Private-Network"] = "true"

        return response


limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add standard CORS middleware first
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Add custom CORS middleware that works with all response types
app.add_middleware(CORSHeaderMiddleware)

app.include_router(chat_router)
app.include_router(rag_router)
app.include_router(agent_router)
app.include_router(auth_router)
app.include_router(chats_v2_router)
app.include_router(admin_config_router)
app.include_router(admin_knowledge_router)
app.include_router(admin_users_router)
app.include_router(admin_analytics_router)
app.include_router(admin_cache_router)
app.include_router(department_knowledge_router)
app.include_router(department_analytics_router)
app.include_router(feedback_router)
app.include_router(chat_history_router)


@app.get("/")
def read_root():
    return {"message": "Hello, World!"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
