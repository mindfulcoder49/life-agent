"""Hydrogen - Manager/Router Agent.

Checks user's data state and either handles the message directly or
routes to a specialist agent. Uses MODEL_BIG for synthesis/recommendations.
"""

from datetime import datetime, timezone
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from agents.tools.life_goal_tools import make_life_goal_tools, format_goals_for_prompt
from agents.tools.state_tools import format_states_for_prompt
from agents.tools.task_tools import format_metrics_for_prompt
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
- **Lithium**: User State specialist (energy, soreness, sickness check-in)
- **Beryllium**: Task and Metrics specialist (add/edit/delete tasks, log meals/sleep/exercise/lifts, review metric trends)
- **Boron**: Weekly Review specialist (structured review of the past 7 days — completions, metrics, wins, misses, adjustments)

## Routing Logic — FOLLOW THIS ORDER STRICTLY
Use the data already provided above, then route:
1. NO life goals exist -> route to helium. This is ALWAYS the first priority.
2. User explicitly asks to update/add goals -> route to helium
3. User wants to log metrics, track a workout, log meals/sleep/exercise/lifts, or set up metric tracking -> route to beryllium
4. User asks to review their progress, see stats, or analyze trends -> route to beryllium
5. User explicitly asks for a weekly review -> route to boron
6. User explicitly asks to update/add/manage tasks (quick add) -> route to beryllium
7. User explicitly asks about state/check-in -> route to lithium
8. Life goals exist, NO state in past 4 hours, AND no explicit request from the user -> route to lithium
9. Life goals + recent state but NO tasks -> route to beryllium
10. Life goals + recent state + tasks -> offer a daily recommendation. If the last weekly review was 7+ days ago (or never), also mention it: "Also, it's been X days since your last weekly review — want to do that now or after your plan?"
11. If the user says yes to a recommendation -> read all data (goals, last 10 states, last 2 days completed tasks, overdue recurring tasks, all incomplete one-time tasks) and synthesize a prioritized daily plan, then save it as a todo list
12. If the user says yes to a weekly review -> route to boron

IMPORTANT: Explicit user requests (rules 2-7) take priority over automatic routing (rules 8-9). If the user says "add a task" or "manage my tasks", route to beryllium. If the user says "log my workout" or "log what I ate", route to beryllium. If the user says "weekly review" or "review my week", route to boron.

## When Making Recommendations
Read everything: goals, recent states, recent metrics, completed tasks, overdue recurring tasks, incomplete tasks. Consider the user's energy level, soreness, sickness, metric trends, cognitive load of tasks, deadlines, and goal priorities. Create a concrete ordered list of what to do today and why.

When building a todo list, each item sourced from a task MUST include:
- `source_task_id`: the task's database ID (int)
- `source_type`: either `"one_time"` or `"recurring"`
- `completed`: false (default)
Items not sourced from either table should have `source_task_id` as null, `source_type` as null, and `completed` as false.

{goals_section}

{states_section}

{metrics_section}

{last_review_section}

## Context Cache
{context_hint}

## Important
- Route quickly. Do not chat or ask unnecessary questions. Check data, decide, route.
- Do NOT offer health advice, life coaching, or anything outside the system's purpose.
- Do NOT re-introduce yourself or the team after the first interaction.
- When routing, your response can be brief or empty — the specialist will greet the user.
- Life goals, recent states, and recent metrics are already provided above — do NOT call get_life_goals to make routing decisions.
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
        """Route the user to a specialist agent. agent_name must be: helium, lithium, beryllium, or boron."""
        valid = {"helium", "lithium", "beryllium", "boron"}
        if agent_name not in valid:
            return f"Invalid agent '{agent_name}'. Must be one of: {', '.join(valid)}"
        route_target_holder["target"] = agent_name
        return f"Routing to {agent_name}."

    life_goal_tools = make_life_goal_tools(user_id, context_cache)
    task_tools = make_task_tools(user_id, context_cache)
    todo_tools = make_todo_tools(user_id)
    help_tools = make_help_tools()

    # Hydrogen gets route + get_tasks + todo creation + help
    # (goals, states, and metrics are pre-injected into the prompt)
    tools = [route_to_agent]
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

    # Build context cache hint (exclude data shown in dedicated sections)
    cache_hints = []
    excluded = {"recent_states", "life_goals", "recent_metrics", "last_weekly_review"}
    for key, cached in context_cache.items():
        if key in excluded:
            continue
        cache_hints.append(f"- {key}: {str(cached.get('result', cached))[:300]}")
    context_hint = "\n".join(cache_hints) if cache_hints else "No cached data yet."

    goals_section = format_goals_for_prompt(context_cache.get("life_goals", []))
    states_section = format_states_for_prompt(context_cache.get("recent_states", []))
    metrics_section = format_metrics_for_prompt(context_cache.get("recent_metrics", []))

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    last_review = context_cache.get("last_weekly_review")
    if last_review:
        created = last_review.get("created_at", "")[:10]
        week_start = last_review.get("week_start", "?")
        week_end = last_review.get("week_end", "?")
        try:
            from datetime import date
            days_ago = (datetime.now(timezone.utc).date() - datetime.fromisoformat(last_review["created_at"]).date()).days
            days_str = f"{days_ago} days ago"
        except Exception:
            days_str = "unknown"
        last_review_section = f"## Weekly Review\nLast completed: {created} (week of {week_start} to {week_end}) — {days_str}."
    else:
        last_review_section = "## Weekly Review\nNo weekly review completed yet."

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        now=now_str, context_hint=context_hint,
        goals_section=goals_section, states_section=states_section,
        metrics_section=metrics_section, last_review_section=last_review_section,
    )

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
