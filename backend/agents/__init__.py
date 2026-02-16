from database import get_row
import config


def get_api_key(user_id: int) -> str:
    """Resolve the OpenAI API key: prefer user's own key, fall back to system key."""
    row = get_row("users", user_id)
    if row and row["data"].get("openai_api_key"):
        return row["data"]["openai_api_key"]
    return config.OPENAI_API_KEY
