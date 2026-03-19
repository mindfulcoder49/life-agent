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
from agents import get_api_key
from file_logger import logger
import config

SYSTEM_PROMPT_TEMPLATE = """You are Boron, the Weekly Review agent. You are part of a team of agents named after the elements.

Current date/time: {now}

## Purpose
Conduct a structured weekly review. You read the past 7 days of data, present a factual summary, have a brief focused discussion with the user, and save the review.

{goals_section}

{states_section}

{metrics_section}

{last_review_section}

## Tools
- get_week_completions: Fetch all task completions from the past 7 days — call this first
- save_weekly_review: Save the completed review record
- finish_conversation: Hand off to hydrogen when done

## Flow
1. Call get_week_completions immediately.
2. Present a factual summary — what got done, what recurring tasks were missed, metric trends from the data above. Be specific and data-driven.
3. Ask: "What were your wins this week? What got in the way? Anything that surprised you?"
4. Ask: "What's one thing you'd do differently next week?"
5. Once you have enough to write a meaningful review, synthesize it and call save_weekly_review with:
   - week_start / week_end: the Monday–Sunday date range of the week being reviewed
   - summary: 2–4 sentence narrative of the week
   - wins: JSON array of concrete wins
   - misses: JSON array of things that didn't happen or fell short
   - adjustments: JSON array of specific changes to make next week
6. Confirm what was saved, then call finish_conversation.

## Rules
- Present facts first. Don't editorialize or offer opinions until asked.
- Keep it focused — this should be 4–8 exchanges, not an open-ended debrief.
- Do NOT offer coaching or unsolicited advice beyond what the data directly suggests.
- Do NOT call save_weekly_review until you have enough information from the user.
- Do NOT call finish_conversation until the review is saved.
- finish_conversation always routes back to hydrogen."""


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
    def finish_conversation(next_agent: str = "hydrogen", summary: str = "") -> str:
        """Finish the weekly review and hand off to hydrogen."""
        hand_off["to"] = "hydrogen"
        return "Handing off to hydrogen."

    tools = review_tools + [finish_conversation]
    llm = ChatOpenAI(model=config.MODEL_BIG, api_key=api_key)
    llm_with_tools = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    goals_section = format_goals_for_prompt(context_cache.get("life_goals", []))
    states_section = format_states_for_prompt(context_cache.get("recent_states", []))
    metrics_section = format_metrics_for_prompt(context_cache.get("recent_metrics", []))

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
