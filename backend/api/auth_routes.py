from fastapi import APIRouter, Request, Response, HTTPException
from models import RegisterRequest, LoginRequest
from auth import hash_password, verify_password, create_session, get_current_user, delete_session
from database import insert_row, get_db
from config import COOKIE_SECURE
from logging_service import log_info
import json

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/register")
def register(req: RegisterRequest, response: Response):
    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM users WHERE json_extract(data, '$.username') = ?",
        (req.username,)
    ).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already taken")
    conn.close()

    user_data = {
        "username": req.username,
        "password_hash": hash_password(req.password),
        "display_name": req.display_name or req.username,
        "is_admin": False,
        "openai_api_key": None,
        "theme": "dark",
        "settings": {},
    }
    user_id = insert_row("users", user_data)
    token = create_session(user_id)
    response.set_cookie("session_token", token, httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=72*3600)
    log_info("auth", "register", f"User {req.username} registered", user_id=user_id)
    return {"id": user_id, "username": req.username, "display_name": user_data["display_name"]}

@router.post("/login")
def login(req: LoginRequest, response: Response):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE json_extract(data, '$.username') = ?",
        (req.username,)
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user_data = json.loads(row["data"])
    if not verify_password(req.password, user_data["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_session(row["id"])
    response.set_cookie("session_token", token, httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=72*3600)
    log_info("auth", "login", f"User {req.username} logged in", user_id=row["id"])
    return {
        "id": row["id"],
        "username": user_data["username"],
        "display_name": user_data.get("display_name", user_data["username"]),
        "is_admin": user_data.get("is_admin", False),
        "theme": user_data.get("theme", "dark"),
    }

@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        delete_session(token)
    response.delete_cookie("session_token")
    return {"ok": True}

@router.get("/me")
def me(request: Request):
    user = get_current_user(request)
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user.get("display_name", user["username"]),
        "is_admin": user.get("is_admin", False),
        "theme": user.get("theme", "dark"),
        "settings": user.get("settings", {}),
    }
