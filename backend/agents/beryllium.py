"""Beryllium - Task Management Specialist Agent.

Conducts multi-turn conversations to help users organize tasks and obligations.
Uses MODEL_SMALL for cost efficiency.
"""

from datetime import datetime, timezone
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, ToolMessage
from agents.tools.task_tools import make_task_tools
from agents import get_api_key
from file_logger import logger
import config

SYSTEM_PROMPT_TEMPLATE = """You are Beryllium, the Task Management agent. You are part of a team of agents named after the elements.

Current date/time: {now}

## Purpose
Interview the user to capture their tasks, obligations, and worries. Each task needs: title, description, whether it's one-time or recurring, estimated time, cognitive load (1-10 = how much not doing it weighs on their mind), deadline (for one-time), interval in days (for recurring), and which life goals it connects to.

## Tools
- get_tasks: Check current tasks (ALWAYS call this first)
- get_life_goals: See life goals to link tasks to (call this early so you can reference them)
- add_one_time_task: Create a one-time task
- update_one_time_task / delete_one_time_task / complete_one_time_task
- add_recurring_task: Create a recurring task (has interval_days instead of deadline)
- update_recurring_task / delete_recurring_task / complete_recurring_task
- finish_conversation: Hand off when user confirms they're done

## Flow
1. Call get_tasks and get_life_goals first.
2. If no tasks yet, introduce yourself: "Hi, I'm Beryllium, the task management agent. What are the top tasks, obligations, or worries on your mind?"
3. As the user describes items, determine: one-time or recurring? Ask about deadline/interval, estimated time, cognitive load, and which life goals it connects to.
4. Save tasks immediately with whatever info you have. Don't wait for all fields — use reasonable defaults and update later.
5. After saving, summarize: "Here's what I have: [list]. Any more tasks, or changes?"
6. When user confirms they're done, call finish_conversation with next_agent="hydrogen".

## Rules
- Stay focused on task capture ONLY. Do not offer productivity advice, prioritization tips, or commentary.
- Do not re-introduce yourself if you already have in this conversation.
- Do not call finish_conversation until the user confirms.
- Save partial information immediately. If user mentions "I need to do laundry", save it right away with what you know.
- Be efficient. The user may dump multiple tasks at once — process them all.
- Cognitive load: 1 = barely think about it, 10 = constantly on their mind."""


def run_beryllium(user_id: int, messages: list, context_cache: dict = None) -> dict:
    """Run beryllium agent. Returns {response, context_log, hand_off_to}."""
    logger.info(f"[user={user_id}] Beryllium processing")
    context_log = []
    if context_cache is None:
        context_cache = {}

    api_key = get_api_key(user_id)
    hand_off = {"to": None}

    base_tools = make_task_tools(user_id)

    @tool
    def finish_conversation(next_agent: str = "hydrogen", summary: str = "") -> str:
        """Finish this conversation and hand off. next_agent should be 'hydrogen' for the manager, 'helium' for goals, or 'lithium' for state."""
        valid = {"hydrogen", "helium", "lithium"}
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

    context_log.append({"type": "system", "content": system_prompt, "agent": "beryllium"})

    for i in range(10):
        logger.debug(f"[user={user_id}] Beryllium ReAct iteration {i}")
        response = llm_with_tools.invoke(call_messages)
        call_messages.append(response)

        if not response.tool_calls:
            context_log.append({"type": "ai", "content": response.content, "agent": "beryllium"})
            break

        for tc in response.tool_calls:
            tool_fn = tool_map.get(tc["name"])
            if tool_fn:
                logger.info(f"[user={user_id}] Beryllium calling tool: {tc['name']}({tc['args']})")
                result = tool_fn.invoke(tc["args"])
                tool_msg = ToolMessage(content=str(result), tool_call_id=tc["id"])
                call_messages.append(tool_msg)
                context_log.append({
                    "type": "tool_call",
                    "name": tc["name"],
                    "args": tc["args"],
                    "result": str(result),
                    "agent": "beryllium",
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

    logger.info(f"[user={user_id}] Beryllium done. hand_off={hand_off['to']}")

    return {
        "response": final_text,
        "context_log": context_log,
        "hand_off_to": hand_off["to"],
    }
