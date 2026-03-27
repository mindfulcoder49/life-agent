"""Discord OAuth2 + bot management endpoints.

GET  /api/discord/auth         — return OAuth authorization URL (authenticated)
GET  /api/discord/callback     — OAuth callback, stores discord_user_id on user record
DELETE /api/discord/disconnect — remove Discord connection for current user
POST /api/discord/tick         — called by GitHub Actions cron, sends due messages
POST /api/discord/schedule     — queue a proactive ping (authenticated)
"""

import hashlib
import hmac as _hmac
import json
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import RedirectResponse

from auth import get_current_user
from config import (
    ADMIN_API_KEY, APP_URL,
    DISCORD_BOT_TOKEN, DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET,
    SECRET_KEY,
)
from database import get_db, get_row, insert_row, update_row
from file_logger import logger

router = APIRouter(prefix="/api/discord", tags=["discord"])

MORNING_GREETING = "Hey, good morning! How are you doing? 👋"
MORNING_HOUR_START = 7
MORNING_HOUR_END = 10

EVENING_GREETING = "Hey, how did today go? 🌙"
EVENING_HOUR_START = 19
EVENING_HOUR_END = 21


# ---------------------------------------------------------------------------
# State helpers (HMAC-signed, no DB required)
# ---------------------------------------------------------------------------

def _make_state(user_id: int) -> str:
    ts = str(int(time.time()))
    msg = f"{user_id}:{ts}"
    sig = _hmac.new(SECRET_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{msg}:{sig}"


def _verify_state(state: str) -> int | None:
    try:
        parts = state.split(":")
        if len(parts) != 3:
            return None
        user_id_str, ts, sig = parts
        msg = f"{user_id_str}:{ts}"
        expected = _hmac.new(SECRET_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()[:16]
        if not _hmac.compare_digest(sig, expected):
            return None
        if time.time() - int(ts) > 600:   # 10-minute window
            return None
        return int(user_id_str)
    except Exception:
        return None


def _redirect_uri() -> str:
    return f"{APP_URL}/api/discord/callback"


# ---------------------------------------------------------------------------
# OAuth endpoints
# ---------------------------------------------------------------------------

@router.get("/auth")
def discord_auth(request: Request):
    """Return the Discord OAuth URL for the logged-in user to visit."""
    user = get_current_user(request)
    if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Discord OAuth not configured on this server")
    state = _make_state(user["id"])
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": "identify",
        "state": state,
    }
    return {"url": "https://discord.com/oauth2/authorize?" + urlencode(params)}


@router.get("/callback")
async def discord_callback(code: str = None, state: str = None, error: str = None):
    """Handle Discord OAuth redirect. Saves discord_user_id and redirects to settings."""
    if error or not code or not state:
        return RedirectResponse("/#/settings?discord=error")

    user_id = _verify_state(state)
    if user_id is None:
        return RedirectResponse("/#/settings?discord=error")

    try:
        async with httpx.AsyncClient() as http:
            token_resp = await http.post(
                "https://discord.com/api/oauth2/token",
                data={
                    "client_id": DISCORD_CLIENT_ID,
                    "client_secret": DISCORD_CLIENT_SECRET,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": _redirect_uri(),
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]

            me_resp = await http.get(
                "https://discord.com/api/users/@me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            me_resp.raise_for_status()
            discord_user = me_resp.json()
    except Exception as e:
        logger.error(f"[discord/oauth] Token exchange failed: {e}")
        return RedirectResponse("/#/settings?discord=error")

    row = get_row("users", user_id)
    if not row:
        return RedirectResponse("/#/settings?discord=error")

    data = row["data"]
    data["discord_user_id"] = discord_user["id"]
    data["discord_username"] = discord_user.get("global_name") or discord_user.get("username", "")
    update_row("users", user_id, data)

    logger.info(f"[discord/oauth] user={user_id} connected as {discord_user.get('username')}")
    return RedirectResponse("/#/settings?discord=connected")


@router.delete("/disconnect")
def discord_disconnect(request: Request):
    """Remove Discord connection for the current user."""
    user = get_current_user(request)
    row = get_row("users", user["id"])
    data = row["data"]
    data.pop("discord_user_id", None)
    data.pop("discord_username", None)
    update_row("users", user["id"], data)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Tick — called by GitHub Actions cron
# ---------------------------------------------------------------------------

def _check_key(key: str):
    if key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/tick")
async def discord_tick(x_api_key: str = Header(...)):
    _check_key(x_api_key)

    from discord_bot import get_bot
    bot = get_bot()
    if bot is None or bot.is_closed():
        logger.info("[discord/tick] Bot not running")
        return {"sent": 0, "bot_running": False}

    from discord_bot import graph_runner as _gr
    DISCORD_SESSION_ID = "discord"

    sent = 0
    for user in _discord_users():
        uid = user["id"]
        did = user["data"]["discord_user_id"]

        if _should_send_morning(uid):
            await bot.send_dm(did, MORNING_GREETING)
            _record_morning_sent(uid)
            sent += 1
            logger.info(f"[discord/tick] Morning greeting → user={uid}")

        if _should_send_evening(uid):
            await bot.send_dm(did, EVENING_GREETING)
            _record_evening_sent(uid)
            if _gr:
                _gr.set_active_agent(uid, DISCORD_SESSION_ID, "carbon")
            sent += 1
            logger.info(f"[discord/tick] Evening greeting → user={uid}")

        for ping in _due_pings(uid):
            msg = ping["data"].get("message") or "Hey, checking in — what are you up to?"
            await bot.send_dm(did, msg)
            ping["data"]["sent"] = True
            update_row("discord_schedules", ping["id"], ping["data"])
            sent += 1
            logger.info(f"[discord/tick] Ping → user={uid}: {msg[:60]}")

    return {"sent": sent, "bot_running": True}


# ---------------------------------------------------------------------------
# Schedule a proactive ping
# ---------------------------------------------------------------------------

@router.post("/schedule")
def schedule_ping(request: Request, minutes: int, message: str = "Hey, checking in — what are you up to?"):
    user = get_current_user(request)
    send_at = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
    insert_row("discord_schedules", {
        "user_id": user["id"],
        "type": "ping",
        "message": message,
        "send_at": send_at,
        "sent": False,
    })
    return {"ok": True, "send_at": send_at}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _discord_users() -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, data FROM users WHERE json_extract(data, '$.discord_user_id') IS NOT NULL"
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = {"id": r["id"]}
        try:
            d["data"] = json.loads(r["data"])
        except Exception:
            d["data"] = {}
        result.append(d)
    return result


def _user_local_hour(user_id: int) -> int:
    conn = get_db()
    row = conn.execute("SELECT data FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    tz_str = "UTC"
    if row:
        try:
            tz_str = json.loads(row["data"]).get("timezone") or "UTC"
        except Exception:
            pass
    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).hour


def _should_send_morning(user_id: int) -> bool:
    if not (MORNING_HOUR_START <= _user_local_hour(user_id) < MORNING_HOUR_END):
        return False
    today = datetime.now(timezone.utc).date().isoformat()
    conn = get_db()
    row = conn.execute("""
        SELECT id FROM discord_schedules
        WHERE json_extract(data, '$.user_id') = ?
          AND json_extract(data, '$.type') = 'morning'
          AND json_extract(data, '$.sent_date') = ?
    """, (user_id, today)).fetchone()
    conn.close()
    return row is None


def _record_morning_sent(user_id: int):
    insert_row("discord_schedules", {
        "user_id": user_id,
        "type": "morning",
        "sent_date": datetime.now(timezone.utc).date().isoformat(),
        "sent": True,
    })


def _should_send_evening(user_id: int) -> bool:
    if not (EVENING_HOUR_START <= _user_local_hour(user_id) < EVENING_HOUR_END):
        return False
    today = datetime.now(timezone.utc).date().isoformat()
    conn = get_db()
    row = conn.execute("""
        SELECT id FROM discord_schedules
        WHERE json_extract(data, '$.user_id') = ?
          AND json_extract(data, '$.type') = 'evening'
          AND json_extract(data, '$.sent_date') = ?
    """, (user_id, today)).fetchone()
    conn.close()
    return row is None


def _record_evening_sent(user_id: int):
    insert_row("discord_schedules", {
        "user_id": user_id,
        "type": "evening",
        "sent_date": datetime.now(timezone.utc).date().isoformat(),
        "sent": True,
    })


def _due_pings(user_id: int) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM discord_schedules
        WHERE json_extract(data, '$.user_id') = ?
          AND json_extract(data, '$.type') = 'ping'
          AND json_extract(data, '$.sent') = 0
          AND json_extract(data, '$.send_at') <= ?
        ORDER BY json_extract(data, '$.send_at') ASC
        LIMIT 20
    """, (user_id, now)).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["data"] = json.loads(d["data"])
        except Exception:
            pass
        result.append(d)
    return result
