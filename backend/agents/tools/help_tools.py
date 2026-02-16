from langchain_core.tools import tool
from database import get_rows
import json


def make_help_tools():
    """Create help article tools (not user-specific)."""

    @tool
    def get_help_articles() -> str:
        """Get all help articles available in the system."""
        rows = get_rows("help_articles", limit=100, order_desc=False)
        articles = [{"id": r["id"], **r["data"]} for r in rows]
        return json.dumps(articles)

    return [get_help_articles]
