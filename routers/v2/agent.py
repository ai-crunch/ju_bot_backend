from fastapi import APIRouter, Depends, HTTPException
from routers.v2.auth import get_current_user
from agno.models.openai import OpenAIChat

from models.qa_messages import ChatRequest, ChatResponse, SourceMetadata, Source
from agent.agent import JUAgent
from utils.vdb import QdrantVDB
from utils.logger import get_logger
from utils.source_handler import enhance_source_metadata
from utils.embedder import Embedder
from utils.semantic_cache import SemanticCache

import config

from models.chat import Chat, ChatDB
from models.message import Message as MessageModel, MessageDB
from models.user import UserDB

logger = get_logger(__name__)

router = APIRouter(
    prefix="/v2/chat",
    tags=["agent", "chat"],
)


def get_agent(user_id: str, chat_id: str):
    # JUAgent now internally handles pulling model from config if not provided
    return JUAgent(user_id=user_id, chat_id=chat_id)


def get_vdb():
    return QdrantVDB()


chat_db = ChatDB()
message_db = MessageDB()
user_db = UserDB()
embedder = Embedder()
semantic_cache = SemanticCache()


@router.post("/agent")
async def response(request: ChatRequest, current_user: dict = Depends(get_current_user)) -> ChatResponse:
    request_dict = request.to_dict()
    messages = request_dict["messages"]
    chat_id = request_dict["chat_id"]
    user_id = current_user["user_id"]

    chat_id = str(chat_id)
    question = messages[-1]["content"]
    logger.info(
        f"Getting request from user for Agent | Chat ID: {chat_id} | User ID: {user_id} | Question: {question}"
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
            type="agent",
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
                type_filter="agent",
                exclude_message_id=user_msg.message_id,
            )

        if cached:
            cached_sources = []
            for src in cached.get("sources", []):
                if isinstance(src, dict):
                    cached_sources.append(Source(**src))
                else:
                    cached_sources.append(src)

            agent_msg = MessageModel(
                user_id=user_id,
                chat_id=chat_id,
                role="assistant",
                content=cached["response"],
                model=config.OPENAI["model"],
                type="agent",
                sources=[s.model_dump() for s in cached_sources],
                cached_from_message_id=cached.get("cached_from_message_id"),
            )
            message_db.add_message(agent_msg)

            logger.info(
                f"Semantic cache HIT in Agent endpoint for user {user_id} | chat {chat_id} | "
                f"cached_from={cached.get('cached_from_message_id')}"
            )
            return ChatResponse(
                response=cached["response"],
                sources=cached_sources,
                chat_id=chat_id,
                message_id=agent_msg.message_id,
            )

        # 5. Generate agent response (cache miss)
        try:
            agent = get_agent(user_id, chat_id)
        except ValueError as ve:
            logger.error(f"Agent configuration error: {ve}")
            raise HTTPException(status_code=503, detail=str(ve))

        response_text, sources_ids = agent.answer(user_id, chat_id, messages)

        vdb = get_vdb()
        sources = vdb.get_sources(sources_ids)
        structured_sources = []
        for source in sources:
            enhanced_source = enhance_source_metadata(source.payload)
            structured_sources.append(Source(**enhanced_source))

        # 6. Store the agent's response
        agent_msg = MessageModel(
            user_id=user_id,
            chat_id=chat_id,
            role="assistant",
            content=response_text,
            model=config.OPENAI["model"],
            type="agent",
            sources=[source.model_dump() for source in structured_sources],
        )
        message_db.add_message(agent_msg)

        chat_response = ChatResponse(
            response=response_text,
            sources=structured_sources,
            chat_id=chat_id,
            message_id=agent_msg.message_id,
        )
        return chat_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in agent response: {e}")
        response = "I'm having trouble answering your question. Please try again."
        structured_sources = []
        chat_response = ChatResponse(
            response=response,
            sources=structured_sources,
            chat_id=chat_id,
        )
        return chat_response
