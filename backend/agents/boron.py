"""Boron - Task Planning & Info Gathering Agent.

Conducts deep, exploratory conversations to fully understand what a task
entails before handing a structured plan off to Beryllium to create.
Uses MODEL_BIG for quality of reasoning.
"""

import json
from datetime import datetime, timezone
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from agents.tools.task_tools import make_task_tools
from agents.tools.life_goal_tools import format_goals_for_prompt
from agents.tools.state_tools import format_states_for_prompt
from agents import get_api_key
from file_logger import logger
import config

SYSTEM_PROMPT_TEMPLATE = """You are Boron, the Task Planning agent. You are part of a team of agents named after the elements.

Current date/time: {now}

## Purpose
Your job is to thoroughly understand what the user needs to do — not to add tasks yourself, but to gather enough detail that the tasks you hand off to Beryllium are specific, accurate, and immediately actionable. You think deeply about what a task really involves.

{goals_section}

{states_section}

## Existing Tasks
{tasks_section}

## Tools
- finish_planning: When the user confirms they've said everything relevant, call this with the structured plan.

## How to conduct the conversation
You are doing two things at once: helping the user think through what they need to do, and extracting the information needed to create well-defined tasks.

For each thing the user wants to accomplish, probe deeply:
- **What exactly does "done" look like?** Push past vague outcomes.
- **What are the concrete steps or sub-tasks?** Break big items down.
- **What's the realistic time estimate?** Ask about past experience, not optimistic guesses.
- **What's actually blocking it?** Resources, decisions, dependencies on others?
- **Is it one-time or something that needs to recur?** If recurring, how often?
- **What's the real deadline?** "Soon" and "when I can" are not deadlines — push for dates.
- **Which life goal does this serve?** Reference the goals listed above by ID.
- **What's the cognitive weight?** How much does not doing this thing weigh on them day-to-day? (1-10)
- **What details would someone else need to do this for them?** Assume zero context.

Do NOT rush. Ask follow-up questions. If an answer is vague, probe further. If the user names five things at once, address each one. You may take as many turns as needed.

## When the user is done
When the user says they've covered everything, synthesize the full plan and read it back in plain language: each task with its title, description, type (one-time/recurring), time estimate, deadline or interval, cognitive load, and which goal it serves. Ask: "Does this capture everything accurately? Anything to adjust?"

Only once the user confirms call finish_planning with a JSON array of task objects. Each object must have:
- title (str)
- description (str) — rich detail, enough context for someone with no prior knowledge
- task_type ("one_time" or "recurring")
- estimated_minutes (int)
- cognitive_load (int, 1-10)
- life_goal_ids (array of goal ID ints, empty array if none)
- deadline (ISO date string "YYYY-MM-DD", only for one_time tasks, omit if none)
- interval_days (int, only for recurring tasks)

## Rules
- Do NOT add tasks. That is Beryllium's job.
- Do NOT offer unsolicited advice or commentary on the tasks themselves. Your role is to understand and document, not to coach.
- Do NOT call finish_planning until the user has explicitly confirmed the plan is complete and accurate.
- Reference goal IDs from the Life Goals section above when asking which goal a task serves.
- Be warm but persistent. Vague answers get follow-up questions."""


def run_boron(user_id: int, messages: list, context_cache: dict = None, on_event=None) -> dict:
    """Run boron agent. Returns {response, context_log, hand_off_to}."""
    logger.info(f"[user={user_id}] Boron processing")
    context_log = []
    if context_cache is None:
        context_cache = {}

    api_key = get_api_key(user_id)
    hand_off = {"to": None}
    plan_holder = {"plan": None}

    task_tools = make_task_tools(user_id, context_cache)
    get_tasks_tool = next(t for t in task_tools if t.name == "get_tasks")

    @tool
    def finish_planning(plan: str) -> str:
        """Call this when the user has confirmed the task plan is complete and accurate.
        plan must be a JSON array of task objects. Hands off to Beryllium to create the tasks."""
        try:
            parsed = json.loads(plan) if isinstance(plan, str) else plan
        except json.JSONDecodeError:
            return "Invalid JSON in plan. Please provide a valid JSON array."
        context_cache["task_plan"] = parsed
        hand_off["to"] = "beryllium"
        return "Plan saved. Handing off to Beryllium."

    tools = [get_tasks_tool, finish_planning]
    llm = ChatOpenAI(model=config.MODEL_BIG, api_key=api_key)
    llm_with_tools = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    goals_section = format_goals_for_prompt(context_cache.get("life_goals", []))
    states_section = format_states_for_prompt(context_cache.get("recent_states", []))

    # Build tasks section from cache or a quick fetch
    cached_tasks = context_cache.get("get_tasks")
    if cached_tasks:
        tasks_section = f"(cached)\n{str(cached_tasks.get('result', ''))[:1000]}"
    else:
        tasks_section = "Call get_tasks to load existing tasks."

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        now=now_str,
        goals_section=goals_section,
        states_section=states_section,
        tasks_section=tasks_section,
    )

    call_messages = [SystemMessage(content=system_prompt)] + messages
    num_input_messages = len(call_messages)

    context_log.append({"type": "system", "content": system_prompt, "agent": "boron"})

    for i in range(20):
        logger.debug(f"[user={user_id}] Boron ReAct iteration {i}")
        if on_event:
            full_response = None
            for chunk in llm_with_tools.stream(call_messages):
                if full_response is None:
                    full_response = chunk
                else:
                    full_response = full_response + chunk
                if chunk.content:
                    on_event("token", {"content": chunk.content, "agent": "boron"})
            response = full_response
        else:
            response = llm_with_tools.invoke(call_messages)
        call_messages.append(response)

        if not response.tool_calls:
            context_log.append({"type": "ai", "content": response.content, "agent": "boron"})
            break

        for tc in response.tool_calls:
            tool_fn = tool_map.get(tc["name"])
            if tool_fn:
                logger.info(f"[user={user_id}] Boron calling tool: {tc['name']}({tc['args']})")
                if on_event:
                    on_event("tool_start", {"tool": tc["name"], "agent": "boron"})
                result = tool_fn.invoke(tc["args"])
                if on_event:
                    on_event("tool_end", {"tool": tc["name"], "agent": "boron"})
                tool_msg = ToolMessage(content=str(result), tool_call_id=tc["id"])
                call_messages.append(tool_msg)
                context_log.append({
                    "type": "tool_call",
                    "name": tc["name"],
                    "args": tc["args"],
                    "result": str(result),
                    "agent": "boron",
                })

        if hand_off["to"]:
            break

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

    logger.info(f"[user={user_id}] Boron done. hand_off={hand_off['to']}")

    return {
        "response": final_text,
        "context_log": context_log,
        "hand_off_to": hand_off["to"],
    }
