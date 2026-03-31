from langchain_core.tools import tool
from database import insert_row, update_row, delete_row, get_rows, get_row, get_db, user_today
from datetime import datetime, timezone, timedelta
import json


def fetch_tasks(user_id: int) -> dict:
    """Fetch current incomplete one-time and active recurring tasks for a user."""
    one_time = get_rows("one_time_tasks", filters={"user_id": user_id, "completed": False}, limit=200)
    recurring = get_rows("recurring_tasks", filters={"user_id": user_id, "active": True}, limit=200)
    return {
        "one_time_tasks": [{"id": r["id"], "created_at": r["created_at"], **r["data"]} for r in one_time],
        "recurring_tasks": [{"id": r["id"], "created_at": r["created_at"], **r["data"]} for r in recurring],
    }


def format_tasks_for_prompt(tasks: dict) -> str:
    """Format tasks dict for injection into agent system prompts."""
    if not tasks:
        return "## Current Tasks\nNo tasks loaded."
    ot = tasks.get("one_time_tasks", [])
    rec = tasks.get("recurring_tasks", [])
    lines = ["## Current Tasks"]
    if ot:
        lines.append("\n### One-Time Tasks")
        for t in ot:
            deadline = f" | deadline: {t['deadline']}" if t.get("deadline") else ""
            lines.append(f"- [id={t['id']}] {t['title']}{deadline} | est {t.get('estimated_minutes', 0)}min | load {t.get('cognitive_load', 5)}")
    else:
        lines.append("No incomplete one-time tasks.")
    if rec:
        active = [t for t in rec if t.get("status", "active") == "active"]
        habits = [t for t in rec if t.get("status") == "habit"]
        if active:
            lines.append("\n### Active Habit Tasks (building — one per goal)")
            for t in active:
                goal_ids = t.get("life_goal_ids", [])
                lines.append(f"- [id={t['id']}] {t['title']} | goals={goal_ids} | est {t.get('estimated_minutes', 0)}min")
        if habits:
            lines.append("\n### Established Habits (graduated)")
            for t in habits:
                lines.append(f"- [id={t['id']}] {t['title']} ✓")
    else:
        lines.append("No recurring tasks.")
    return "\n".join(lines)


def make_task_tools(user_id: int, context_cache: dict = None):
    """Create task management tools bound to a specific user_id."""
    if context_cache is None:
        context_cache = {}

    def _get_streak(task_id: int) -> int:
        """Count completions of a recurring task in the last 7 days."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        conn = get_db()
        count = conn.execute("""
            SELECT COUNT(*) FROM one_time_tasks
            WHERE json_extract(data, '$.user_id') = ?
              AND json_extract(data, '$.from_recurring_id') = ?
              AND json_extract(data, '$.completed_at') >= ?
        """, (user_id, task_id, cutoff)).fetchone()[0]
        conn.close()
        return count

    def _check_and_graduate(task_id: int) -> dict:
        """Check streak and graduate to habit status if >= 6/7 days."""
        streak = _get_streak(task_id)
        graduated = False
        if streak >= 6:
            row = get_row("recurring_tasks", task_id)
            if row and row["data"].get("status", "active") != "habit":
                data = row["data"]
                data["status"] = "habit"
                update_row("recurring_tasks", task_id, data)
                context_cache.pop("tasks", None)
                graduated = True
        return {"streak": streak, "graduated": graduated}

    def _mark_todo_item_completed(source_task_id: int, source_type: str):
        """Check off the matching item in today's active todo list."""
        today = user_today(user_id)
        conn = get_db()
        row = conn.execute("""
            SELECT id, data FROM todo_lists
            WHERE json_extract(data, '$.user_id') = ?
              AND json_extract(data, '$.date') = ?
            ORDER BY id DESC LIMIT 1
        """, (user_id, today)).fetchone()
        conn.close()
        if not row:
            return
        try:
            data = json.loads(row["data"])
        except Exception:
            return
        changed = False
        for section in ("items", "habit_items", "mandatory_items", "overdue_items"):
            for item in data.get(section, []):
                if item.get("source_task_id") == source_task_id and item.get("source_type") == source_type:
                    item["completed"] = True
                    changed = True
        if changed:
            update_row("todo_lists", row["id"], data)

    @tool
    def get_habit_progress() -> str:
        """Get all recurring tasks with their 7-day completion streak and status.
        Use this to see which habits are active vs graduated, and track progress."""
        rows = get_rows("recurring_tasks", filters={"user_id": user_id, "active": True}, limit=200)
        if not rows:
            return json.dumps([])
        ids = [r["id"] for r in rows]
        placeholders = ",".join(["?"] * len(ids))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        conn = get_db()
        streak_rows = conn.execute(f"""
            SELECT json_extract(data, '$.from_recurring_id') as task_id, COUNT(*) as count
            FROM one_time_tasks
            WHERE json_extract(data, '$.user_id') = ?
              AND json_extract(data, '$.from_recurring_id') IN ({placeholders})
              AND json_extract(data, '$.completed_at') >= ?
            GROUP BY json_extract(data, '$.from_recurring_id')
        """, [user_id] + ids + [cutoff]).fetchall()
        conn.close()
        streak_map = {int(r["task_id"]): r["count"] for r in streak_rows if r["task_id"]}
        result = []
        for r in rows:
            d = r["data"]
            tid = r["id"]
            streak = streak_map.get(tid, 0)
            result.append({
                "id": tid,
                "title": d.get("title"),
                "status": d.get("status", "active"),
                "streak_last_7": streak,
                "streak_label": f"{streak}/7 this week",
                "life_goal_ids": d.get("life_goal_ids", []),
            })
        return json.dumps(result)

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
        context_cache.pop("tasks", None)
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
        context_cache.pop("tasks", None)
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
        context_cache.pop("tasks", None)
        return json.dumps({"success": True, "message": f"Task {task_id} deleted."})

    @tool
    def complete_one_time_task(task_id: int) -> str:
        """Mark a one-time task as completed."""
        row = get_row("one_time_tasks", task_id)
        if not row:
            return json.dumps({"success": False, "message": "Task not found."})
        if row["data"].get("user_id") != user_id:
            return json.dumps({"success": False, "message": "You do not own this task."})
        merged = {**row["data"], "completed": True, "completed_at": datetime.now(timezone.utc).isoformat()}
        update_row("one_time_tasks", task_id, merged)
        context_cache.pop("tasks", None)
        _mark_todo_item_completed(task_id, "one_time")
        return json.dumps({"success": True, "message": f"Task {task_id} marked as completed."})

    @tool
    def add_recurring_task(
        title: str,
        description: str = "",
        interval_days: int = 1,
        estimated_minutes: int = 0,
        cognitive_load: int = 5,
        life_goal_ids: str = "[]",
    ) -> str:
        """Add a recurring habit task. interval_days is how often it repeats (default 1 = daily).
        life_goal_ids is a JSON array of goal IDs — always include this.
        One active habit task per goal — check get_habit_progress first to ensure no active task exists for this goal."""
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
            "status": "active",
        }
        row_id = insert_row("recurring_tasks", data)
        context_cache.pop("tasks", None)
        return json.dumps({"success": True, "id": row_id, "message": f"Habit task '{title}' created."})

    @tool
    def update_recurring_task(task_id: int, updates: str) -> str:
        """Update a recurring task. Pass updates as a JSON string with fields to change.
        To graduate manually: {\"status\": \"habit\"}. To reactivate a lapsed habit: {\"status\": \"active\"}."""
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
        context_cache.pop("tasks", None)
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
        context_cache.pop("tasks", None)
        return json.dumps({"success": True, "message": f"Recurring task {task_id} deleted."})

    @tool
    def complete_recurring_task(
        task_id: int,
        notes: str = "",
    ) -> str:
        """Mark a recurring habit task as completed for today. Streak is checked automatically —
        at 6/7 completions in the last 7 days the task graduates to established habit status."""
        row = get_row("recurring_tasks", task_id)
        if not row:
            return json.dumps({"success": False, "message": "Recurring task not found."})
        if row["data"].get("user_id") != user_id:
            return json.dumps({"success": False, "message": "You do not own this task."})
        completed_data = {
            "user_id": user_id,
            "title": row["data"]["title"],
            "description": row["data"].get("description", ""),
            "from_recurring_id": task_id,
            "completed": True,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "completed_date": user_today(user_id),
            "life_goal_ids": row["data"].get("life_goal_ids", []),
        }
        if notes:
            completed_data["notes"] = notes
        completed_id = insert_row("one_time_tasks", completed_data)
        _mark_todo_item_completed(task_id, "recurring")
        graduation = _check_and_graduate(task_id)
        msg = f"'{row['data']['title']}' completed. Streak: {graduation['streak']}/7 this week."
        if graduation["graduated"]:
            msg += " This habit has graduated to established status — it's now part of who you are."
        return json.dumps({
            "success": True,
            "completed_record_id": completed_id,
            "streak": graduation["streak"],
            "graduated": graduation["graduated"],
            "message": msg,
        })

    @tool
    def get_tasks() -> str:
        """WARNING: output is already in the system prompt under '## Current Tasks'. Only call after writing a task and needing a refresh."""
        if "tasks" in context_cache:
            return json.dumps(context_cache["tasks"])
        one_time = get_rows("one_time_tasks", filters={"user_id": user_id, "completed": False}, limit=200)
        recurring = get_rows("recurring_tasks", filters={"user_id": user_id, "active": True}, limit=200)
        result = {
            "one_time_tasks": [{"id": r["id"], "created_at": r["created_at"], **r["data"]} for r in one_time],
            "recurring_tasks": [{"id": r["id"], "created_at": r["created_at"], **r["data"]} for r in recurring],
        }
        context_cache["tasks"] = result
        return json.dumps(result)

    @tool
    def get_life_goals() -> str:
        """Get all life goals for the current user. Useful for linking tasks to goals."""
        if "life_goals" in context_cache:
            return json.dumps(context_cache["life_goals"])
        rows = get_rows("life_goals", filters={"user_id": user_id}, limit=100)
        goals = [{"id": r["id"], **r["data"]} for r in rows]
        context_cache["life_goals"] = goals
        return json.dumps(goals)

    return [
        get_habit_progress,
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
