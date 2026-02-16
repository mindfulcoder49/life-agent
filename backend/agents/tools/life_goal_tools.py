from langchain_core.tools import tool
from database import insert_row, update_row, delete_row, get_rows, get_row
import json


def make_life_goal_tools(user_id: int):
    """Create life goal tools bound to a specific user_id."""

    @tool
    def add_life_goal(title: str, description: str = "", priority: int = 5, stress: int = 5) -> str:
        """Add a new life goal for the user. Priority and stress are 1-10 scales."""
        data = {
            "user_id": user_id,
            "title": title,
            "description": description,
            "priority": priority,
            "stress": stress,
            "status": "active",
        }
        row_id = insert_row("life_goals", data)
        return json.dumps({"success": True, "id": row_id, "message": f"Life goal '{title}' created."})

    @tool
    def update_life_goal(goal_id: int, updates: str) -> str:
        """Update an existing life goal. Pass updates as a JSON string with fields to change (title, description, priority, stress, status)."""
        row = get_row("life_goals", goal_id)
        if not row:
            return json.dumps({"success": False, "message": "Life goal not found."})
        if row["data"].get("user_id") != user_id:
            return json.dumps({"success": False, "message": "You do not own this life goal."})
        try:
            updates_dict = json.loads(updates) if isinstance(updates, str) else updates
        except json.JSONDecodeError:
            return json.dumps({"success": False, "message": "Invalid updates JSON."})
        merged = {**row["data"], **updates_dict}
        update_row("life_goals", goal_id, merged)
        return json.dumps({"success": True, "message": f"Life goal {goal_id} updated."})

    @tool
    def delete_life_goal(goal_id: int) -> str:
        """Delete a life goal by ID."""
        row = get_row("life_goals", goal_id)
        if not row:
            return json.dumps({"success": False, "message": "Life goal not found."})
        if row["data"].get("user_id") != user_id:
            return json.dumps({"success": False, "message": "You do not own this life goal."})
        delete_row("life_goals", goal_id)
        return json.dumps({"success": True, "message": f"Life goal {goal_id} deleted."})

    @tool
    def get_life_goals() -> str:
        """Get all life goals for the current user."""
        rows = get_rows("life_goals", filters={"user_id": user_id}, limit=100)
        goals = [{"id": r["id"], **r["data"]} for r in rows]
        return json.dumps(goals)

    return [add_life_goal, update_life_goal, delete_life_goal, get_life_goals]
