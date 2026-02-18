"""Agent dispatcher and runner with session support.

Routes each user message to the correct agent based on who is currently
active for that user+session. Supports multiple chat sessions per user.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from langchain_core.messages import HumanMessage, AIMessage
from database import insert_row, get_rows, get_db
from file_logger import logger, log_conversation_turn

from agents.hydrogen import run_hydrogen
from agents.helium import run_helium
from agents.lithium import run_lithium
from agents.beryllium import run_beryllium
from agents.tools.state_tools import fetch_recent_states

AGENT_RUNNERS = {
    "hydrogen": run_hydrogen,
    "helium": run_helium,
    "lithium": run_lithium,
    "beryllium": run_beryllium,
}

SPECIALISTS = {"helium", "lithium", "beryllium"}

AGENT_LABELS = {
    "hydrogen": "Hydrogen (Manager)",
    "helium": "Helium (Life Goals)",
    "lithium": "Lithium (State Check)",
    "beryllium": "Beryllium (Tasks)",
}


def create_graph_runner():
    # In-memory state keyed by (user_id, session_id)
    sessions: dict[tuple[int, str], dict] = {}

    def _get_session(user_id: int, session_id: str) -> dict:
        key = (user_id, session_id)
        if key not in sessions:
            sessions[key] = {
                "messages": [],
                "active_agent": None,
                "context_cache": {},  # {tool_name: {result, timestamp}}
            }
        return sessions[key]

    def reset(user_id: int, session_id: str = None):
        if session_id:
            key = (user_id, session_id)
            if key in sessions:
                del sessions[key]
        else:
            # Reset all sessions for user
            to_delete = [k for k in sessions if k[0] == user_id]
            for k in to_delete:
                del sessions[k]
        logger.info(f"[user={user_id}] Session(s) reset")

    def get_active_agent(user_id: int, session_id: str) -> str | None:
        key = (user_id, session_id)
        if key in sessions:
            return sessions[key].get("active_agent")
        return None

    def list_sessions(user_id: int) -> list[dict]:
        """List chat sessions for a user from the DB (excludes 'default' which is shown separately in UI)."""
        conn = get_db()
        rows = conn.execute("""
            SELECT json_extract(data, '$.session_id') as sid,
                   MIN(created_at) as started,
                   MAX(created_at) as last_msg,
                   COUNT(*) as msg_count
            FROM chat_contexts
            WHERE json_extract(data, '$.user_id') = ?
              AND json_extract(data, '$.session_id') != 'default'
            GROUP BY json_extract(data, '$.session_id')
            ORDER BY MAX(created_at) DESC
        """, (user_id,)).fetchall()
        conn.close()
        result = []
        for r in rows:
            result.append({
                "session_id": r[0],
                "started": r[1],
                "last_message": r[2],
                "message_count": r[3],
            })
        return result

    def _run_core(user_id: int, message: str, session_id: str = "default", on_event=None) -> dict:
        """Core routing logic. Runs synchronously. on_event is optional callback."""
        state = _get_session(user_id, session_id)
        state["messages"].append(HumanMessage(content=message))

        active = state["active_agent"] or "hydrogen"
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # Pre-fetch states into cache if not already present
        if "recent_states" not in state["context_cache"]:
            state["context_cache"]["recent_states"] = fetch_recent_states(user_id)

        logger.info(f"[user={user_id}|{session_id}] >>> Active: {active}")

        log_conversation_turn(user_id, session_id, "user", "input", message)

        try:
            if on_event:
                on_event("agent_start", {"agent": active, "label": AGENT_LABELS[active]})

            agent_fn = AGENT_RUNNERS[active]
            result = agent_fn(user_id, state["messages"], state["context_cache"], on_event)

            response = result["response"]
            context_log = result["context_log"]
            hand_off_to = result.get("hand_off_to")

            logger.info(f"[user={user_id}|{session_id}] {active} -> hand_off={hand_off_to}")
            log_conversation_turn(user_id, session_id, active, "output", response,
                                  [e for e in context_log if e.get("type") == "tool_call"])

            # --- Routing logic ---

            if active == "hydrogen":
                if hand_off_to and hand_off_to in SPECIALISTS:
                    logger.info(f"[user={user_id}|{session_id}] Routing -> {hand_off_to}")
                    if response:
                        state["messages"].append(AIMessage(content=response))

                    if on_event:
                        on_event("agent_start", {"agent": hand_off_to, "label": AGENT_LABELS[hand_off_to]})

                    spec_result = AGENT_RUNNERS[hand_off_to](
                        user_id, state["messages"], state["context_cache"], on_event)
                    response = spec_result["response"]
                    context_log = context_log + spec_result["context_log"]
                    spec_hand_off = spec_result.get("hand_off_to")

                    log_conversation_turn(user_id, session_id, hand_off_to, "output",
                                          spec_result["response"],
                                          [e for e in spec_result["context_log"] if e.get("type") == "tool_call"])

                    if spec_hand_off == "hydrogen":
                        state["active_agent"] = None
                    elif spec_hand_off and spec_hand_off in SPECIALISTS and spec_hand_off != hand_off_to:
                        state["active_agent"] = spec_hand_off
                        response, context_log = _chain_to(
                            user_id, session_id, spec_hand_off, state, response, context_log, on_event)
                    else:
                        state["active_agent"] = hand_off_to
                else:
                    state["active_agent"] = None

            elif active in SPECIALISTS:
                if hand_off_to is None:
                    # Specialist stays active
                    state["active_agent"] = active

                elif hand_off_to == "hydrogen":
                    # Specialist done -> auto-call hydrogen for follow-up
                    state["active_agent"] = None
                    logger.info(f"[user={user_id}|{session_id}] {active} finished -> auto-calling hydrogen")

                    if response:
                        state["messages"].append(AIMessage(content=response))

                    if on_event:
                        on_event("agent_start", {"agent": "hydrogen", "label": AGENT_LABELS["hydrogen"]})

                    h_result = run_hydrogen(user_id, state["messages"], state["context_cache"], on_event)
                    h_response = h_result["response"]
                    h_hand_off = h_result.get("hand_off_to")
                    context_log = context_log + h_result["context_log"]

                    log_conversation_turn(user_id, session_id, "hydrogen", "output",
                                          h_response,
                                          [e for e in h_result["context_log"] if e.get("type") == "tool_call"])

                    if h_hand_off and h_hand_off in SPECIALISTS:
                        # Hydrogen wants to route to next specialist
                        if h_response:
                            response = response + "\n\n" + h_response
                            state["messages"].append(AIMessage(content=h_response))

                        if on_event:
                            on_event("agent_start", {"agent": h_hand_off, "label": AGENT_LABELS[h_hand_off]})

                        next_result = AGENT_RUNNERS[h_hand_off](
                            user_id, state["messages"], state["context_cache"], on_event)
                        response = (response + "\n\n" if response else "") + next_result["response"]
                        context_log = context_log + next_result["context_log"]
                        state["active_agent"] = h_hand_off

                        log_conversation_turn(user_id, session_id, h_hand_off, "output",
                                              next_result["response"])
                    elif h_response:
                        response = response + "\n\n" + h_response
                    # else hydrogen had nothing to add

                elif hand_off_to in SPECIALISTS and hand_off_to != active:
                    state["active_agent"] = hand_off_to
                    response, context_log = _chain_to(
                        user_id, session_id, hand_off_to, state, response, context_log, on_event)
                else:
                    state["active_agent"] = active

            # Add final response to history
            if response:
                state["messages"].append(AIMessage(content=response))

            # Persist to DB
            active_label = AGENT_LABELS.get(state["active_agent"] or "hydrogen", "Hydrogen (Manager)")
            insert_row("chat_contexts", {
                "user_id": user_id,
                "session_id": session_id,
                "role": "user",
                "content": message,
                "context_log": None,
            })
            insert_row("chat_contexts", {
                "user_id": user_id,
                "session_id": session_id,
                "role": "assistant",
                "content": response,
                "context_log": context_log,
                "agent": state["active_agent"] or "hydrogen",
            })

            logger.info(f"[user={user_id}|{session_id}] <<< Done. Active: {state['active_agent']}")

            return {
                "response": response,
                "context_log": context_log,
                "active_agent": state["active_agent"] or "hydrogen",
                "active_agent_label": AGENT_LABELS.get(state["active_agent"] or "hydrogen"),
            }

        except Exception as e:
            logger.error(f"[user={user_id}|{session_id}] Error: {e}", exc_info=True)
            if state["messages"] and isinstance(state["messages"][-1], HumanMessage):
                state["messages"].pop()
            raise

    def _chain_to(user_id, session_id, specialist, state, prev_response, context_log, on_event=None):
        """Call a chained specialist, return updated (response, context_log)."""
        logger.info(f"[user={user_id}|{session_id}] Chaining -> {specialist}")
        if prev_response:
            state["messages"].append(AIMessage(content=prev_response))
        if on_event:
            on_event("agent_start", {"agent": specialist, "label": AGENT_LABELS[specialist]})
        result = AGENT_RUNNERS[specialist](user_id, state["messages"], state["context_cache"], on_event)
        new_response = (prev_response + "\n\n" if prev_response else "") + result["response"]
        new_context = context_log + result["context_log"]
        log_conversation_turn(user_id, session_id, specialist, "output", result["response"])
        h = result.get("hand_off_to")
        if h == "hydrogen":
            state["active_agent"] = None
        elif h is None:
            state["active_agent"] = specialist
        return new_response, new_context

    async def run(user_id: int, message: str, session_id: str = "default") -> dict:
        """Backward-compatible blocking run (no streaming)."""
        return _run_core(user_id, message, session_id)

    async def run_stream(user_id: int, message: str, session_id: str = "default", on_event=None) -> dict:
        """Streaming run — executes _run_core in a thread with on_event callback."""
        return await asyncio.to_thread(_run_core, user_id, message, session_id, on_event)

    run.reset = reset
    run.get_active_agent = get_active_agent
    run.list_sessions = list_sessions
    run.run_stream = run_stream
    return run
