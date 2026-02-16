"""Lithium - User State Specialist Agent.

Conducts multi-turn conversations to check in on the user's physical/mental state.
Uses MODEL_SMALL for cost efficiency.
"""

from datetime import datetime, timezone
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, ToolMessage
from agents.tools.state_tools import make_state_tools
from agents import get_api_key
from file_logger import logger
import config

SYSTEM_PROMPT_TEMPLATE = """You are Lithium, the User State agent. You are part of a team of agents named after the elements.

Current date/time: {now}

## Purpose
Interview the user to record their current physical/mental state. You need to collect: food (what they ate recently), exercise (recent activity), sleep (last night — duration and quality), energy (1-10), soreness (1-10), sickness (1-10), and any notes.

## Tools
- get_recent_states: Check recent state records (ALWAYS call this first)
- add_user_state: Save the state once you have the information
- finish_conversation: Hand off when user confirms they're done

## Flow
1. Call get_recent_states first.
2. If this is the user's first state check, introduce the concept: "Hi, I'm Lithium, the state check-in agent. I track how you're doing physically so we can make better task recommendations. Let me ask a few quick questions."
3. Ask about food, exercise, and sleep first. Then ask about energy (1-10), soreness (1-10), and sickness (1-10). You can ask 2-3 things at a time.
4. Save partial data as you get it. Don't wait for every field — save what you have and update as you learn more.
5. Summarize what you saved: "Here's your state: [summary]. Anything to add or change?"
6. When the user confirms, call finish_conversation with next_agent="beryllium" (onboarding) or "hydrogen" (returning user).

## Rules
- Stay focused on collecting state data ONLY. Do not offer health advice, tips, sleep recommendations, or any commentary beyond the check-in.
- Do not re-introduce yourself if you already have in this conversation.
- Do not call finish_conversation until the user confirms.
- Save partial information immediately. If the user gives you food and sleep info, save that now — don't wait for energy/soreness/sickness.
- Be warm but efficient. Collect the data, save it, confirm, move on.
- If the user has already provided information in earlier messages, use it — don't ask again."""


def run_lithium(user_id: int, messages: list, context_cache: dict = None) -> dict:
    """Run lithium agent. Returns {response, context_log, hand_off_to}."""
    logger.info(f"[user={user_id}] Lithium processing")
    context_log = []
    if context_cache is None:
        context_cache = {}

    api_key = get_api_key(user_id)
    hand_off = {"to": None}

    base_tools = make_state_tools(user_id)

    @tool
    def finish_conversation(next_agent: str = "hydrogen", summary: str = "") -> str:
        """Finish this conversation and hand off. next_agent should be 'beryllium' for tasks, 'helium' for goals, or 'hydrogen' for the manager."""
        valid = {"hydrogen", "helium", "beryllium"}
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

    context_log.append({"type": "system", "content": system_prompt, "agent": "lithium"})

    for i in range(10):
        logger.debug(f"[user={user_id}] Lithium ReAct iteration {i}")
        response = llm_with_tools.invoke(call_messages)
        call_messages.append(response)

        if not response.tool_calls:
            context_log.append({"type": "ai", "content": response.content, "agent": "lithium"})
            break

        for tc in response.tool_calls:
            tool_fn = tool_map.get(tc["name"])
            if tool_fn:
                logger.info(f"[user={user_id}] Lithium calling tool: {tc['name']}({tc['args']})")
                result = tool_fn.invoke(tc["args"])
                tool_msg = ToolMessage(content=str(result), tool_call_id=tc["id"])
                call_messages.append(tool_msg)
                context_log.append({
                    "type": "tool_call",
                    "name": tc["name"],
                    "args": tc["args"],
                    "result": str(result),
                    "agent": "lithium",
                })

    new_messages = call_messages[num_input_messages:]
    final_text = ""
    for msg in reversed(new_messages):
        if hasattr(msg, "content") and msg.content and hasattr(msg, "type") and msg.type == "ai":
            if not getattr(msg, "tool_calls", None):
                final_text = msg.content
                break
            elif msg.content:
                final_text = msg.content
                break

    logger.info(f"[user={user_id}] Lithium done. hand_off={hand_off['to']}")

    return {
        "response": final_text,
        "context_log": context_log,
        "hand_off_to": hand_off["to"],
    }
