"""Helium - Life Goals Specialist Agent.

Conducts multi-turn conversations to help users define their life goals.
Uses MODEL_SMALL for cost efficiency.
"""

from datetime import datetime, timezone
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from agents.tools.life_goal_tools import make_life_goal_tools
from agents import get_api_key
from file_logger import logger
import config

SYSTEM_PROMPT_TEMPLATE = """You are Helium, the Life Goals agent. You are part of a team of agents named after the elements.

Current date/time: {now}

## Purpose
Interview the user to define their life goals. Each goal needs: title, description, priority (1-10), and stress (1-10). Priority = how important this goal is. Stress = how much not having achieved this goal weighs on them day-to-day.

## Tools
- get_life_goals: Check current goals (ALWAYS call this first)
- add_life_goal: Create a goal
- update_life_goal: Modify a goal
- delete_life_goal: Remove a goal
- finish_conversation: Hand off when user confirms they're done

## Flow
1. Call get_life_goals first.
2. If this is the user's first time (no goals), say: "Hello! I'm Helium, the life goals agent. We're your agent team — all named after the elements. Today we'll start your onboarding. First, can you tell me your top life goals?"
3. As the user shares goals, save them immediately — even with partial info. Use reasonable defaults (priority=5, stress=5) if the user hasn't specified. You can always update later.
4. After storing goals, summarize: "Here are the life goals I have for you now: [list]. Do you want to add any or make any changes?"
5. If the user says they're done, call finish_conversation with next_agent="lithium" (for onboarding) or "hydrogen" (if returning user).

## Rules
- Stay focused on life goals ONLY. Do not offer advice, coaching, or commentary outside this scope.
- Do not re-introduce yourself if you've already greeted the user in this conversation.
- Do not call finish_conversation until the user explicitly confirms they're done.
- Save partial information immediately. Don't wait for all fields before saving a goal.
- Be warm but efficient. Gather the data, confirm, move on."""


def run_helium(user_id: int, messages: list, context_cache: dict = None, on_event=None) -> dict:
    """Run helium agent. Returns {response, context_log, hand_off_to}."""
    logger.info(f"[user={user_id}] Helium processing")
    context_log = []
    if context_cache is None:
        context_cache = {}

    api_key = get_api_key(user_id)
    hand_off = {"to": None}

    # Build tools
    base_tools = make_life_goal_tools(user_id)

    @tool
    def finish_conversation(next_agent: str = "hydrogen", summary: str = "") -> str:
        """Finish this conversation and hand off. next_agent should be 'lithium' for state check, 'beryllium' for tasks, or 'hydrogen' for the manager."""
        valid = {"hydrogen", "lithium", "beryllium"}
        if next_agent not in valid:
            next_agent = "hydrogen"
        hand_off["to"] = next_agent
        return f"Handing off to {next_agent}."

    tools = base_tools + [finish_conversation]
    llm = ChatOpenAI(model=config.MODEL_SMALL, api_key=api_key)
    llm_with_tools = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(now=now_str)

    call_messages = [SystemMessage(content=system_prompt)] + messages
    num_input_messages = len(call_messages)

    context_log.append({"type": "system", "content": system_prompt, "agent": "helium"})

    # ReAct loop
    for i in range(10):
        logger.debug(f"[user={user_id}] Helium ReAct iteration {i}")
        if on_event:
            full_response = None
            for chunk in llm_with_tools.stream(call_messages):
                if full_response is None:
                    full_response = chunk
                else:
                    full_response = full_response + chunk
                if chunk.content:
                    on_event("token", {"content": chunk.content, "agent": "helium"})
            response = full_response
        else:
            response = llm_with_tools.invoke(call_messages)
        call_messages.append(response)

        if not response.tool_calls:
            context_log.append({"type": "ai", "content": response.content, "agent": "helium"})
            break

        for tc in response.tool_calls:
            tool_fn = tool_map.get(tc["name"])
            if tool_fn:
                logger.info(f"[user={user_id}] Helium calling tool: {tc['name']}({tc['args']})")
                if on_event:
                    on_event("tool_start", {"tool": tc["name"], "agent": "helium"})
                result = tool_fn.invoke(tc["args"])
                if on_event:
                    on_event("tool_end", {"tool": tc["name"], "agent": "helium"})
                tool_msg = ToolMessage(content=str(result), tool_call_id=tc["id"])
                call_messages.append(tool_msg)
                context_log.append({
                    "type": "tool_call",
                    "name": tc["name"],
                    "args": tc["args"],
                    "result": str(result),
                    "agent": "helium",
                })

    # Extract final response - only from THIS turn's messages
    new_messages = call_messages[num_input_messages:]
    final_text = ""
    for msg in reversed(new_messages):
        if isinstance(msg, AIMessage) and msg.content:
            if not getattr(msg, "tool_calls", None):
                final_text = msg.content
                break
            elif msg.content:
                final_text = msg.content
                break

    logger.info(f"[user={user_id}] Helium done. hand_off={hand_off['to']}")

    return {
        "response": final_text,
        "context_log": context_log,
        "hand_off_to": hand_off["to"],
    }
