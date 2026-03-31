"""Beryllium - Task and Metrics Agent.

Handles task management and metric logging as a unified agent.
Every recurring task can have a metric attached — completing a task
and logging its value happen as one action.
Uses MODEL_BIG for nutrition estimation and reasoning quality.
"""

import json as _json
from datetime import datetime, timezone
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from agents.tools.task_tools import make_task_tools, fetch_tasks, format_tasks_for_prompt
from agents.tools.life_goal_tools import format_goals_for_prompt
from agents.tools.state_tools import format_states_for_prompt
from agents.tools.journal_tools import format_journal_for_prompt
from agents import get_api_key
from file_logger import logger
import config

SYSTEM_PROMPT_TEMPLATE = """You are Beryllium, the Task agent. You are part of a team of agents named after the elements.

Current date/time: {now}

## Purpose
Manage the user's tasks. You handle one-time tasks (things with a deadline or fixed scope) and recurring habit tasks (daily or weekly habits the user is building).

{goals_section}

{states_section}

{journal_section}
{task_plan_section}
{tasks_section}

## Tools
- get_tasks: **Do NOT call this.** Its output is already in the '## Current Tasks' section above. Only call it after you've added/updated/deleted a task and need the updated list.
- get_habit_progress: Get all recurring tasks with 7-day streak counts. Call this before adding a new recurring task to check the one-per-goal rule.
- add_one_time_task / update_one_time_task / delete_one_time_task / complete_one_time_task
- add_recurring_task / update_recurring_task / delete_recurring_task
- complete_recurring_task: Log that a habit was done today. Returns streak and graduation status.
- finish_conversation: Hand off when done

## Habit model
- Recurring tasks are building habits — one active habit task per life goal maximum.
- When the user completes a habit 6 out of the last 7 days, it graduates to "established habit" status automatically. Established habits are part of who they are — they no longer need active tracking.
- **One per goal rule**: before adding a new recurring task, call get_habit_progress to check. If a goal already has an active (not graduated) habit task, do NOT add another one. Tell the user they need to graduate their current habit first, or ask if they want to replace it.

## Task capture (no incoming plan)
1. For each task the user describes: title, description, type (one-time or recurring), estimated minutes, cognitive load (1-10), deadline (one-time) or interval in days (recurring), linked life goals.
2. Cognitive load: 1 = barely think about it, 10 = constantly on their mind.
3. Save immediately with whatever info you have. Don't wait for all fields.
4. When done, call finish_conversation with next_agent="hydrogen".

## Incoming plan from Boron (weekly review overhaul)
If a plan is shown above, it may include additions, deletions, and modifications. Skip the interview:
1. Present the full plan in plain language — what will be deleted, what will change, what will be added.
2. Ask: "Ready for me to make all of these changes?"
3. On confirmation, execute everything: delete with delete_one_time_task / delete_recurring_task, update with update_one_time_task / update_recurring_task, add with the appropriate add tool.
4. Summarize what was done and ask if anything needs adjusting.
5. Call finish_conversation with next_agent="hydrogen".

## Completing habits
When the user reports doing a habit, find the task and call complete_recurring_task. Respond with the streak: "Done — {{streak}}/7 this week." If it graduated, say so: "This one's a habit now."

## Rules
- Do NOT offer coaching, advice, or commentary beyond task management.
- Do NOT re-introduce yourself if you already have in this conversation.
- Do NOT call finish_conversation until the user confirms.
- Enforce the one-active-habit-per-goal rule strictly.
- finish_conversation always routes back to hydrogen."""


def run_beryllium(user_id: int, messages: list, context_cache: dict = None, on_event=None) -> dict:
    """Run beryllium agent. Returns {response, context_log, hand_off_to}."""
    logger.info(f"[user={user_id}] Beryllium processing")
    context_log = []
    if context_cache is None:
        context_cache = {}

    api_key = get_api_key(user_id)
    hand_off = {"to": None}

    base_tools = make_task_tools(user_id, context_cache)

    @tool
    def finish_conversation(next_agent: str = "hydrogen", summary: str = "") -> str:
        """Finish this conversation and hand off. next_agent should be 'hydrogen' for the manager, 'helium' for goals, or 'lithium' for state."""
        valid = {"hydrogen", "helium", "lithium"}
        if next_agent not in valid:
            next_agent = "hydrogen"
        context_cache.pop("task_plan", None)
        hand_off["to"] = next_agent
        return f"Handing off to {next_agent}."

    tools = base_tools + [finish_conversation]
    from runtime_config import get_agent_model
    llm = ChatOpenAI(model=get_agent_model("beryllium"), api_key=api_key)
    llm_with_tools = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    goals_section = format_goals_for_prompt(context_cache.get("life_goals", []))
    states_section = format_states_for_prompt(context_cache.get("recent_states", []))
    journal_section = format_journal_for_prompt(context_cache.get("recent_journal_entries", []))
    if "tasks" not in context_cache:
        context_cache["tasks"] = fetch_tasks(user_id)
    tasks_section = format_tasks_for_prompt(context_cache["tasks"])

    task_plan = context_cache.get("task_plan")
    if task_plan:
        plan_text = _json.dumps(task_plan, indent=2)
        task_plan_section = f"\n## Incoming Plan from Boron\nThe following tasks were planned with the user — save them all on confirmation:\n```json\n{plan_text}\n```\n"
    else:
        task_plan_section = ""

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        now=now_str,
        goals_section=goals_section,
        states_section=states_section,
        journal_section=journal_section,
        tasks_section=tasks_section,
        task_plan_section=task_plan_section,
    )

    call_messages = [SystemMessage(content=system_prompt)] + messages
    num_input_messages = len(call_messages)

    context_log.append({"type": "system", "content": system_prompt, "agent": "beryllium"})

    for i in range(20):
        logger.debug(f"[user={user_id}] Beryllium ReAct iteration {i}")
        if on_event:
            full_response = None
            for chunk in llm_with_tools.stream(call_messages):
                if full_response is None:
                    full_response = chunk
                else:
                    full_response = full_response + chunk
                if chunk.content:
                    on_event("token", {"content": chunk.content, "agent": "beryllium"})
            response = full_response
        else:
            response = llm_with_tools.invoke(call_messages)
        call_messages.append(response)

        if not response.tool_calls:
            context_log.append({"type": "ai", "content": response.content, "agent": "beryllium"})
            break

        for tc in response.tool_calls:
            tool_fn = tool_map.get(tc["name"])
            if tool_fn:
                logger.info(f"[user={user_id}] Beryllium calling tool: {tc['name']}({tc['args']})")
                if on_event:
                    on_event("tool_start", {"tool": tc["name"], "agent": "beryllium"})
                result = tool_fn.invoke(tc["args"])
                if on_event:
                    on_event("tool_end", {"tool": tc["name"], "agent": "beryllium"})
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
        if isinstance(msg, AIMessage) and msg.content:
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
