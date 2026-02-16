from langchain_core.tools import tool
from database import insert_row, get_rows
import json


def make_state_tools(user_id: int):
    """Create user state tools bound to a specific user_id."""

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
        return json.dumps({"success": True, "id": row_id, "message": "State recorded."})

    @tool
    def get_recent_states(limit: int = 5) -> str:
        """Get the user's most recent state check-ins."""
        rows = get_rows("user_states", filters={"user_id": user_id}, limit=limit, order_desc=True)
        states = [{"id": r["id"], "created_at": r["created_at"], **r["data"]} for r in rows]
        return json.dumps(states)

    return [add_user_state, get_recent_states]
