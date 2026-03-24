"""Welcome screen endpoints."""

import json
from fastapi import APIRouter, Request
from openai import OpenAI
from auth import get_current_user
from config import OPENAI_API_KEY
from file_logger import logger

router = APIRouter(prefix="/api/welcome", tags=["welcome"])


@router.get("/suggestions")
def task_suggestions(request: Request, goal: str, energy: int, soreness: int, sickness: int):
    """Generate AI task suggestions for a new user based on their goal and current state."""
    get_current_user(request)  # auth check
    client = OpenAI(api_key=OPENAI_API_KEY)

    prompt = f"""A person just joined a personal planning app. Their primary goal: "{goal}"
Current state: energy {energy}/10, soreness {soreness}/10, sickness {sickness}/10.

Generate 10-12 task suggestions to help them work toward their goal.
Rules:
- If soreness > 6, avoid intense physical training tasks
- If sickness > 5, prioritize rest, hydration, gentle tasks only
- Mix recurring daily habits and one-time setup tasks
- For goals involving fitness/body: include meal logging, workout, sleep tracking, weigh-in
- For goals involving money/career: include habit tracking, learning tasks, action items
- Keep titles short (3-6 words)

Return JSON with key "tasks", each item:
{{
  "title": "short task name",
  "type": "recurring" or "one_time",
  "interval_days": integer (for recurring — 1=daily, 7=weekly),
  "estimated_minutes": integer,
  "cognitive_load": integer 1-10,
  "emoji": "single emoji",
  "description": "one sentence — why this matters for their goal",
  "metric": null or {{"label": "...", "unit": "...", "value_type": "number" or "meal" or "text"}}
}}"""

    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "You are a task planning assistant. Always respond with valid JSON."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        max_tokens=1500,
    )

    try:
        data = json.loads(resp.choices[0].message.content)
        suggestions = data.get("tasks", data.get("suggestions", []))
    except Exception as e:
        logger.error(f"[welcome] suggestions parse error: {e}")
        suggestions = []

    return {"suggestions": suggestions}
