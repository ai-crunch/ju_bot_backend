from fastapi import APIRouter, HTTPException
from openai import OpenAI
from typing import List, Tuple
from qdrant_client.http.models import Record

from models.qa_messages import (
    ChatRequest,
    ChatResponse,
    SourceMetadata,
    Source,
    Message,
)
from utils.vdb import QdrantVDB
from utils.logger import get_logger
from utils.source_handler import enhance_source_metadata
from prompts.system import SYSTEM_PROMPT
from prompts.qa import QUESTION_PROMPT

import config

logger = get_logger(__name__)

router = APIRouter(
    prefix="/v2/chat",
    tags=["rag", "chat"],
)

from models.chat import Chat, ChatDB
from models.message import Message as MessageModel, MessageDB
from models.user import UserDB


def get_vdb():
    return QdrantVDB()


def get_openai_client():
    return OpenAI(api_key=config.OPENAI["api_key"])


chat_db = ChatDB()
message_db = MessageDB()
user_db = UserDB()


def get_llm_response(messages: List[dict]) -> str:
    client = get_openai_client()
    response = client.chat.completions.create(
        model=config.OPENAI["model"],
        temperature=config.OPENAI["temperature"],
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
    )
    return response.choices[0].message.content


def retrieve(question: str) -> Tuple[List[Record], List[int]]:
    vdb = get_vdb()
    results = vdb.retrieve(question)
    sources_ids = [result.id for result in results]
    return results, sources_ids


def get_llm_answer(messages: List[dict], question: str, results: List[Record]):
    sources_text = "\n".join(
        [f"Source {i+1}: {result.payload['text']}" for i, result in enumerate(results)]
    )
    prompt = QUESTION_PROMPT.format(sources=sources_text, question=question)
    new_messages = messages + [{"role": "user", "content": prompt}]
    response = get_llm_response(new_messages)
    return response


def answer(messages: List[Message]) -> tuple[str, List[Source]]:
    question = messages[-1].content
    messages = [{"role": msg.role, "content": msg.content} for msg in messages[:-1]]
    results, sources_ids = retrieve(question)
    response = get_llm_answer(messages, question, results)

    vdb = get_vdb()
    sources = vdb.get_sources(sources_ids)
    structured_sources = []
    for source in sources:
        enhanced_source = enhance_source_metadata(source.payload)
        structured_sources.append(Source(**enhanced_source))

    return response, structured_sources


@router.post("/rag")
async def response(request: ChatRequest) -> ChatResponse:
    messages = request.messages
    chat_id = request.chat_id
    user_id = request.user_id

    if not user_id:
        user_id = "user_test_id"

    chat_id = str(chat_id)
    question = messages[-1].content
    logger.info(
        f"Getting request from user for RAG | Chat ID: {chat_id} | User ID: {user_id} | Question: {question}"
    )
    try:
        # 1. Handle chat lookup and validation
        if chat_id != "-1":
            # Validate chat ownership for existing chats
            chat_data = chat_db.get_chat_by_id(chat_id)

            # If chat doesn't exist, start a new one
            if not chat_data:
                logger.warning(
                    f"Chat {chat_id} not found, falling back to new chat creation"
                )
                chat_id = "-1"
            else:
                # Allow access if it's the owner OR if requester is an admin
                is_owner = str(chat_data["user_id"]) == str(user_id)
                if not is_owner:
                    # Check if user is an admin
                    user = user_db.get_user_by_id(user_id)
                    is_admin = user.get("is_admin", False) if user else False
                    if not is_admin:
                        logger.warning(
                            f"Access denied for user {user_id} to chat {chat_id}, falling back to new chat"
                        )
                        chat_id = "-1"

        # 2. Handle new chat creation (either explicit or fallback)
        if chat_id == "-1":
            # Generate title from the first message
            title = (question[:50] + "...") if len(question) > 50 else question

            # Create the chat entry in MongoDB with a unique UUID (handled by Chat model)
            chat = Chat(user_id=user_id, title=title)
            chat_id = chat.chat_id
            chat_db.collection.insert_one(chat.model_dump())
            logger.info(f"Created new chat for user {user_id} with ID: {chat_id}")

        # 3. Store the user's message
        user_msg = MessageModel(
            user_id=user_id,
            chat_id=chat_id,
            role="user",
            content=question,
            type="rag",
        )
        message_db.add_message(user_msg)

        # 4. Generate assistant response
        response_text, sources = answer(messages)

        # 5. Store the assistant's response
        assistant_msg = MessageModel(
            user_id=user_id,
            chat_id=chat_id,
            role="assistant",
            content=response_text,
            model=config.OPENAI["model"],
            type="rag",
            sources=[source.model_dump() for source in sources],
        )
        message_db.add_message(assistant_msg)

        chat_response = ChatResponse(
            response=response_text,
            sources=sources,
            chat_id=chat_id,
        )
        return chat_response

    except Exception as e:
        logger.error(f"Error in RAG response: {e}")
        response_text = "I'm having trouble answering your question. Please try again."
        sources = []
        chat_response = ChatResponse(
            response=response_text,
            sources=sources,
            chat_id=chat_id,
        )
        return chat_response
