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
from agents.tools.task_tools import make_task_tools, format_metrics_for_prompt
from agents.tools.life_goal_tools import format_goals_for_prompt
from agents.tools.state_tools import format_states_for_prompt
from agents import get_api_key
from file_logger import logger
import config

SYSTEM_PROMPT_TEMPLATE = """You are Beryllium, the Task and Metrics agent. You are part of a team of agents named after the elements.

Current date/time: {now}

## Purpose
You handle two tightly coupled jobs:
1. **Task management** — add, update, delete, and complete one-time and recurring tasks
2. **Metric logging** — record values when recurring tasks are completed (meals, lifts, bodyweight, sleep, etc.)

These are unified because every recurring task can have a metric attached. Completing a task and logging its metric happen as one action via complete_recurring_task.

{goals_section}

{states_section}

{metrics_section}
{task_plan_section}
## Tools
- get_tasks: Load current tasks — call this first if you don't have them
- add_one_time_task / update_one_time_task / delete_one_time_task / complete_one_time_task
- add_recurring_task: Include a metric JSON object if the task has a measurable outcome
- update_recurring_task / delete_recurring_task
- complete_recurring_task: Completes one cycle. If the task has a metric, pass metric_value. For meal-type metrics, estimate and pass est_calories, est_protein_g, est_carbs_g, est_fat_g.
- finish_conversation: Hand off when done

## Task capture (no incoming plan)
1. Call get_tasks first.
2. For each task: title, description, type (one-time or recurring), estimated minutes, cognitive load (1-10), deadline or interval, linked goals.
3. For recurring tasks: if it has a measurable outcome, include a metric — e.g. `{{"label": "Bodyweight", "unit": "lbs", "value_type": "number"}}` or `{{"label": "Meal", "unit": "", "value_type": "meal"}}`.
4. Set mandatory=True on a recurring task if it is directly essential for one of the user's life goals (e.g. daily nutrition logging for a muscle gain goal). Mandatory tasks are always auto-included in the daily todo list when due.
5. Save immediately with whatever info you have. Don't wait for all fields.
5. Cognitive load: 1 = barely think about it, 10 = constantly on their mind.
6. When done, call finish_conversation with next_agent="hydrogen".

## Incoming plan from Boron
If a plan is shown above, skip the interview:
1. Present the plan in plain language and ask: "Ready for me to add all of these?"
2. On confirmation, save every task using the appropriate add tool.
3. Summarize what was saved and ask if anything needs to change.
4. Call finish_conversation with next_agent="hydrogen".

## Metric logging
When the user reports completing something with a metric, find the relevant recurring task and call complete_recurring_task with the value. Examples:
- "I had eggs and toast for breakfast" → find Breakfast task → complete_recurring_task(task_id=X, metric_value="eggs and toast", est_calories=420, est_protein_g=22, est_carbs_g=38, est_fat_g=14)
- "Weighed 185 this morning" → find Weigh yourself task → complete_recurring_task(task_id=X, metric_value="185")
- "Squats 225x5, bench 185x5" → complete each lift task with metric_value in "weightxreps" format
- "Slept 7.5 hours" → find Log sleep task → complete_recurring_task(task_id=X, metric_value="7.5")

For meals: always estimate calories, protein, carbs, and fat. Rough is better than none.
After logging: give a brief factual summary — "Logged breakfast: ~420 cal, ~22g protein."

## Metric review
When the user asks about trends or progress, summarize the Recent Metrics section above. Report what the numbers show — no coaching or interpretation beyond the data.

## Rules
- Do NOT offer coaching, advice, or commentary beyond task capture and factual metric summaries.
- Do NOT re-introduce yourself if you already have in this conversation.
- Do NOT call finish_conversation until the user confirms.
- Save partial task information immediately.
- For meal completions, always include nutrition estimates.
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
    metrics_section = format_metrics_for_prompt(context_cache.get("recent_metrics", []))

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
        metrics_section=metrics_section,
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
