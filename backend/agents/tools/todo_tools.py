from langchain_core.tools import tool
from database import insert_row, get_rows, update_row, get_row, get_db
from datetime import datetime, timezone, timedelta
import json


def make_todo_tools(user_id: int, context_cache: dict = None):
    """Create todo list tools bound to a specific user_id."""
    if context_cache is None:
        context_cache = {}

    def _get_due_recurring(exclude_ids: set) -> tuple[list, list]:
        """Return (mandatory_due, overdue_due) for recurring tasks not in exclude_ids.
        Both lists respect each task's interval — only tasks overdue by their own schedule are included."""
        recurring = get_rows("recurring_tasks", filters={"user_id": user_id, "active": True}, limit=200)
        if not recurring:
            return [], []

        now = datetime.now(timezone.utc)
        ids = [t["id"] for t in recurring]
        placeholders = ",".join(["?"] * len(ids))
        conn = get_db()
        rows = conn.execute(f"""
            SELECT json_extract(data, '$.from_recurring_id') as task_id,
                   MAX(COALESCE(
                       json_extract(data, '$.completed_date'),
                       substr(json_extract(data, '$.completed_at'), 1, 10)
                   )) as last_done
            FROM one_time_tasks
            WHERE json_extract(data, '$.user_id') = ?
              AND json_extract(data, '$.from_recurring_id') IN ({placeholders})
            GROUP BY json_extract(data, '$.from_recurring_id')
        """, [user_id] + ids).fetchall()
        conn.close()

        last_done_map = {}
        for r in rows:
            tid = r["task_id"]
            if tid is not None:
                last_done_map[int(tid)] = r["last_done"]

        mandatory_due = []
        overdue_due = []
        for task in recurring:
            tid = task["id"]
            if tid in exclude_ids:
                continue
            interval = task["data"].get("interval_days", 7)
            cutoff = (now - timedelta(days=interval)).date().isoformat()
            last_done = last_done_map.get(tid)
            if not last_done or last_done < cutoff:
                item = {
                    "title": task["data"]["title"],
                    "description": task["data"].get("description", ""),
                    "source_task_id": tid,
                    "source_type": "recurring",
                    "completed": False,
                }
                if task["data"].get("mandatory"):
                    mandatory_due.append(item)
                else:
                    overdue_due.append(item)

        return mandatory_due, overdue_due

    @tool
    def create_todo_list(date: str, items: str, reasoning: str = "", agent_notes: str = "") -> str:
        """Create a daily todo list. items is a JSON array of AI-chosen task objects with fields:
        'title', 'description' (copy from source task if present), 'estimated_minutes', 'priority',
        'source_task_id' (int or null), 'source_type' ("one_time", "recurring", or null), 'completed' (false).
        Focus on one-time tasks and context-driven items — the backend automatically appends any mandatory
        or overdue recurring tasks you didn't include into separate sections."""
        try:
            items_list = json.loads(items) if isinstance(items, str) else items
        except json.JSONDecodeError:
            return json.dumps({"success": False, "message": "Invalid items JSON."})

        # Find recurring task IDs the LLM already included
        llm_task_ids = {
            i["source_task_id"]
            for i in items_list
            if isinstance(i, dict) and i.get("source_task_id") and i.get("source_type") == "recurring"
        }

        # Auto-inject mandatory and overdue recurring tasks the LLM missed
        mandatory_items, overdue_items = _get_due_recurring(llm_task_ids)

        data = {
            "user_id": user_id,
            "date": date,
            "items": items_list,
            "mandatory_items": mandatory_items,
            "overdue_items": overdue_items,
            "reasoning": reasoning,
            "agent_notes": agent_notes,
        }
        row_id = insert_row("todo_lists", data)
        context_cache["last_todo_list_id"] = row_id
        return json.dumps({
            "success": True,
            "id": row_id,
            "message": (
                f"Todo list for {date} created: {len(items_list)} AI-chosen items, "
                f"{len(mandatory_items)} mandatory items auto-added, "
                f"{len(overdue_items)} overdue items auto-added."
            ),
        })

    @tool
    def update_todo_list(list_id: int, add_items: str = "[]", remove_indices: str = "[]") -> str:
        """Add or remove items from the AI-chosen section of an existing todo list.
        add_items: JSON array of item objects to append.
        remove_indices: JSON array of integer indices to remove from the items list.
        Use this when the user says you forgot something — do not recreate the whole list."""
        row = get_row("todo_lists", list_id)
        if not row or row["data"].get("user_id") != user_id:
            return json.dumps({"success": False, "message": "Todo list not found."})
        data = row["data"]
        items = data.get("items", [])
        try:
            remove_list = json.loads(remove_indices) if isinstance(remove_indices, str) else remove_indices
        except json.JSONDecodeError:
            remove_list = []
        for idx in sorted(remove_list, reverse=True):
            if 0 <= idx < len(items):
                items.pop(idx)
        try:
            add_list = json.loads(add_items) if isinstance(add_items, str) else add_items
        except json.JSONDecodeError:
            add_list = []
        items.extend(add_list)
        data["items"] = items
        update_row("todo_lists", list_id, data)
        return json.dumps({"success": True, "id": list_id, "item_count": len(items), "message": "Todo list updated."})

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
        """Check for recurring tasks that haven't been completed recently (based on their interval).
        Returns all overdue tasks regardless of mandatory flag."""
        mandatory, overdue = _get_due_recurring(set())
        return json.dumps(mandatory + overdue)

    return [create_todo_list, update_todo_list, get_completed_tasks_recent, get_overdue_recurring_tasks]
