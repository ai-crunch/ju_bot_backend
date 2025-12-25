from typing import List, Callable, Tuple
from pydantic import BaseModel, Field
from pymongo import MongoClient

from agno.agent import Agent
from agno.db.mongo import MongoDb
from agno.models.openai import OpenAIChat
from agno.utils.response import RunOutput

from agent.tools import tools
from agent.role import ROLE
from agent.description import DESCRIPTION
from agent.instructions import INSTRUCTIONS
from prompts.system import SYSTEM_PROMPT

from models.qa_messages import Message
from utils.logger import get_logger

import config

logger = get_logger(__name__)


class AgentOutputSchema(BaseModel):
    response: str = Field(description="The response to the question")
    sources: List[int] = Field(
        description="The sources IDs used to answer the question"
    )


mongo_client = MongoClient(config.MONGO_CONNECTION_STRING)
mongo = MongoDb(
    db_client=mongo_client,
    db_name=config.MONGODB["database"],
)


class JUAgent:
    """
    JU Agent class for the chatbot using Agno framework

    Args:
        model: The model to use for the agent
        user_id: The user ID
        chat_id: The chat ID
        name: The name of the agent
        description: The description of the agent
        instructions: The instructions of the agent
        role: The role of the agent
        system_message: The system message of the agent
        output_schema: The output schema of the agent
        tools: The tools of the agent
        add_history_to_context: Whether to add the history to the context
    """

    def __init__(
        self,
        model: OpenAIChat | None = None,
        user_id: str | None = None,
        chat_id: str | None = None,
        name: str = "JU Bot",
        description: str = DESCRIPTION,
        instructions: str = INSTRUCTIONS,
        role: str = ROLE,
        system_message: str = SYSTEM_PROMPT,
        output_schema: BaseModel = AgentOutputSchema,
        tools: List[Callable] = tools,
        add_history_to_context: bool = True,
    ):
        if model is None:
            model = OpenAIChat(
                id=config.OPENAI["model"],
                api_key=config.OPENAI["api_key"],
                temperature=config.OPENAI["temperature"],
            )

        # Apply reasoning instructions if enabled in system config
        if config.ENABLE_REASONING:
            instructions += "\n\nREASONING ENABLED: Please provide a detailed step-by-step reasoning for your answer before providing the final response."

        self.agent = Agent(
            # Agent General Settings
            user_id=user_id,
            session_id=chat_id,
            model=model,
            name=name,
            # Agent description and instructions
            description=description,
            instructions=instructions,
            role=role,
            system_message=system_message,
            # Agent Output Schema
            output_schema=output_schema,
            tools=tools,
            tool_call_limit=10,
            # Agent Context
            add_history_to_context=add_history_to_context,
            debug_mode=True,
            # Agent DB (MongoDB)
            db=mongo,
            enable_user_memories=True,  # This enables Memory for the Agent
            enable_agentic_memory=True,
            add_memories_to_context=True,
        )

    def answer(
        self,
        user_id: str,
        chat_id: str,
        messages: List[Message],
    ) -> Tuple[str, List[int]]:
        """
        Answer a question using the agent

        Args:
            user_id: The user ID
            chat_id: The chat ID
            messages: The messages to answer

        Returns:
            The response and the sources IDs
        """
        result: RunOutput = self.agent.run(
            input=messages,
            user_id=user_id,
            chat_id=chat_id,
            add_history_to_context=True,
        )
        result = AgentOutputSchema.model_validate(result.content)
        response = result.response
        sources_ids = result.sources
        logger.info(f"Response: {response} | Sources IDs: {sources_ids}")
        return response, sources_ids
