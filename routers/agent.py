from agno.agent import Agent as AgnoAgent
from agno.models.openai import OpenAIChat
from agno.tools import tool


from fastapi import APIRouter, HTTPException, Response, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Literal, Dict, Any, Optional
from urllib.parse import urlparse
from openai import OpenAI
import os

from dotenv import load_dotenv

from utils.vdb import QdrantVDB
from prompts.qa import QUESTION_PROMPT
from prompts.system import SYSTEM_PROMPT
from models.chat_history import QADict, chat_history_db
from agent.agent import JUAgent
from utils.source_handler import enhance_source_metadata
import config

load_dotenv()

router = APIRouter(
    prefix="/api",
    tags=["chat"],
)

qdrant_vdb = QdrantVDB()
model = OpenAIChat(config.OPENAI["model"])
agent = JUAgent(model=model)


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    chat_id: Optional[str] = None  # Optional chat_id for existing chats


class SourceMetadata(BaseModel):
    filename: Optional[str] = None
    source_title: Optional[str] = None
    source_link: Optional[str] = None
    is_web_source: bool = False
    source_type: Literal["pdf", "web", "document"] = "document"
    display_name: Optional[str] = None
    clickable: bool = False


class Source(BaseModel):
    text: str
    file_path: str
    metadata: Optional[SourceMetadata] = None


class ChatResponse(BaseModel):
    response: str
    sources: List[Source]
    chat_id: str  # Include chat_id in response

    class Config:
        json_encoders = {
            # Ensure proper JSON serialization
        }


def agent_response(messages: List[Message]) -> tuple[str, List[Source]]:
    # Use dummy IDs for V1 if not provided
    user_id = "user_test_id"
    chat_id = "temp_chat_id"
    response_text, sources_ids = agent.answer(user_id, chat_id, messages)

    sources = qdrant_vdb.get_sources(sources_ids)

    # Ensure sources have proper metadata structure
    enhanced_sources = []
    for source in sources:
        # Enhance the source metadata
        enhanced_source_dict = enhance_source_metadata(source.payload)
        enhanced_sources.append(Source(**enhanced_source_dict))

    return response_text, enhanced_sources


@router.post("/agent")
def chat(request: ChatRequest):
    print("Hitting the agent endpoint | Question: ", request.messages[-1].content)

    # Handle chat_id - create new if not provided
    chat_id = request.chat_id
    if not chat_id:
        try:
            chat_id = chat_history_db.create_new_chat()
            print(f"Created new chat with ID: {chat_id}")
        except Exception as e:
            print(f"Error creating new chat: {e}")
            # Continue without chat history if DB fails
            chat_id = "temp_agent_" + str(hash(str(request.messages)))[:8]

    try:
        messages = request.messages
        response, sources = agent_response(messages)

        # Save the Q&A to chat history
        try:
            question = messages[-1].content
            # For agent, the prompt is the full conversation with agent instructions
            prompt = f"Agent conversation with {len(messages)} messages. Last question: {question}"

            # Convert sources to dict format for storage
            references = []
            for source in sources:
                ref_dict = {
                    "text": source.text,
                    "file_path": source.file_path,
                    "metadata": source.metadata.model_dump() if source.metadata else {},
                }
                references.append(ref_dict)

            # Create QADict
            qa_dict = QADict(
                question=question,
                answer=response,
                prompt=prompt,
                references=references,
                feedback=0,  # No feedback initially
                user_feedback_str="",
            )

            # Add to chat history
            chat_history_db.add_message_to_chat(chat_id, qa_dict)
            print(f"Saved agent message to chat history: {chat_id}")

        except Exception as e:
            print(f"Error saving agent response to chat history: {e}")
            # Continue even if chat history fails

    except Exception as e:
        print("Error: ", e)
        response = (
            "I'm sorry, I'm having trouble answering your question. Please try again."
        )
        sources = []

    print("Response: ", response)
    print("Sources: ", sources)
    print("Returning the response")
    return ChatResponse(response=response, sources=sources, chat_id=chat_id)
