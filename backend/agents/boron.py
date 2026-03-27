"""Boron - Weekly Review Agent.

Conducts a structured weekly review: reads the past 7 days of completions,
metrics, and state data, discusses it with the user, and saves a review record.
Uses MODEL_BIG for synthesis quality.
"""

from datetime import datetime, timezone
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from agents.tools.review_tools import make_review_tools
from agents.tools.life_goal_tools import format_goals_for_prompt
from agents.tools.state_tools import format_states_for_prompt
from agents.tools.task_tools import format_metrics_for_prompt
from agents.tools.journal_tools import format_journal_for_prompt
from agents import get_api_key
from file_logger import logger
import config

SYSTEM_PROMPT_TEMPLATE = """You are Boron, the Weekly Review agent. You are part of a team of agents named after the elements.

Current date/time: {now}

## Purpose
Conduct a thorough, honest weekly review. This is not a feel-good summary — it is a real examination of what worked, what didn't, and what the task list should look like going forward. You have full authority to propose task changes and hand off to Beryllium to execute them.

{goals_section}

{states_section}

{metrics_section}

{journal_section}

{last_review_section}

## Tools
- get_week_completions: Fetch all completions from the past 7 days — call immediately
- get_week_incomplete: Fetch all incomplete one-time tasks (with age) and recurring task status — call immediately alongside get_week_completions
- save_weekly_review: Save the review record (do this before any handoff)
- hand_off_to_beryllium: Hand off to Beryllium to execute agreed task changes
- finish_conversation: Return to Hydrogen if no task changes are needed

## Flow

### Phase 1 — Data (before saying anything to the user)
Call BOTH get_week_completions AND get_week_incomplete in your first turn.

### Phase 2 — Honest assessment
Present a direct, specific breakdown:
- **What got done**: completions with any notable streaks or effort
- **What was missed**: recurring tasks that slipped, one-time tasks that didn't happen
- **Task health**: flag any one-time tasks that are 14+ days old and still incomplete — these are stale and probably not happening. Flag any recurring tasks consistently missed.
- **Metric trends**: from the data above (weight, sleep, nutrition, exercise)

Be direct. "You completed 3 of 8 recurring tasks" is more useful than "you made some progress."

### Phase 3 — User input
Ask two questions (can be combined):
1. What actually got in the way this week?
2. Looking at the stale/missed tasks — which ones are you cutting, keeping, or changing?

### Phase 4 — Task overhaul proposal
Based on the data and user's answers, propose concrete changes:
- Tasks to DELETE (stale, abandoned, no longer relevant)
- Tasks to MODIFY (wrong interval, too vague, needs splitting)
- Tasks to ADD (gaps identified from goals or patterns)

Be specific and opinionated. Don't just ask "what do you want to do?" — say "I'd cut these 3, here's why."

### Phase 5 — Save and execute
Once the user agrees on changes:
1. Call save_weekly_review with wins, misses, adjustments, and task_changes (list the agreed changes)
2. If there are task changes to execute: call hand_off_to_beryllium with a clear plain-English description of exactly what to add/remove/modify
3. If no task changes: call finish_conversation

## Rules
- Do NOT skip Phase 1. Always call both data tools before responding.
- Do NOT be vague. Name specific tasks, specific numbers, specific patterns.
- Do NOT save the review until you have the user's input on what's changing.
- Do NOT call finish_conversation until the review is saved.
- Stale one-time tasks (14+ days old, incomplete) should be explicitly flagged — they are cluttering the system.
- Recurring tasks missed 2+ weeks in a row should be flagged for interval adjustment or deactivation.
- If the user says "cut everything stale" or similar, take them at their word and include all stale items in the Beryllium handoff."""


def run_boron(user_id: int, messages: list, context_cache: dict = None, on_event=None) -> dict:
    """Run boron agent. Returns {response, context_log, hand_off_to}."""
    logger.info(f"[user={user_id}] Boron processing")
    context_log = []
    if context_cache is None:
        context_cache = {}

    api_key = get_api_key(user_id)
    hand_off = {"to": None}

    review_tools = make_review_tools(user_id)

    @tool
    def hand_off_to_beryllium(task_plan: str) -> str:
        """Hand off to Beryllium to execute agreed task changes after the review is saved.
        task_plan: plain-English description of exactly what to add, remove, or modify.
        Only call this after save_weekly_review has been called."""
        context_cache["task_plan"] = task_plan
        hand_off["to"] = "beryllium"
        return "Handing off to Beryllium to execute task changes."

    @tool
    def finish_conversation(summary: str = "") -> str:
        """Finish the weekly review and return to Hydrogen. Use when no task changes are needed."""
        hand_off["to"] = "hydrogen"
        return "Handing off to hydrogen."

    tools = review_tools + [hand_off_to_beryllium, finish_conversation]
    from runtime_config import get_agent_model
    llm = ChatOpenAI(model=get_agent_model("boron"), api_key=api_key)
    llm_with_tools = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    goals_section = format_goals_for_prompt(context_cache.get("life_goals", []))
    states_section = format_states_for_prompt(context_cache.get("recent_states", []))
    metrics_section = format_metrics_for_prompt(context_cache.get("recent_metrics", []))
    journal_section = format_journal_for_prompt(context_cache.get("recent_journal_entries", []))

    last_review = context_cache.get("last_weekly_review")
    if last_review:
        created = last_review.get("created_at", "")[:10]
        week_start = last_review.get("week_start", "?")
        week_end = last_review.get("week_end", "?")
        last_review_section = f"## Last Weekly Review\nCompleted: {created} (week of {week_start} to {week_end})"
        if last_review.get("adjustments"):
            adjs = last_review["adjustments"]
            if adjs:
                last_review_section += "\nAdjustments from last week:\n" + "\n".join(f"- {a}" for a in adjs)
    else:
        last_review_section = "## Last Weekly Review\nNo previous weekly reviews."

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        now=now_str,
        goals_section=goals_section,
        states_section=states_section,
        metrics_section=metrics_section,
        journal_section=journal_section,
        last_review_section=last_review_section,
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
