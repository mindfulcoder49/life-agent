from fastapi import APIRouter, Request
from models import ApiKeyUpdate, DataUpdate
from auth import get_current_user
from database import get_row, update_row, count_rows

router = APIRouter(prefix="/api/users", tags=["users"])

@router.get("/me")
def get_profile(request: Request):
    user = get_current_user(request)
    row = get_row("users", user["id"])
    data = row["data"]
    is_new = count_rows("user_states", filters={"user_id": user["id"]}) == 0
    return {
        "id": user["id"],
        "username": data["username"],
        "display_name": data.get("display_name", data["username"]),
        "theme": data.get("theme", "dark"),
        "settings": data.get("settings", {}),
        "has_api_key": bool(data.get("openai_api_key")),
        "timezone": data.get("timezone", "UTC"),
        "aspirational_image_b64": data.get("aspirational_image_b64"),
        "is_new": is_new,
        "discord_connected": bool(data.get("discord_user_id")),
        "discord_username": data.get("discord_username"),
    }

@router.put("/me")
def update_profile(request: Request, body: DataUpdate):
    user = get_current_user(request)
    row = get_row("users", user["id"])
    data = row["data"]
    allowed = {"display_name", "theme", "settings", "timezone"}
    for key in allowed:
        if key in body.data:
            data[key] = body.data[key]
    update_row("users", user["id"], data)
    return {"ok": True}

@router.put("/me/api-key")
def update_api_key(request: Request, body: ApiKeyUpdate):
    user = get_current_user(request)
    row = get_row("users", user["id"])
    data = row["data"]
    data["openai_api_key"] = body.openai_api_key
    update_row("users", user["id"], data)
    return {"ok": True, "has_api_key": bool(body.openai_api_key)}
