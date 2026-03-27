from langchain_core.tools import tool
from database import insert_row, get_rows, user_today
import json


def fetch_recent_journal_entries(user_id: int, days: int = 7) -> list[dict]:
    """Plain helper (not a tool). Queries DB for recent journal entries, returns list of entry dicts."""
    rows = get_rows("journal_entries", filters={"user_id": user_id}, limit=days, order_desc=True)
    return [{"id": r["id"], "created_at": r["created_at"], **r["data"]} for r in rows]


def format_journal_for_prompt(entries: list[dict]) -> str:
    """Format a list of journal entry dicts into a readable section for system prompts."""
    if not entries:
        return "## Recent Journal Entries\nNo journal entries yet."
    lines = ["## Recent Journal Entries"]
    for entry in entries[:5]:
        date = entry.get("date", entry.get("created_at", "unknown"))
        what_worked = entry.get("what_worked", "")
        what_discouraged = entry.get("what_discouraged", "")
        line = f"- {date}: Worked → {what_worked}. Discouraged → {what_discouraged}."
        notes = entry.get("notes", "")
        if notes:
            line += f" Notes: {notes}"
        lines.append(line)
    return "\n".join(lines)


def make_journal_tools(user_id: int, context_cache: dict = None):
    """Create journal tools bound to a specific user_id."""
    if context_cache is None:
        context_cache = {}

    @tool
    def save_journal_entry(what_worked: str, what_discouraged: str, notes: str = "") -> str:
        """Save an evening journal entry capturing what worked and what was discouraging today."""
        date = user_today(user_id)
        data = {
            "user_id": user_id,
            "date": date,
            "what_worked": what_worked,
            "what_discouraged": what_discouraged,
            "notes": notes,
        }
        row_id = insert_row("journal_entries", data)
        context_cache["recent_journal_entries"] = fetch_recent_journal_entries(user_id)
        return json.dumps({"success": True, "id": row_id})

    @tool
    def get_journal_entries(days_back: int = 7) -> str:
        """Fetch recent journal entries for the user."""
        rows = get_rows("journal_entries", filters={"user_id": user_id}, limit=days_back, order_desc=True)
        entries = [{"id": r["id"], "created_at": r["created_at"], **r["data"]} for r in rows]
        return json.dumps(entries)

    return [save_journal_entry, get_journal_entries]
