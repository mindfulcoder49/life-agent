"""Lithium - User State Specialist Agent.

Collects the three subjective wellbeing fields: energy, soreness, sickness.
Meals, sleep, and exercise are tracked as metrics by Carbon.
Uses MODEL_SMALL for cost efficiency.
"""

from datetime import datetime, timezone
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from agents.tools.state_tools import make_state_tools, format_states_for_prompt
from agents.tools.task_tools import format_metrics_for_prompt
from agents import get_api_key
from file_logger import logger
import config

SYSTEM_PROMPT_TEMPLATE = """You are Lithium, the User State agent. You are part of a team of agents named after the elements.

Current date/time: {now}

## Purpose
Check in on the user's current subjective physical state. You collect exactly three fields: energy (1-10), soreness (1-10), and sickness (1-10). Meals, sleep hours, and exercise are tracked separately as metrics via task completion — do not ask about those here.

{session_state_section}

{states_section}

{metrics_section}

## User Has Tasks
{has_tasks_note}

## Tools
- add_user_state: Create a NEW state check-in (use only for genuinely new sessions)
- update_user_state: Update an EXISTING state by ID — use this to correct a state you already created this session
- finish_conversation: Hand off when user confirms they're done

## Flow
1. Review the recent states shown above.
2. If this is the user's first state check, briefly introduce yourself: "Hi, I'm Lithium. Quick check-in — how are you feeling right now?"
3. Ask all three questions at once in a single message: energy (1-10), soreness (1-10), and sickness (1-10). Include notes if there's anything else relevant.
4. Save with add_user_state once the user responds. If you need to correct something, use update_user_state with the returned state ID — do NOT create duplicate states.
5. Summarize: "Got it — energy {{X}}/10, soreness {{Y}}/10, sickness {{Z}}/10. Anything to change?"
6. When the user confirms (or says no changes), immediately call finish_conversation — do NOT ask additional questions:
   - next_agent="beryllium" if the user has NO tasks yet (see "User Has Tasks" above)
   - next_agent="hydrogen" if the user already has tasks

## Rules
- Ask ONLY about energy, soreness, and sickness. Do not ask about food, sleep, or exercise — those are logged via task completion.
- Do not offer health advice, tips, or any commentary beyond the check-in.
- Do not re-introduce yourself if you already have in this conversation.
- Do not call finish_conversation until the user confirms.
- Only call add_user_state ONCE per check-in. After the first save, always use update_user_state.
- If "State Saved This Session" is shown above, do NOT call add_user_state again. Use update_user_state with the shown ID if corrections are needed.
- Call finish_conversation immediately when the user says they're done — do not ask "Anything else?" or similar.
- Be warm but fast. This is a 2-message exchange."""


def run_lithium(user_id: int, messages: list, context_cache: dict = None, on_event=None) -> dict:
    """Run lithium agent. Returns {response, context_log, hand_off_to}."""
    logger.info(f"[user={user_id}] Lithium processing")
    context_log = []
    if context_cache is None:
        context_cache = {}

    api_key = get_api_key(user_id)
    hand_off = {"to": None}

    base_tools = make_state_tools(user_id, context_cache)

    @tool
    def finish_conversation(next_agent: str = "hydrogen", summary: str = "") -> str:
        """Finish this conversation and hand off. next_agent should be 'beryllium' if user has no tasks yet, 'hydrogen' if they have tasks."""
        valid = {"hydrogen", "beryllium"}
        if next_agent not in valid:
            next_agent = "hydrogen"
        hand_off["to"] = next_agent
        return f"Handing off to {next_agent}."

    tools = base_tools + [finish_conversation]
    from runtime_config import get_agent_model
    llm = ChatOpenAI(model=get_agent_model("lithium"), api_key=api_key)
    llm_with_tools = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    states_section = format_states_for_prompt(context_cache.get("recent_states", []))
    metrics_section = format_metrics_for_prompt(context_cache.get("recent_metrics", []))

    # Session state tracking: did we already save a state this session?
    session_state_id = context_cache.get("session_state_id")
    if session_state_id:
        session_state_section = (
            f"## State Saved This Session\n"
            f"State already saved this session: id={session_state_id}. "
            f"Do NOT call add_user_state again. Use update_user_state with this ID if corrections are needed."
        )
    else:
        session_state_section = ""

    # Does the user have any tasks?
    if "has_tasks" not in context_cache:
        from database import count_rows
        has_ot = count_rows("one_time_tasks", filters={"user_id": user_id, "completed": False})
        has_rec = count_rows("recurring_tasks", filters={"user_id": user_id, "active": True})
        context_cache["has_tasks"] = has_ot > 0 or has_rec > 0
    has_tasks = context_cache["has_tasks"]
    has_tasks_note = (
        "Yes — user has existing tasks. Route to hydrogen when done."
        if has_tasks else
        "No — user has no tasks yet. Route to beryllium when done so they can set up their tasks."
    )

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        now=now_str,
        session_state_section=session_state_section,
        states_section=states_section,
        metrics_section=metrics_section,
        has_tasks_note=has_tasks_note,
    )

    call_messages = [SystemMessage(content=system_prompt)] + messages
    num_input_messages = len(call_messages)

    context_log.append({"type": "system", "content": system_prompt, "agent": "lithium"})

    for i in range(10):
        logger.debug(f"[user={user_id}] Lithium ReAct iteration {i}")
        if on_event:
            full_response = None
            for chunk in llm_with_tools.stream(call_messages):
                if full_response is None:
                    full_response = chunk
                else:
                    full_response = full_response + chunk
                if chunk.content:
                    on_event("token", {"content": chunk.content, "agent": "lithium"})
            response = full_response
        else:
            response = llm_with_tools.invoke(call_messages)
        call_messages.append(response)

        if not response.tool_calls:
            context_log.append({"type": "ai", "content": response.content, "agent": "lithium"})
            break

        for tc in response.tool_calls:
            tool_fn = tool_map.get(tc["name"])
            if tool_fn:
                logger.info(f"[user={user_id}] Lithium calling tool: {tc['name']}({tc['args']})")
                if on_event:
                    on_event("tool_start", {"tool": tc["name"], "agent": "lithium"})
                result = tool_fn.invoke(tc["args"])
                if on_event:
                    on_event("tool_end", {"tool": tc["name"], "agent": "lithium"})
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
        if isinstance(msg, AIMessage) and msg.content:
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
