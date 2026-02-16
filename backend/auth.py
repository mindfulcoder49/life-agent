import secrets
from datetime import datetime, timezone, timedelta
from fastapi import Request, HTTPException
import bcrypt
from database import get_db, insert_row, get_rows, _now
from config import SESSION_EXPIRE_HOURS
import json

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())

def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=SESSION_EXPIRE_HOURS)).isoformat()
    insert_row("sessions", {
        "user_id": user_id,
        "session_token": token,
        "expires_at": expires_at,
    })
    return token

def get_session_user(token: str) -> dict | None:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM sessions WHERE json_extract(data, '$.session_token') = ?",
        (token,)
    ).fetchone()
    if row is None:
        conn.close()
        return None
    session_data = json.loads(row["data"])
    expires_at = datetime.fromisoformat(session_data["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        conn.execute("DELETE FROM sessions WHERE id = ?", (row["id"],))
        conn.commit()
        conn.close()
        return None
    user_row = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (session_data["user_id"],)
    ).fetchone()
    conn.close()
    if user_row is None:
        return None
    user_data = json.loads(user_row["data"])
    user_data["id"] = user_row["id"]
    return user_data

def get_current_user(request: Request) -> dict:
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = get_session_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired")
    return user

def require_admin(request: Request) -> dict:
    user = get_current_user(request)
    if not user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="Admin required")
    return user

def delete_session(token: str):
    conn = get_db()
    conn.execute(
        "DELETE FROM sessions WHERE json_extract(data, '$.session_token') = ?",
        (token,)
    )
    conn.commit()
    conn.close()
