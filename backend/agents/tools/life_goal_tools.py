from langchain_core.tools import tool
from database import insert_row, update_row, delete_row, get_rows, get_row
import json


def fetch_life_goals(user_id: int) -> list[dict]:
    """Plain helper (not a tool). Queries DB for life goals, returns list of goal dicts."""
    rows = get_rows("life_goals", filters={"user_id": user_id}, limit=100)
    return [{"id": r["id"], **r["data"]} for r in rows]


def format_goals_for_prompt(goals: list[dict]) -> str:
    """Format a list of goal dicts into a readable section for system prompts."""
    if not goals:
        return "## Life Goals\nNo life goals recorded yet."
    lines = ["## Life Goals"]
    for g in goals:
        status = g.get("status", "active")
        priority = g.get("priority", "?")
        stress = g.get("stress", "?")
        desc = f" — {g['description']}" if g.get("description") else ""
        lines.append(f"- (id={g['id']}) [{status}] {g['title']}{desc} (priority={priority}/10, stress={stress}/10)")
    return "\n".join(lines)


def make_life_goal_tools(user_id: int, context_cache: dict = None):
    """Create life goal tools bound to a specific user_id."""
    if context_cache is None:
        context_cache = {}

    def _refresh_cache():
        context_cache["life_goals"] = fetch_life_goals(user_id)

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
        _refresh_cache()
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
        _refresh_cache()
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
        _refresh_cache()
        return json.dumps({"success": True, "message": f"Life goal {goal_id} deleted."})

    @tool
    def get_life_goals() -> str:
        """Get all life goals for the current user."""
        if "life_goals" in context_cache:
            return json.dumps(context_cache["life_goals"])
        goals = fetch_life_goals(user_id)
        context_cache["life_goals"] = goals
        return json.dumps(goals)

    return [add_life_goal, update_life_goal, delete_life_goal, get_life_goals]
