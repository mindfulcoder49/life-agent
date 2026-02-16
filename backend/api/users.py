from fastapi import APIRouter, Request
from models import ApiKeyUpdate, DataUpdate
from auth import get_current_user
from database import get_row, update_row

router = APIRouter(prefix="/api/users", tags=["users"])

@router.get("/me")
def get_profile(request: Request):
    user = get_current_user(request)
    row = get_row("users", user["id"])
    data = row["data"]
    return {
        "id": user["id"],
        "username": data["username"],
        "display_name": data.get("display_name", data["username"]),
        "theme": data.get("theme", "dark"),
        "settings": data.get("settings", {}),
        "has_api_key": bool(data.get("openai_api_key")),
    }

@router.put("/me")
def update_profile(request: Request, body: DataUpdate):
    user = get_current_user(request)
    row = get_row("users", user["id"])
    data = row["data"]
    allowed = {"display_name", "theme", "settings"}
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
