from langchain_core.tools import tool
from database import insert_row, update_row, delete_row, get_rows, get_row, get_db, user_today
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import json


def fetch_recent_metric_completions(user_id: int, days: int = 14) -> list[dict]:
    """Fetch recent recurring task completions that have a metric_value logged."""
    conn = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = conn.execute("""
        SELECT * FROM one_time_tasks
        WHERE json_extract(data, '$.user_id') = ?
          AND json_extract(data, '$.from_recurring_id') IS NOT NULL
          AND json_extract(data, '$.metric_value') IS NOT NULL
          AND json_extract(data, '$.completed_at') >= ?
        ORDER BY json_extract(data, '$.completed_at') DESC
        LIMIT 200
    """, (user_id, cutoff)).fetchall()
    conn.close()
    return [{"id": r["id"], "created_at": r["created_at"], **json.loads(r["data"])} for r in rows]


def format_metrics_for_prompt(recent_completions: list[dict]) -> str:
    """Format recent metric completions for injection into agent system prompts."""
    if not recent_completions:
        return "## Recent Metrics\nNo metric data logged yet."

    groups = defaultdict(list)
    for c in recent_completions:
        snapshot = c.get("metric_snapshot") or {}
        label = snapshot.get("label") or c.get("title", "Unknown")
        groups[label].append(c)

    lines = ["## Recent Metrics"]
    for label, entries in sorted(groups.items()):
        sorted_entries = sorted(entries, key=lambda x: x.get("completed_at", ""), reverse=True)[:5]
        snapshot = sorted_entries[0].get("metric_snapshot") or {}
        unit = snapshot.get("unit", "")
        header = f"\n### {label}"
        if unit:
            header += f" ({unit})"
        lines.append(header)
        for e in sorted_entries:
            val = e.get("metric_value", "")
            ts = (e.get("completed_at") or "")[:10]
            extra = ""
            if e.get("est_calories"):
                parts = [f"~{e['est_calories']} cal"]
                if e.get("est_protein_g"):
                    parts.append(f"{e['est_protein_g']}g protein")
                extra = f" ({', '.join(parts)})"
            lines.append(f"- [{ts}] {val}{extra}")

    return "\n".join(lines)


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
        lines.append("\n### Recurring Tasks")
        for t in rec:
            mandatory = " [MANDATORY]" if t.get("mandatory") else ""
            lines.append(f"- [id={t['id']}] {t['title']}{mandatory} | every {t.get('interval_days', 1)}d | est {t.get('estimated_minutes', 0)}min")
    else:
        lines.append("No active recurring tasks.")
    return "\n".join(lines)


def make_task_tools(user_id: int, context_cache: dict = None):
    """Create task management tools bound to a specific user_id."""
    if context_cache is None:
        context_cache = {}

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
        return json.dumps({"success": True, "message": f"Task {task_id} marked as completed."})

    @tool
    def add_recurring_task(
        title: str,
        description: str = "",
        interval_days: int = 7,
        estimated_minutes: int = 0,
        cognitive_load: int = 5,
        life_goal_ids: str = "[]",
        metric: str = "",
        mandatory: bool = False,
    ) -> str:
        """Add a recurring task. interval_days is how often it repeats. life_goal_ids is a JSON array of goal IDs. metric is an optional JSON object: {"label": "...", "unit": "...", "value_type": "number"|"text"|"meal"}. Set mandatory=True if this task is directly essential for one of the user's life goals — mandatory tasks are always included in the daily todo list when due, in a dedicated section."""
        try:
            goal_ids = json.loads(life_goal_ids) if isinstance(life_goal_ids, str) else life_goal_ids
        except json.JSONDecodeError:
            goal_ids = []
        metric_data = None
        if metric:
            try:
                metric_data = json.loads(metric) if isinstance(metric, str) else metric
            except json.JSONDecodeError:
                pass
        data = {
            "user_id": user_id,
            "title": title,
            "description": description,
            "interval_days": interval_days,
            "estimated_minutes": estimated_minutes,
            "cognitive_load": cognitive_load,
            "life_goal_ids": goal_ids,
            "active": True,
            "mandatory": mandatory,
        }
        if metric_data:
            data["metric"] = metric_data
        row_id = insert_row("recurring_tasks", data)
        context_cache.pop("tasks", None)
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
        metric_value: str = "",
        metric_notes: str = "",
        est_calories: int = 0,
        est_protein_g: int = 0,
        est_carbs_g: int = 0,
        est_fat_g: int = 0,
    ) -> str:
        """Mark a recurring task as completed for this cycle. If the task has a metric, pass metric_value. For meal-type metrics, also pass est_calories, est_protein_g, est_carbs_g, est_fat_g."""
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
            "cognitive_load": row["data"].get("cognitive_load", 5),
            "estimated_minutes": row["data"].get("estimated_minutes", 0),
        }
        if row["data"].get("metric"):
            completed_data["metric_snapshot"] = row["data"]["metric"]
        if metric_value:
            completed_data["metric_value"] = metric_value
        if metric_notes:
            completed_data["metric_notes"] = metric_notes
        if est_calories:
            completed_data["est_calories"] = est_calories
        if est_protein_g:
            completed_data["est_protein_g"] = est_protein_g
        if est_carbs_g:
            completed_data["est_carbs_g"] = est_carbs_g
        if est_fat_g:
            completed_data["est_fat_g"] = est_fat_g
        completed_id = insert_row("one_time_tasks", completed_data)
        return json.dumps({
            "success": True,
            "completed_record_id": completed_id,
            "message": f"Recurring task '{row['data']['title']}' completed for this cycle.",
        })

    @tool
    def get_tasks() -> str:
        """WARNING: get_tasks output is already in the system prompt under '## Current Tasks'. Do NOT call this unless you just wrote a task and need a refresh. Calling it otherwise wastes a round-trip and returns the same data already shown above."""
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
