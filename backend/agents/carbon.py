"""Carbon - Evening Journaling Agent.

Guides the user through a brief evening reflection, capturing what worked
and what was discouraging. Named after element Carbon (C).
"""

from datetime import datetime, timezone
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from agents.tools.journal_tools import make_journal_tools, format_journal_for_prompt
from agents.tools.life_goal_tools import format_goals_for_prompt
from agents.tools.state_tools import format_states_for_prompt
from agents import get_api_key
from file_logger import logger

SYSTEM_PROMPT_TEMPLATE = """You are Carbon, the Evening Reflection agent. You are part of a team of agents named after the elements.

Current date/time: {now}

## Purpose
Guide the user through a brief evening reflection. Your goal is to capture what worked today and what was discouraging — two or three sentences each is plenty. This information helps the whole team understand what motivates and challenges this person.

{goals_section}

{states_section}

{journal_section}

## Tools
- save_journal_entry: Save the reflection once you have enough to work with
- finish_conversation: Hand off when done

## Flow
1. Open with something warm and specific if there's goal context: "Hey, how did today go?" or reference a specific goal if relevant to recent state. Keep it to one sentence.
2. Listen to what they share. If they mention both what worked AND what was hard, you have enough — save it and confirm.
3. If they only share one side, ask a brief follow-up for the other: "What felt hard or discouraging today?" or "Was there anything that clicked well?"
4. Once you have both sides (even roughly), call save_journal_entry — don't wait for perfection.
5. Confirm briefly: "Saved. Rest up." or similar. Then call finish_conversation.

## Rules
- Keep it conversational. This is NOT a form — don't ask "on a scale of 1-10" or list fields.
- Do NOT offer advice, coaching, or commentary. Listen and save.
- Do NOT call finish_conversation until the entry is saved.
- Two exchanges max — open, collect, save. Don't over-interview.
- Be warm but brief. Evening tone — winding down, not ramping up.
- If the user just says "good" or "fine", ask one gentle follow-up then save whatever you have.
- finish_conversation always routes to hydrogen."""


def run_carbon(user_id: int, messages: list, context_cache: dict = None, on_event=None) -> dict:
    """Run carbon agent. Returns {response, context_log, hand_off_to}."""
    logger.info(f"[user={user_id}] Carbon processing")
    context_log = []
    if context_cache is None:
        context_cache = {}

    api_key = get_api_key(user_id)
    hand_off = {"to": None}

    base_tools = make_journal_tools(user_id, context_cache)

    @tool
    def finish_conversation(next_agent: str = "hydrogen") -> str:
        """Finish this conversation and hand off to hydrogen."""
        valid = {"hydrogen"}
        if next_agent not in valid:
            next_agent = "hydrogen"
        hand_off["to"] = next_agent
        return f"Handing off to {next_agent}."

    tools = base_tools + [finish_conversation]
    from runtime_config import get_agent_model
    llm = ChatOpenAI(model=get_agent_model("carbon"), api_key=api_key)
    llm_with_tools = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    goals_section = format_goals_for_prompt(context_cache.get("life_goals", []))
    states_section = format_states_for_prompt(context_cache.get("recent_states", []))
    journal_section = format_journal_for_prompt(context_cache.get("recent_journal_entries", []))

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        now=now_str,
        goals_section=goals_section,
        states_section=states_section,
        journal_section=journal_section,
    )

    call_messages = [SystemMessage(content=system_prompt)] + messages
    num_input_messages = len(call_messages)

    context_log.append({"type": "system", "content": system_prompt, "agent": "carbon"})

    for i in range(10):
        logger.debug(f"[user={user_id}] Carbon ReAct iteration {i}")
        if on_event:
            full_response = None
            for chunk in llm_with_tools.stream(call_messages):
                if full_response is None:
                    full_response = chunk
                else:
                    full_response = full_response + chunk
                if chunk.content:
                    on_event("token", {"content": chunk.content, "agent": "carbon"})
            response = full_response
        else:
            response = llm_with_tools.invoke(call_messages)
        call_messages.append(response)

        if not response.tool_calls:
            context_log.append({"type": "ai", "content": response.content, "agent": "carbon"})
            break

        for tc in response.tool_calls:
            tool_fn = tool_map.get(tc["name"])
            if tool_fn:
                logger.info(f"[user={user_id}] Carbon calling tool: {tc['name']}({tc['args']})")
                if on_event:
                    on_event("tool_start", {"tool": tc["name"], "agent": "carbon"})
                result = tool_fn.invoke(tc["args"])
                if on_event:
                    on_event("tool_end", {"tool": tc["name"], "agent": "carbon"})
                tool_msg = ToolMessage(content=str(result), tool_call_id=tc["id"])
                call_messages.append(tool_msg)
                context_log.append({
                    "type": "tool_call",
                    "name": tc["name"],
                    "args": tc["args"],
                    "result": str(result),
                    "agent": "carbon",
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

    logger.info(f"[user={user_id}] Carbon done. hand_off={hand_off['to']}")

    return {
        "response": final_text,
        "context_log": context_log,
        "hand_off_to": hand_off["to"],
    }
