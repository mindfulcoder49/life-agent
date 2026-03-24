"""Onboarding flow — no auth required.

Endpoints:
  POST /api/onboarding/chat      — Goal extraction via GPT
  POST /api/onboarding/transform — Selfie → aspirational image
  POST /api/onboarding/claim     — Email capture, user creation, magic link
"""

import io
import secrets
import smtplib
import tempfile
import os
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText

from fastapi import APIRouter, UploadFile, File, Form
from pydantic import BaseModel
from openai import OpenAI

from auth import hash_password
from database import insert_row, get_row, update_row, get_db
from config import (
    OPENAI_API_KEY, COOKIE_SECURE,
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM, SMTP_FROM_NAME,
    APP_URL,
)
from file_logger import logger

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

ONBOARDING_SYSTEM = """You are a warm onboarding assistant for Life Agent, an AI-powered personal planning app.

The user just told you their primary goal. Your job:
1. Confirm you understood it (1 sentence, warm but brief)
2. Tell them you'll show them what achieving it looks like — ask them to upload a selfie (1 sentence)

Keep it to 2 sentences total. No questions. No lists. No filler.

After your response, on a new line output:
GOAL: <the goal restated clearly and concisely in plain language>"""


class ChatRequest(BaseModel):
    message: str


class ClaimRequest(BaseModel):
    email: str
    goal: str
    aspirational_image_b64: str | None = None


@router.post("/chat")
async def onboarding_chat(req: ChatRequest):
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": ONBOARDING_SYSTEM},
            {"role": "user", "content": req.message},
        ],
        max_tokens=200,
    )
    full = resp.choices[0].message.content.strip()

    goal = None
    response_text = full
    if "\nGOAL:" in full:
        parts = full.rsplit("\nGOAL:", 1)
        response_text = parts[0].strip()
        goal = parts[1].strip()

    return {"response": response_text, "goal": goal or req.message}


@router.post("/transform")
async def onboarding_transform(
    goal: str = Form(...),
    image: UploadFile = File(...),
):
    client = OpenAI(api_key=OPENAI_API_KEY)

    # Ask GPT to describe what success looks like visually for this goal
    visual_resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{
            "role": "user",
            "content": (
                f"A person has achieved this goal: '{goal}'. "
                "Write a short 2-3 sentence visual description of how they look in a portrait photo — "
                "their appearance, expression, style, and setting. "
                "Be concrete and specific to the goal. Do not mention the goal text directly. "
                "Output only the visual description, nothing else."
            ),
        }],
        max_tokens=120,
    )
    visual = visual_resp.choices[0].message.content.strip()

    prompt = (
        "Transform this person's photo to show them having fully achieved their goal. "
        "Keep their face, skin tone, and identity fully recognizable. "
        f"{visual} "
        "Cinematic studio portrait lighting. Photorealistic."
    )

    image_bytes = await image.read()
    ext = os.path.splitext(image.filename or "selfie.jpg")[1] or ".jpg"

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            edit_resp = client.images.edit(
                model="gpt-image-1.5",
                image=f,
                prompt=prompt,
                size="1024x1024",
                n=1,
            )
    finally:
        os.unlink(tmp_path)

    return {"image_b64": edit_resp.data[0].b64_json}


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


@router.post("/claim")
async def onboarding_claim(req: ClaimRequest):
    conn = get_db()

    existing = conn.execute(
        "SELECT id FROM users WHERE json_extract(data, '$.email') = ?",
        (req.email,)
    ).fetchone()

    if existing:
        user_id = existing["id"]
    else:
        username_base = req.email.split("@")[0].lower().replace(".", "_").replace("+", "_")
        username = username_base
        suffix = 1
        while conn.execute(
            "SELECT id FROM users WHERE json_extract(data, '$.username') = ?", (username,)
        ).fetchone():
            username = f"{username_base}{suffix}"
            suffix += 1

        user_data = {
            "username": username,
            "email": req.email,
            "password_hash": hash_password(secrets.token_urlsafe(16)),
            "display_name": username_base.replace("_", " ").title(),
            "is_admin": False,
            "openai_api_key": None,
            "theme": "dark",
            "settings": {},
            "timezone": "UTC",
            "needs_password_setup": True,
        }
        user_id = insert_row("users", user_data)

        insert_row("life_goals", {
            "user_id": user_id,
            "title": req.goal,
            "description": "",
            "priority": 8,
            "stress": 7,
            "status": "active",
        })

    conn.close()

    if req.aspirational_image_b64:
        row = get_row("users", user_id)
        data = row["data"]
        data["aspirational_image_b64"] = req.aspirational_image_b64
        update_row("users", user_id, data)

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
        logger.info(f"[onboarding] Magic link sent to {req.email}")
    except Exception as e:
        logger.error(f"[onboarding] Email failed: {e}. Link: {magic_url}")

    return {"ok": True}
