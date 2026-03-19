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
        """Fetch all tasks completed in the past N days, including any metric values logged."""
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
    def save_weekly_review(
        week_start: str,
        week_end: str,
        summary: str,
        wins: str = "[]",
        misses: str = "[]",
        adjustments: str = "[]",
    ) -> str:
        """Save the completed weekly review. week_start and week_end are ISO date strings (YYYY-MM-DD). wins, misses, and adjustments are JSON arrays of strings."""
        try:
            wins_list = json.loads(wins) if isinstance(wins, str) else wins
            misses_list = json.loads(misses) if isinstance(misses, str) else misses
            adjustments_list = json.loads(adjustments) if isinstance(adjustments, str) else adjustments
        except json.JSONDecodeError:
            wins_list, misses_list, adjustments_list = [], [], []
        data = {
            "user_id": user_id,
            "week_start": week_start,
            "week_end": week_end,
            "summary": summary,
            "wins": wins_list,
            "misses": misses_list,
            "adjustments": adjustments_list,
        }
        row_id = insert_row("weekly_reviews", data)
        return json.dumps({"success": True, "id": row_id, "message": "Weekly review saved."})

    return [get_week_completions, save_weekly_review]
