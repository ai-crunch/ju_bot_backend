import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from routers.chat import router as chat_router
from routers.agent import router as agent_router
from routers.feedback import router as feedback_router
from routers.chat_history import router as chat_history_router

import config


class CORSHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Add CORS headers to all responses, including file responses
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, PUT, DELETE, OPTIONS, HEAD"
        )
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "*"

        # Add private network access headers for Chrome's security policy
        response.headers["Access-Control-Allow-Private-Network"] = "true"

        return response


app = FastAPI()

# Add standard CORS middleware first
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=False,  # Set to False when using allow_origins=["*"]
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Add custom CORS middleware that works with all response types
app.add_middleware(CORSHeaderMiddleware)

app.include_router(chat_router)
app.include_router(agent_router)
app.include_router(feedback_router)
app.include_router(chat_history_router)


@app.get("/")
def read_root():
    return {"message": "Hello, World!"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
