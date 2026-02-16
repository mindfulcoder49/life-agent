from langchain_core.tools import tool
from database import insert_row, get_rows
from datetime import datetime, timezone, timedelta
import json


def make_todo_tools(user_id: int):
    """Create todo list tools bound to a specific user_id."""

    @tool
    def create_todo_list(date: str, items: str, reasoning: str = "", agent_notes: str = "") -> str:
        """Create a daily todo list for the user. items should be a JSON array of task objects with 'title', 'estimated_minutes', 'priority', and optional 'source_task_id'."""
        try:
            items_list = json.loads(items) if isinstance(items, str) else items
        except json.JSONDecodeError:
            return json.dumps({"success": False, "message": "Invalid items JSON."})
        data = {
            "user_id": user_id,
            "date": date,
            "items": items_list,
            "reasoning": reasoning,
            "agent_notes": agent_notes,
        }
        row_id = insert_row("todo_lists", data)
        return json.dumps({"success": True, "id": row_id, "message": f"Todo list for {date} created."})

    @tool
    def get_completed_tasks_recent(days: int = 7) -> str:
        """Get tasks completed in the last N days."""
        rows = get_rows("one_time_tasks", filters={"user_id": user_id, "completed": True}, limit=200, order_desc=True)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        recent = []
        for r in rows:
            if r.get("created_at", "") >= cutoff:
                recent.append({"id": r["id"], "created_at": r["created_at"], **r["data"]})
        return json.dumps(recent)

    @tool
    def get_overdue_recurring_tasks() -> str:
        """Check for recurring tasks that haven't been completed recently (based on their interval)."""
        recurring = get_rows("recurring_tasks", filters={"user_id": user_id, "active": True}, limit=200)
        completed = get_rows("one_time_tasks", filters={"user_id": user_id, "completed": True}, limit=500, order_desc=True)
        now = datetime.now(timezone.utc)
        overdue = []
        for task in recurring:
            task_id = task["id"]
            interval = task["data"].get("interval_days", 7)
            cutoff = (now - timedelta(days=interval)).isoformat()
            # Check if any completed record references this recurring task since cutoff
            recently_done = any(
                c["data"].get("source_recurring_task_id") == task_id and c.get("created_at", "") >= cutoff
                for c in completed
            )
            if not recently_done:
                overdue.append({"id": task_id, "created_at": task["created_at"], **task["data"]})
        return json.dumps(overdue)

    return [create_todo_list, get_completed_tasks_recent, get_overdue_recurring_tasks]
