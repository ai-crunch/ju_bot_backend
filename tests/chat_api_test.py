from typing import List, Literal
import requests
from pydantic import BaseModel


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]


def test_chat_api():
    request = ChatRequest(
        messages=[Message(role="user", content="What is the capital of France?")]
    )
    response = requests.post(
        "http://localhost:8000/api/chat", json=request.model_dump()
    )
    print(response.json())
    assert response.status_code == 200


if __name__ == "__main__":
    test_chat_api()
