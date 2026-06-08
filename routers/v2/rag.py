import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from routers.v2.auth import get_current_user
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
from utils.embedder import Embedder
from utils.semantic_cache import SemanticCache
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
embedder = Embedder()
semantic_cache = SemanticCache()


def get_active_system_prompt() -> str:
    """Returns the active system prompt from DB config or file fallback."""
    if config.SYSTEM_INSTRUCTIONS:
        return config.SYSTEM_INSTRUCTIONS
    return SYSTEM_PROMPT


def get_llm_response(messages: List[dict]) -> str:
    client = get_openai_client()
    response = client.chat.completions.create(
        model=config.OPENAI["model"],
        temperature=config.OPENAI["temperature"],
        max_tokens=config.MAX_TOKENS,
        messages=[{"role": "system", "content": get_active_system_prompt()}] + messages,
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
async def response(request: ChatRequest, current_user: dict = Depends(get_current_user)) -> ChatResponse:
    messages = request.messages
    chat_id = request.chat_id
    user_id = current_user["user_id"]

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

        # 3. Embed and store the user's message
        question_embedding = embedder.embed([question], is_query=True)[0]
        user_msg = MessageModel(
            user_id=user_id,
            chat_id=chat_id,
            role="user",
            content=question,
            type="rag",
            embedding=question_embedding,
        )
        message_db.add_message(user_msg)

        # 4. Semantic cache lookup
        cached = None
        if config.SEMANTIC_CACHE.get("enabled", True):
            cached = semantic_cache.lookup(
                user_id=user_id,
                question=question,
                question_embedding=question_embedding,
                type_filter="rag",
                exclude_message_id=user_msg.message_id,
            )

        if cached:
            # Reconstruct Source objects from cached dicts
            cached_sources = []
            for src in cached.get("sources", []):
                if isinstance(src, dict):
                    cached_sources.append(Source(**src))
                else:
                    cached_sources.append(src)

            assistant_msg = MessageModel(
                user_id=user_id,
                chat_id=chat_id,
                role="assistant",
                content=cached["response"],
                model=config.OPENAI["model"],
                type="rag",
                sources=[s.model_dump() for s in cached_sources],
                cached_from_message_id=cached.get("cached_from_message_id"),
            )
            message_db.add_message(assistant_msg)

            logger.info(
                f"Semantic cache HIT in RAG endpoint for user {user_id} | chat {chat_id} | "
                f"cached_from={cached.get('cached_from_message_id')}"
            )
            return ChatResponse(
                response=cached["response"],
                sources=cached_sources,
                chat_id=chat_id,
                message_id=assistant_msg.message_id,
            )

        # 5. Generate assistant response (cache miss)
        response_text, sources = answer(messages)

        # 6. Store the assistant's response
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
            message_id=assistant_msg.message_id,
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


@router.post("/rag/stream")
async def stream_response(request: ChatRequest, current_user: dict = Depends(get_current_user)):
    messages = request.messages
    chat_id = request.chat_id
    user_id = current_user["user_id"]

    chat_id = str(chat_id)
    question = messages[-1].content
    logger.info(
        f"Streaming RAG request | Chat ID: {chat_id} | User ID: {user_id} | Question: {question}"
    )

    def generate():
        nonlocal chat_id
        try:
            # 1. Handle chat lookup and validation
            if chat_id != "-1":
                chat_data = chat_db.get_chat_by_id(chat_id)
                if not chat_data:
                    logger.warning(f"Chat {chat_id} not found, falling back to new chat")
                    chat_id = "-1"
                else:
                    is_owner = str(chat_data["user_id"]) == str(user_id)
                    if not is_owner:
                        user = user_db.get_user_by_id(user_id)
                        is_admin = user.get("is_admin", False) if user else False
                        if not is_admin:
                            chat_id = "-1"

            # 2. Handle new chat creation
            if chat_id == "-1":
                title = (question[:50] + "...") if len(question) > 50 else question
                chat = Chat(user_id=user_id, title=title)
                chat_id = chat.chat_id
                chat_db.collection.insert_one(chat.model_dump())
                logger.info(f"Created new chat {chat_id}")

            # 3. Embed and store user message
            question_embedding = embedder.embed([question], is_query=True)[0]
            user_msg = MessageModel(
                user_id=user_id,
                chat_id=chat_id,
                role="user",
                content=question,
                type="rag",
                embedding=question_embedding,
            )
            message_db.add_message(user_msg)

            # 4. Semantic cache lookup
            cached = None
            if config.SEMANTIC_CACHE.get("enabled", True):
                cached = semantic_cache.lookup(
                    user_id=user_id,
                    question=question,
                    question_embedding=question_embedding,
                    type_filter="rag",
                    exclude_message_id=user_msg.message_id,
                )

            if cached:
                full_response = cached["response"]
                cached_sources = []
                for src in cached.get("sources", []):
                    if isinstance(src, dict):
                        cached_sources.append(Source(**src))
                    else:
                        cached_sources.append(src)

                yield f"data: {json.dumps({'type': 'chunk', 'content': full_response})}\n\n"

                assistant_msg = MessageModel(
                    user_id=user_id,
                    chat_id=chat_id,
                    role="assistant",
                    content=full_response,
                    model=config.OPENAI["model"],
                    type="rag",
                    sources=[s.model_dump() for s in cached_sources],
                    cached_from_message_id=cached.get("cached_from_message_id"),
                )
                message_db.add_message(assistant_msg)

                sources_data = [s.model_dump() for s in cached_sources]
                yield f"data: {json.dumps({'type': 'sources', 'content': sources_data, 'chat_id': chat_id, 'message_id': assistant_msg.message_id})}\n\n"
                yield "data: [DONE]\n\n"
                return

            # 5. Retrieve sources
            results, sources_ids = retrieve(question)
            vdb = get_vdb()
            source_records = vdb.get_sources(sources_ids)
            structured_sources = []
            for source in source_records:
                enhanced = enhance_source_metadata(source.payload)
                structured_sources.append(Source(**enhanced))

            # 6. Stream the LLM response
            conv_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            for m in messages[:-1]:
                conv_messages.append({"role": m.role, "content": m.content})

            sources_text = "\n".join(
                [f"Source {i+1}: {r.payload['text']}" for i, r in enumerate(results)]
            )
            prompt = QUESTION_PROMPT.format(sources=sources_text, question=question)
            conv_messages.append({"role": "user", "content": prompt})

            client = get_openai_client()
            stream = client.chat.completions.create(
                model=config.OPENAI["model"],
                temperature=config.OPENAI["temperature"],
                messages=conv_messages,
                stream=True,
            )

            full_response = ""
            for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        content = delta.content
                        full_response += content
                        yield f"data: {json.dumps({'type': 'chunk', 'content': content})}\n\n"

            # 7. Store assistant message
            assistant_msg = MessageModel(
                user_id=user_id,
                chat_id=chat_id,
                role="assistant",
                content=full_response,
                model=config.OPENAI["model"],
                type="rag",
                sources=[s.model_dump() for s in structured_sources],
            )
            message_db.add_message(assistant_msg)

            # 8. Send sources + done
            sources_data = [s.model_dump() for s in structured_sources]
            yield f"data: {json.dumps({'type': 'sources', 'content': sources_data, 'chat_id': chat_id, 'message_id': assistant_msg.message_id})}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Error in streaming RAG: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
