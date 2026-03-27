from langchain_core.tools import tool
from database import insert_row, get_rows, get_db
from datetime import datetime, timezone, timedelta
import json


def fetch_last_weekly_review(user_id: int) -> dict | None:
    """Fetch the most recent weekly review for a user. Plain helper for pre-fetching."""
    rows = get_rows("weekly_reviews", filters={"user_id": user_id}, limit=1, order_desc=True)
    if not rows:
        return None
    return {"id": rows[0]["id"], "created_at": rows[0]["created_at"], **rows[0]["data"]}


def make_review_tools(user_id: int):
    """Create weekly review tools bound to a specific user_id."""

    @tool
    def get_week_completions(days_back: int = 7) -> str:
        """Fetch all tasks completed in the past N days, including metric values logged."""
        conn = get_db()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()
        rows = conn.execute("""
            SELECT * FROM one_time_tasks
            WHERE json_extract(data, '$.user_id') = ?
              AND json_extract(data, '$.completed') = 1
              AND json_extract(data, '$.completed_at') >= ?
            ORDER BY json_extract(data, '$.completed_at') DESC
            LIMIT 200
        """, (user_id, cutoff)).fetchall()
        conn.close()
        completions = [{"id": r["id"], "created_at": r["created_at"], **json.loads(r["data"])} for r in rows]
        return json.dumps(completions)

    @tool
    def get_week_incomplete() -> str:
        """Fetch what DIDN'T happen: all incomplete one-time tasks (with age) and
        all active recurring tasks showing when each was last completed and whether
        it is currently overdue. Call this alongside get_week_completions."""
        now = datetime.now(timezone.utc)

        # --- Incomplete one-time tasks ---
        ot_rows = get_rows("one_time_tasks", filters={"user_id": user_id, "completed": False}, limit=200)
        incomplete = []
        for r in ot_rows:
            d = r["data"]
            created = r.get("created_at", "")
            age_days = None
            if created:
                try:
                    age_days = (now - datetime.fromisoformat(created.replace("Z", "+00:00"))).days
                except Exception:
                    pass
            incomplete.append({
                "id": r["id"],
                "title": d.get("title"),
                "description": d.get("description"),
                "deadline": d.get("deadline"),
                "cognitive_load": d.get("cognitive_load"),
                "estimated_minutes": d.get("estimated_minutes"),
                "age_days": age_days,
                "created_at": created,
            })

        # --- Recurring tasks: overdue check ---
        rec_rows = get_rows("recurring_tasks", filters={"user_id": user_id, "active": True}, limit=200)
        if rec_rows:
            ids = [r["id"] for r in rec_rows]
            placeholders = ",".join(["?"] * len(ids))
            conn = get_db()
            done_rows = conn.execute(f"""
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
            last_done_map = {int(r["task_id"]): r["last_done"] for r in done_rows if r["task_id"] is not None}
        else:
            last_done_map = {}

        recurring_status = []
        for r in rec_rows:
            d = r["data"]
            interval = d.get("interval_days", 7)
            cutoff = (now - timedelta(days=interval)).date().isoformat()
            last_done = last_done_map.get(r["id"])
            overdue = not last_done or last_done <= cutoff
            days_since = None
            if last_done:
                try:
                    days_since = (now.date() - datetime.fromisoformat(last_done).date()).days
                except Exception:
                    pass
            recurring_status.append({
                "id": r["id"],
                "title": d.get("title"),
                "interval_days": interval,
                "mandatory": d.get("mandatory", False),
                "last_completed": last_done,
                "days_since_last": days_since,
                "overdue": overdue,
            })

        return json.dumps({
            "incomplete_one_time": incomplete,
            "recurring_status": recurring_status,
        })

    @tool
    def save_weekly_review(
        week_start: str,
        week_end: str,
        summary: str,
        wins: str = "[]",
        misses: str = "[]",
        adjustments: str = "[]",
        task_changes: str = "[]",
    ) -> str:
        """Save the completed weekly review.
        week_start / week_end: ISO date strings (YYYY-MM-DD).
        wins, misses, adjustments, task_changes: JSON arrays of strings.
        task_changes should list any specific task modifications proposed."""
        try:
            wins_list = json.loads(wins) if isinstance(wins, str) else wins
            misses_list = json.loads(misses) if isinstance(misses, str) else misses
            adjustments_list = json.loads(adjustments) if isinstance(adjustments, str) else adjustments
            task_changes_list = json.loads(task_changes) if isinstance(task_changes, str) else task_changes
        except json.JSONDecodeError:
            wins_list, misses_list, adjustments_list, task_changes_list = [], [], [], []
        row_id = insert_row("weekly_reviews", {
            "user_id": user_id,
            "week_start": week_start,
            "week_end": week_end,
            "summary": summary,
            "wins": wins_list,
            "misses": misses_list,
            "adjustments": adjustments_list,
            "task_changes": task_changes_list,
        })
        return json.dumps({"success": True, "id": row_id})

    return [get_week_completions, get_week_incomplete, save_weekly_review]
