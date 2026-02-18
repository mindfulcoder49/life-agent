from langchain_core.tools import tool
from database import insert_row, get_row, get_rows, update_row
import json


def fetch_recent_states(user_id: int, limit: int = 5) -> list[dict]:
    """Plain helper (not a tool). Queries DB for recent states, returns list of state dicts."""
    rows = get_rows("user_states", filters={"user_id": user_id}, limit=limit, order_desc=True)
    return [{"id": r["id"], "created_at": r["created_at"], **r["data"]} for r in rows]


def format_states_for_prompt(states: list[dict]) -> str:
    """Format a list of state dicts into a readable section for system prompts."""
    if not states:
        return "## Recent States\nNo state check-ins recorded yet."
    lines = ["## Recent States"]
    for s in states:
        parts = []
        if s.get("food"):
            parts.append(f"Food: {s['food']}")
        if s.get("exercise"):
            parts.append(f"Exercise: {s['exercise']}")
        if s.get("sleep"):
            parts.append(f"Sleep: {s['sleep']}")
        parts.append(f"Energy: {s.get('energy', '?')}/10")
        parts.append(f"Soreness: {s.get('soreness', '?')}/10")
        parts.append(f"Sickness: {s.get('sickness', '?')}/10")
        if s.get("notes"):
            parts.append(f"Notes: {s['notes']}")
        timestamp = s.get("created_at", "unknown")
        lines.append(f"- [{timestamp}] (id={s.get('id')}): {', '.join(parts)}")
    return "\n".join(lines)


def make_state_tools(user_id: int, context_cache: dict = None):
    """Create user state tools bound to a specific user_id."""
    if context_cache is None:
        context_cache = {}

    def _refresh_cache():
        context_cache["recent_states"] = fetch_recent_states(user_id)

    @tool
    def add_user_state(
        food: str = "",
        exercise: str = "",
        sleep: str = "",
        energy: int = 5,
        soreness: int = 1,
        sickness: int = 1,
        notes: str = "",
    ) -> str:
        """Record the user's current physical and mental state. Energy is 1-10, soreness and sickness are 1-10."""
        data = {
            "user_id": user_id,
            "food": food,
            "exercise": exercise,
            "sleep": sleep,
            "energy": energy,
            "soreness": soreness,
            "sickness": sickness,
            "notes": notes,
        }
        row_id = insert_row("user_states", data)
        _refresh_cache()
        return json.dumps({"success": True, "id": row_id, "message": "State recorded."})

    @tool
    def update_user_state(
        state_id: int,
        food: str = None,
        exercise: str = None,
        sleep: str = None,
        energy: int = None,
        soreness: int = None,
        sickness: int = None,
        notes: str = None,
    ) -> str:
        """Update an existing user state record. Provide state_id and only the fields you want to change. Use this to add fields to a state from this session instead of creating a new one."""
        row = get_row("user_states", state_id)
        if not row:
            return json.dumps({"success": False, "message": f"State {state_id} not found."})
        if row["data"].get("user_id") != user_id:
            return json.dumps({"success": False, "message": "Not your state."})
        existing = row["data"]
        updates = {
            "food": food, "exercise": exercise, "sleep": sleep,
            "energy": energy, "soreness": soreness, "sickness": sickness,
            "notes": notes,
        }
        for key, value in updates.items():
            if value is not None:
                existing[key] = value
        update_row("user_states", state_id, existing)
        _refresh_cache()
        return json.dumps({"success": True, "id": state_id, "message": "State updated."})

    return [add_user_state, update_user_state]
