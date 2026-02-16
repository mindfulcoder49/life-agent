from langchain_core.tools import tool
from database import insert_row, update_row, delete_row, get_rows, get_row
import json


def make_task_tools(user_id: int):
    """Create task management tools bound to a specific user_id."""

    @tool
    def add_one_time_task(
        title: str,
        description: str = "",
        deadline: str = "",
        estimated_minutes: int = 0,
        cognitive_load: int = 5,
        life_goal_ids: str = "[]",
    ) -> str:
        """Add a one-time task. life_goal_ids should be a JSON array of goal ID integers."""
        try:
            goal_ids = json.loads(life_goal_ids) if isinstance(life_goal_ids, str) else life_goal_ids
        except json.JSONDecodeError:
            goal_ids = []
        data = {
            "user_id": user_id,
            "title": title,
            "description": description,
            "deadline": deadline,
            "estimated_minutes": estimated_minutes,
            "cognitive_load": cognitive_load,
            "life_goal_ids": goal_ids,
            "completed": False,
        }
        row_id = insert_row("one_time_tasks", data)
        return json.dumps({"success": True, "id": row_id, "message": f"Task '{title}' created."})

    @tool
    def update_one_time_task(task_id: int, updates: str) -> str:
        """Update a one-time task. Pass updates as a JSON string with fields to change."""
        row = get_row("one_time_tasks", task_id)
        if not row:
            return json.dumps({"success": False, "message": "Task not found."})
        if row["data"].get("user_id") != user_id:
            return json.dumps({"success": False, "message": "You do not own this task."})
        try:
            updates_dict = json.loads(updates) if isinstance(updates, str) else updates
        except json.JSONDecodeError:
            return json.dumps({"success": False, "message": "Invalid updates JSON."})
        merged = {**row["data"], **updates_dict}
        update_row("one_time_tasks", task_id, merged)
        return json.dumps({"success": True, "message": f"Task {task_id} updated."})

    @tool
    def delete_one_time_task(task_id: int) -> str:
        """Delete a one-time task by ID."""
        row = get_row("one_time_tasks", task_id)
        if not row:
            return json.dumps({"success": False, "message": "Task not found."})
        if row["data"].get("user_id") != user_id:
            return json.dumps({"success": False, "message": "You do not own this task."})
        delete_row("one_time_tasks", task_id)
        return json.dumps({"success": True, "message": f"Task {task_id} deleted."})

    @tool
    def complete_one_time_task(task_id: int) -> str:
        """Mark a one-time task as completed."""
        row = get_row("one_time_tasks", task_id)
        if not row:
            return json.dumps({"success": False, "message": "Task not found."})
        if row["data"].get("user_id") != user_id:
            return json.dumps({"success": False, "message": "You do not own this task."})
        merged = {**row["data"], "completed": True}
        update_row("one_time_tasks", task_id, merged)
        return json.dumps({"success": True, "message": f"Task {task_id} marked as completed."})

    @tool
    def add_recurring_task(
        title: str,
        description: str = "",
        interval_days: int = 7,
        estimated_minutes: int = 0,
        cognitive_load: int = 5,
        life_goal_ids: str = "[]",
    ) -> str:
        """Add a recurring task. interval_days is how often it repeats. life_goal_ids is a JSON array of goal IDs."""
        try:
            goal_ids = json.loads(life_goal_ids) if isinstance(life_goal_ids, str) else life_goal_ids
        except json.JSONDecodeError:
            goal_ids = []
        data = {
            "user_id": user_id,
            "title": title,
            "description": description,
            "interval_days": interval_days,
            "estimated_minutes": estimated_minutes,
            "cognitive_load": cognitive_load,
            "life_goal_ids": goal_ids,
            "active": True,
        }
        row_id = insert_row("recurring_tasks", data)
        return json.dumps({"success": True, "id": row_id, "message": f"Recurring task '{title}' created."})

    @tool
    def update_recurring_task(task_id: int, updates: str) -> str:
        """Update a recurring task. Pass updates as a JSON string with fields to change."""
        row = get_row("recurring_tasks", task_id)
        if not row:
            return json.dumps({"success": False, "message": "Recurring task not found."})
        if row["data"].get("user_id") != user_id:
            return json.dumps({"success": False, "message": "You do not own this task."})
        try:
            updates_dict = json.loads(updates) if isinstance(updates, str) else updates
        except json.JSONDecodeError:
            return json.dumps({"success": False, "message": "Invalid updates JSON."})
        merged = {**row["data"], **updates_dict}
        update_row("recurring_tasks", task_id, merged)
        return json.dumps({"success": True, "message": f"Recurring task {task_id} updated."})

    @tool
    def delete_recurring_task(task_id: int) -> str:
        """Delete a recurring task by ID."""
        row = get_row("recurring_tasks", task_id)
        if not row:
            return json.dumps({"success": False, "message": "Recurring task not found."})
        if row["data"].get("user_id") != user_id:
            return json.dumps({"success": False, "message": "You do not own this task."})
        delete_row("recurring_tasks", task_id)
        return json.dumps({"success": True, "message": f"Recurring task {task_id} deleted."})

    @tool
    def complete_recurring_task(task_id: int) -> str:
        """Mark a recurring task as completed for this cycle. Creates a completed one-time record."""
        row = get_row("recurring_tasks", task_id)
        if not row:
            return json.dumps({"success": False, "message": "Recurring task not found."})
        if row["data"].get("user_id") != user_id:
            return json.dumps({"success": False, "message": "You do not own this task."})
        completed_data = {
            "user_id": user_id,
            "title": row["data"]["title"],
            "description": row["data"].get("description", ""),
            "source_recurring_task_id": task_id,
            "completed": True,
            "life_goal_ids": row["data"].get("life_goal_ids", []),
            "cognitive_load": row["data"].get("cognitive_load", 5),
            "estimated_minutes": row["data"].get("estimated_minutes", 0),
        }
        completed_id = insert_row("one_time_tasks", completed_data)
        return json.dumps({
            "success": True,
            "completed_record_id": completed_id,
            "message": f"Recurring task '{row['data']['title']}' completed for this cycle.",
        })

    @tool
    def get_tasks() -> str:
        """Get all incomplete one-time tasks and active recurring tasks for the current user."""
        one_time = get_rows("one_time_tasks", filters={"user_id": user_id, "completed": False}, limit=200)
        recurring = get_rows("recurring_tasks", filters={"user_id": user_id, "active": True}, limit=200)
        result = {
            "one_time_tasks": [{"id": r["id"], "created_at": r["created_at"], **r["data"]} for r in one_time],
            "recurring_tasks": [{"id": r["id"], "created_at": r["created_at"], **r["data"]} for r in recurring],
        }
        return json.dumps(result)

    @tool
    def get_life_goals() -> str:
        """Get all life goals for the current user. Useful for linking tasks to goals."""
        rows = get_rows("life_goals", filters={"user_id": user_id}, limit=100)
        goals = [{"id": r["id"], **r["data"]} for r in rows]
        return json.dumps(goals)

    return [
        add_one_time_task,
        update_one_time_task,
        delete_one_time_task,
        complete_one_time_task,
        add_recurring_task,
        update_recurring_task,
        delete_recurring_task,
        complete_recurring_task,
        get_tasks,
        get_life_goals,
    ]
