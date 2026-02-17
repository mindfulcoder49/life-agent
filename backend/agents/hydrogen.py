"""Hydrogen - Manager/Router Agent.

Checks user's data state and either handles the message directly or
routes to a specialist agent. Uses MODEL_BIG for synthesis/recommendations.
"""

from datetime import datetime, timezone
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from agents.tools.life_goal_tools import make_life_goal_tools
from agents.tools.state_tools import make_state_tools
from agents.tools.task_tools import make_task_tools
from agents.tools.todo_tools import make_todo_tools
from agents.tools.help_tools import make_help_tools
from agents import get_api_key
from file_logger import logger
import config

SYSTEM_PROMPT_TEMPLATE = """You are Hydrogen, the manager agent for Life Agent. You are a routing and synthesis agent. Your job is to check the user's data, route to the right specialist, or provide daily recommendations. You do NOT conduct interviews yourself — that's what the specialists do.

Current date/time: {now}

## Your Team (named after elements)
- **Helium**: Life Goals specialist
- **Lithium**: User State specialist (physical/mental check-in)
- **Beryllium**: Task Management specialist

## Routing Logic — FOLLOW THIS ORDER STRICTLY
Use your tools to check the user's data, then route:
1. NO life goals exist -> route to helium. This is ALWAYS the first priority.
2. Life goals exist but NO state check in the past 4 hours -> route to lithium
3. Life goals + recent state but NO tasks -> route to beryllium
4. Life goals + recent state + tasks -> offer a daily recommendation, or ask what they'd like to do
5. If the user explicitly asks to update goals/state/tasks -> route to that agent immediately
6. If the user says yes to a recommendation -> read all data (goals, last 10 states, last 2 days completed tasks, overdue recurring tasks, all incomplete one-time tasks) and synthesize a prioritized daily plan, then save it as a todo list

## When Making Recommendations
Read everything: goals, recent states, completed tasks, overdue recurring tasks, incomplete tasks. Consider the user's energy level, soreness, sickness, cognitive load of tasks, deadlines, and goal priorities. Create a concrete ordered list of what to do today and why.

## Context Cache
{context_hint}

## Important
- Route quickly. Do not chat or ask unnecessary questions. Check data, decide, route.
- Do NOT offer health advice, life coaching, or anything outside the system's purpose.
- Do NOT re-introduce yourself or the team after the first interaction.
- When routing, your response can be brief or empty — the specialist will greet the user.
- If you already have recent data from the context cache, do NOT call those tools again — use the cached info to make your routing decision."""


def run_hydrogen(user_id: int, messages: list, context_cache: dict = None, on_event=None) -> dict:
    """Run hydrogen agent. Returns {response, context_log, hand_off_to}."""
    logger.info(f"[user={user_id}] Hydrogen processing")
    context_log = []
    if context_cache is None:
        context_cache = {}

    api_key = get_api_key(user_id)

    # Build tools
    route_target_holder = {"target": None}

    @tool
    def route_to_agent(agent_name: str) -> str:
        """Route the user to a specialist agent. agent_name must be: helium, lithium, or beryllium."""
        valid = {"helium", "lithium", "beryllium"}
        if agent_name not in valid:
            return f"Invalid agent '{agent_name}'. Must be one of: {', '.join(valid)}"
        route_target_holder["target"] = agent_name
        return f"Routing to {agent_name}."

    life_goal_tools = make_life_goal_tools(user_id)
    state_tools = make_state_tools(user_id)
    task_tools = make_task_tools(user_id)
    todo_tools = make_todo_tools(user_id)
    help_tools = make_help_tools()

    # Hydrogen gets read tools + route + todo creation
    tools = [route_to_agent]
    for t in life_goal_tools:
        if t.name == "get_life_goals":
            tools.append(t)
    for t in state_tools:
        if t.name == "get_recent_states":
            tools.append(t)
    for t in task_tools:
        if t.name == "get_tasks":
            tools.append(t)
    for t in todo_tools:
        tools.append(t)
    for t in help_tools:
        tools.append(t)

    llm = ChatOpenAI(model=config.MODEL_BIG, api_key=api_key)
    llm_with_tools = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}

    # Build context cache hint
    cache_hints = []
    for key, cached in context_cache.items():
        cache_hints.append(f"- {key}: {str(cached['result'])[:300]}")
    context_hint = "\n".join(cache_hints) if cache_hints else "No cached data yet."

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(now=now_str, context_hint=context_hint)

    call_messages = [SystemMessage(content=system_prompt)] + messages
    num_input_messages = len(call_messages)

    context_log.append({"type": "system", "content": system_prompt, "agent": "hydrogen"})
    for m in messages:
        context_log.append({"type": m.type, "content": m.content, "agent": "hydrogen"})

    # ReAct loop
    for i in range(10):
        logger.debug(f"[user={user_id}] Hydrogen ReAct iteration {i}")
        if on_event:
            full_response = None
            for chunk in llm_with_tools.stream(call_messages):
                if full_response is None:
                    full_response = chunk
                else:
                    full_response = full_response + chunk
                if chunk.content:
                    on_event("token", {"content": chunk.content, "agent": "hydrogen"})
            response = full_response
        else:
            response = llm_with_tools.invoke(call_messages)
        call_messages.append(response)

        if not response.tool_calls:
            logger.info(f"[user={user_id}] Hydrogen final response (no tool calls)")
            context_log.append({"type": "ai", "content": response.content, "agent": "hydrogen"})
            break

        # Process tool calls
        for tc in response.tool_calls:
            tool_fn = tool_map.get(tc["name"])
            if tool_fn:
                logger.info(f"[user={user_id}] Hydrogen calling tool: {tc['name']}({tc['args']})")
                if on_event:
                    on_event("tool_start", {"tool": tc["name"], "agent": "hydrogen"})
                result = tool_fn.invoke(tc["args"])
                if on_event:
                    on_event("tool_end", {"tool": tc["name"], "agent": "hydrogen"})
                result_str = str(result)
                # Cache read-only tool results
                if tc["name"] in ("get_life_goals", "get_recent_states", "get_tasks"):
                    context_cache[tc["name"]] = {"result": result_str, "timestamp": now_str}
                tool_msg = ToolMessage(content=result_str, tool_call_id=tc["id"])
                call_messages.append(tool_msg)
                context_log.append({
                    "type": "tool_call",
                    "name": tc["name"],
                    "args": tc["args"],
                    "result": result_str,
                    "agent": "hydrogen",
                })

            # If we just routed, stop the loop
            if route_target_holder["target"]:
                logger.info(f"[user={user_id}] Hydrogen routing to {route_target_holder['target']}")
                break

        if route_target_holder["target"]:
            break

    # Extract final response text - only from messages generated THIS turn
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

    return {
        "response": final_text,
        "context_log": context_log,
        "hand_off_to": route_target_holder["target"],
    }
