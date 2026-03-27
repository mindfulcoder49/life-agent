"""Agent dispatcher and runner with session support.

Routes each user message to the correct agent based on who is currently
active for that user+session. Supports multiple chat sessions per user.
"""

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from langchain_core.messages import HumanMessage, AIMessage
from database import insert_row, get_rows, get_db
from file_logger import logger, log_conversation_turn

from agents.hydrogen import run_hydrogen
from agents.helium import run_helium
from agents.lithium import run_lithium
from agents.beryllium import run_beryllium
from agents.boron import run_boron
from agents.carbon import run_carbon
from agents.tools.state_tools import fetch_recent_states
from agents.tools.life_goal_tools import fetch_life_goals
from agents.tools.task_tools import fetch_tasks, fetch_recent_metric_completions
from agents.tools.review_tools import fetch_last_weekly_review
from agents.tools.journal_tools import fetch_recent_journal_entries


def _fetch_oldest_todo_date(user_id: int):
    rows = get_rows("todo_lists", filters={"user_id": user_id}, limit=1, order_desc=False)
    return rows[0]["created_at"][:10] if rows else None

AGENT_RUNNERS = {
    "hydrogen": run_hydrogen,
    "helium": run_helium,
    "lithium": run_lithium,
    "beryllium": run_beryllium,
    "boron": run_boron,
    "carbon": run_carbon,
}

SPECIALISTS = {"helium", "lithium", "beryllium", "boron", "carbon"}

AGENT_LABELS = {
    "hydrogen": "Hydrogen (Manager)",
    "helium": "Helium (Life Goals)",
    "lithium": "Lithium (State Check)",
    "beryllium": "Beryllium (Tasks & Metrics)",
    "boron": "Boron (Weekly Review)",
    "carbon": "Carbon (Evening Reflection)",
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

    def invalidate_goals_cache(user_id: int):
        """Clear cached life goals for all in-memory sessions belonging to this user."""
        for key, session in sessions.items():
            if key[0] == user_id:
                session["context_cache"].pop("life_goals", None)

    def invalidate_metrics_cache(user_id: int):
        """Clear cached recent metrics for all in-memory sessions belonging to this user."""
        for key, session in sessions.items():
            if key[0] == user_id:
                session["context_cache"].pop("recent_metrics", None)

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
              AND json_extract(data, '$.role') != 'session_meta'
            GROUP BY json_extract(data, '$.session_id')
            ORDER BY MAX(created_at) DESC
        """, (user_id,)).fetchall()
        name_rows = conn.execute("""
            SELECT json_extract(data, '$.session_id') as sid,
                   json_extract(data, '$.name') as name
            FROM chat_contexts
            WHERE json_extract(data, '$.user_id') = ?
              AND json_extract(data, '$.role') = 'session_meta'
        """, (user_id,)).fetchall()
        conn.close()
        names = {r["sid"]: r["name"] for r in name_rows}
        result = []
        for r in rows:
            result.append({
                "session_id": r["sid"],
                "started": r["started"],
                "last_message": r["last_msg"],
                "message_count": r["msg_count"],
                "name": names.get(r["sid"]),
            })
        return result

    def _run_core(user_id: int, message: str, session_id: str = "default", on_event=None) -> dict:
        """Core routing logic. Runs synchronously. on_event is optional callback."""
        state = _get_session(user_id, session_id)
        state["messages"].append(HumanMessage(content=message))

        active = state["active_agent"] or "hydrogen"
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # Parallel pre-fetch: all independent DB reads run concurrently on cold session start
        _prefetch = {
            "recent_states":          fetch_recent_states,
            "life_goals":             fetch_life_goals,
            "recent_metrics":         fetch_recent_metric_completions,
            "last_weekly_review":     fetch_last_weekly_review,
            "tasks":                  fetch_tasks,
            "oldest_todo_date":       _fetch_oldest_todo_date,
            "recent_journal_entries": fetch_recent_journal_entries,
        }
        missing = {k: fn for k, fn in _prefetch.items() if k not in state["context_cache"]}
        if missing:
            with ThreadPoolExecutor(max_workers=len(missing)) as _pool:
                _futures = {k: _pool.submit(fn, user_id) for k, fn in missing.items()}
                for k, fut in _futures.items():
                    state["context_cache"][k] = fut.result()

        # Derive has_tasks from pre-fetched tasks (no extra DB call needed)
        if "has_tasks" not in state["context_cache"]:
            _t = state["context_cache"].get("tasks", {})
            state["context_cache"]["has_tasks"] = bool(
                _t.get("one_time_tasks") or _t.get("recurring_tasks")
            )

        # Code-level pre-routing: skip Hydrogen LLM for unambiguous cases
        if active == "hydrogen" and not state["context_cache"].get("life_goals"):
            logger.info(f"[user={user_id}|{session_id}] Pre-routing -> helium (no life goals)")
            active = "helium"
        elif active == "hydrogen" and state["context_cache"].get("life_goals"):
            # First human message of the session + state is stale → skip Hydrogen, go to Lithium.
            # This is exactly what Hydrogen's rule 8 would decide anyway.
            _recent = state["context_cache"].get("recent_states", [])
            _state_fresh = False
            if _recent:
                try:
                    _ts = datetime.fromisoformat(_recent[0]["created_at"].replace("Z", "+00:00"))
                    _state_fresh = (datetime.now(timezone.utc) - _ts).total_seconds() < 14400
                except Exception:
                    _state_fresh = bool(_recent)  # unreadable timestamp → assume fresh, don't pre-route
            _first_msg = sum(1 for m in state["messages"] if isinstance(m, HumanMessage)) == 1
            if not _state_fresh and _first_msg:
                logger.info(f"[user={user_id}|{session_id}] Pre-routing -> lithium (stale state, session start)")
                active = "lithium"

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
                        # Specialist finished and handed back — call Hydrogen to compose the follow-up
                        state["active_agent"] = None
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

    def set_active_agent(user_id: int, session_id: str, agent: str):
        """Pre-set the active agent for a session (e.g., for proactive Discord routing)."""
        key = (user_id, session_id)
        if key not in sessions:
            sessions[key] = {"messages": [], "active_agent": None, "context_cache": {}}
        sessions[key]["active_agent"] = agent if agent in AGENT_RUNNERS else None

    run.reset = reset
    run.get_active_agent = get_active_agent
    run.set_active_agent = set_active_agent
    run.list_sessions = list_sessions
    run.run_stream = run_stream
    run.invalidate_goals_cache = invalidate_goals_cache
    run.invalidate_metrics_cache = invalidate_metrics_cache
    return run
