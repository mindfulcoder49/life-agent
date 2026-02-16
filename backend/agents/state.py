from typing import TypedDict, Annotated, Literal
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: int
    next_agent: Literal["hydrogen", "helium", "lithium", "beryllium", "__end__"]
    agent_context: dict
    full_context_log: list[dict]
