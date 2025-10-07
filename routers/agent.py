from agno.agent import Agent
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

import config

load_dotenv()

router = APIRouter(
    prefix="/api",
    tags=["chat"],
)

qdrant_vdb = QdrantVDB()
# client = OpenAI(api_key=config.OPENAI["api_key"])


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]


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

    class Config:
        json_encoders = {
            # Ensure proper JSON serialization
        }


@tool(
    name="get_document",
    description="Get a document from the database",
)
def get_document(query: str) -> List[Source]:
    results = qdrant_vdb.retrieve(query)
    sources = []
    for result in results:
        # Process the source data to enhance metadata
        enhanced_source = enhance_source_metadata(result.payload)
        sources.append(Source(**enhanced_source))
    return sources


def enhance_source_metadata(source_data: dict) -> dict:
    """Enhance source metadata for better frontend display"""
    file_path = source_data.get("file_path", "")
    metadata = source_data.get("metadata") or {}

    # Create enhanced metadata
    enhanced_metadata = SourceMetadata()

    # Determine if it's a web source
    parsed_url = urlparse(file_path)
    is_web_source = bool(parsed_url.scheme and parsed_url.netloc)

    if is_web_source:
        # Web source
        enhanced_metadata.is_web_source = True
        enhanced_metadata.source_type = "web"
        enhanced_metadata.source_link = file_path
        enhanced_metadata.clickable = True

        # Try to get title from metadata or create from URL
        if isinstance(metadata, dict) and metadata.get("source_title"):
            enhanced_metadata.source_title = metadata["source_title"]
            enhanced_metadata.display_name = metadata["source_title"]
        else:
            # Create a display name from URL
            domain = parsed_url.netloc
            enhanced_metadata.source_title = f"مصدر من {domain}"
            enhanced_metadata.display_name = f"مصدر من {domain}"
    else:
        # PDF or local file source
        enhanced_metadata.is_web_source = False
        enhanced_metadata.source_type = (
            "pdf" if file_path.lower().endswith(".pdf") else "document"
        )
        enhanced_metadata.clickable = file_path.lower().endswith(".pdf")

        # Extract filename and title
        if isinstance(metadata, dict):
            enhanced_metadata.filename = metadata.get("filename")
            enhanced_metadata.source_title = metadata.get("source_title")

        # Create display name
        if enhanced_metadata.source_title:
            enhanced_metadata.display_name = enhanced_metadata.source_title
        elif enhanced_metadata.filename:
            # Remove extension from filename for display
            display_name = enhanced_metadata.filename
            if "." in display_name:
                display_name = display_name.rsplit(".", 1)[0]
            enhanced_metadata.display_name = display_name
        else:
            enhanced_metadata.display_name = "مستند"

    # Return enhanced source data
    return {
        "text": source_data.get("text", ""),
        "file_path": file_path,
        "metadata": enhanced_metadata.model_dump(),
    }


DESCRIPTION = """
You are JU Bot, an intelligent assistant designed to help users navigate and understand information from the University of Jordan documents and resources. You have access to a comprehensive knowledge base containing university-related documents, policies, academic information, and other institutional resources.

This chatbot was developed by AI Crunch to serve the University of Jordan community.

Your primary responsibilities include:

1. **Document Analysis**: Analyze and extract relevant information from the provided source documents to answer user queries accurately.

2. **Contextual Understanding**: Understand the context of questions related to the University of Jordan, including academic programs, policies, procedures, events, and general university information.

3. **Accurate Responses**: Provide precise, well-structured answers based solely on the information available in the source documents. If information is not available in the sources, clearly state this limitation.

4. **Source Attribution**: Always reference the specific documents or sources when providing information, helping users understand where the information comes from.

5. **Helpful Guidance**: Assist users in finding the information they need, whether it's about admissions, academic requirements, university policies, or other institutional matters.

Guidelines for responses:
- Be concise yet comprehensive in your answers
- Use clear, professional language appropriate for an academic institution
- When multiple sources contain relevant information, synthesize them coherently
- If a question cannot be answered from the available sources, suggest alternative ways the user might find the information
- Maintain a helpful and supportive tone while being factually accurate

Remember: You are representing the University of Jordan through your responses, so maintain professionalism and accuracy at all times.
"""

INSTRUCTIONS = """
1) Search the database for the most relevant documents to the question
2) If the question is not related to the university, say that you are not sure about the answer
3) If the question is related to the university, answer the question based on the documents
4) If the question is greeting and persona, answer with a greeting and a short introduction about yourself
5) If the resources are not enough to answer the question, say that you are not sure about the answer
"""

ROLE = """
You are JU Bot, an intelligent assistant designed to help users navigate and understand information from the University of Jordan documents and resources. You have access to a comprehensive knowledge base containing university-related documents, policies, academic information, and other institutional resources.
"""

agent = Agent(
    model=OpenAIChat("gpt-4o-2024-08-06"),  # gpt-4o-2024-08-06
    name="JU Bot",
    description=DESCRIPTION,
    instructions=INSTRUCTIONS,
    role=ROLE,
    system_message=SYSTEM_PROMPT,
    # structured_output=True,
    output_schema=ChatResponse,
    tools=[
        get_document,
    ],
)


def agent_response(messages: List[Message]) -> tuple[str, List[Source]]:
    response = agent.run(messages)
    agent_response = response.content
    print("Response: ", agent_response)

    # Ensure sources have proper metadata structure
    enhanced_sources = []
    for source in agent_response.sources:
        # Convert source to dict if it's a Pydantic model
        if hasattr(source, "model_dump"):
            source_dict = source.model_dump()
        elif hasattr(source, "dict"):
            source_dict = source.dict()
        else:
            source_dict = source

        # Enhance the source metadata
        enhanced_source_dict = enhance_source_metadata(source_dict)
        enhanced_sources.append(Source(**enhanced_source_dict))

    return agent_response.response, enhanced_sources


@router.post("/agent")
def chat(request: ChatRequest):
    print("Hitting the agent endpoint | Question: ", request.messages[-1].content)

    try:
        messages = request.messages
        response, sources = agent_response(messages)
    except Exception as e:
        print("Error: ", e)
        response = (
            "I'm sorry, I'm having trouble answering your question. Please try again."
        )
        sources = []

    print("Response: ", response)
    print("Sources: ", sources)
    print("Returning the response")
    return ChatResponse(response=response, sources=sources)
