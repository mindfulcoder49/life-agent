import secrets
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText

from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from models import RegisterRequest, LoginRequest
from auth import hash_password, verify_password, create_session, get_current_user, delete_session, get_session_user
from database import insert_row, get_row, update_row, get_db
from config import COOKIE_SECURE, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM, SMTP_FROM_NAME, APP_URL
from logging_service import log_info
from file_logger import logger
import json

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SetPasswordRequest(BaseModel):
    token: str
    password: str


class RequestMagicLinkRequest(BaseModel):
    email: str


def _send_magic_email(to_email: str, magic_url: str):
    body = f"""Hi,

Click the link below to sign in to Life Agent:

{magic_url}

This link expires in 24 hours and can only be used once.

— Life Agent"""
    msg = MIMEText(body)
    msg["Subject"] = "Your Life Agent sign-in link"
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM}>"
    msg["To"] = to_email
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_FROM, [to_email], msg.as_string())


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


@router.get("/magic")
def magic_link(token: str):
    """Validate a magic link token. New users go to password setup; returning users get logged in."""
    user = get_session_user(token)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired link")

    if user.get("needs_password_setup"):
        # Don't burn the token yet — needed for the setup-password step
        return RedirectResponse(url=f"/#/setup-password?token={token}", status_code=302)

    # Returning user: burn token, create session, redirect to welcome
    conn = get_db()
    conn.execute("DELETE FROM sessions WHERE json_extract(data, '$.session_token') = ?", (token,))
    conn.commit()
    conn.close()

    session_token = create_session(user["id"])
    log_info("auth", "magic_login", f"Magic link login for user {user['id']}", user_id=user["id"])

    redirect = RedirectResponse(url="/#/welcome", status_code=302)
    redirect.set_cookie("session_token", session_token, httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=72*3600)
    return redirect


@router.post("/setup-password")
def setup_password(req: SetPasswordRequest, response: Response):
    """Complete first-time setup: validate magic token, set password, create session."""
    user = get_session_user(req.token)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired link")
    if not user.get("needs_password_setup"):
        raise HTTPException(status_code=400, detail="Password already set")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # Save password, clear setup flag
    row = get_row("users", user["id"])
    data = row["data"]
    data["password_hash"] = hash_password(req.password)
    data["needs_password_setup"] = False
    update_row("users", user["id"], data)

    # Burn the magic token
    conn = get_db()
    conn.execute("DELETE FROM sessions WHERE json_extract(data, '$.session_token') = ?", (req.token,))
    conn.commit()
    conn.close()

    session_token = create_session(user["id"])
    response.set_cookie("session_token", session_token, httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=72*3600)
    log_info("auth", "setup_password", f"User {user['id']} set password", user_id=user["id"])

    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user.get("display_name", user["username"]),
        "theme": user.get("theme", "dark"),
    }


@router.post("/request-magic-link")
def request_magic_link(req: RequestMagicLinkRequest):
    """Send a magic sign-in link to an existing user's email."""
    conn = get_db()
    row = conn.execute(
        "SELECT id, data FROM users WHERE json_extract(data, '$.email') = ?",
        (req.email,)
    ).fetchone()
    conn.close()

    # Always return ok — don't leak whether email exists
    if not row:
        return {"ok": True}

    user_id = row["id"]
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    insert_row("sessions", {
        "user_id": user_id,
        "session_token": token,
        "expires_at": expires_at,
        "type": "magic",
    })

    magic_url = f"{APP_URL}/api/auth/magic?token={token}"
    try:
        _send_magic_email(req.email, magic_url)
        logger.info(f"[auth] Magic link sent to {req.email}")
    except Exception as e:
        logger.error(f"[auth] Email failed: {e}. Link: {magic_url}")

    return {"ok": True}
