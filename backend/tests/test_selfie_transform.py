"""
Test: selfie → aspirational image via OpenAI.

Usage:
  cd backend
  venv/bin/python3 tests/test_selfie_transform.py <selfie_path> "<goal>"

Example:
  venv/bin/python3 tests/test_selfie_transform.py ~/selfie.jpg "compete in a physique show in 6 months"

Output:
  tests/selfie_output/aspirational_<timestamp>.png  — the generated image
  tests/selfie_output/description_<timestamp>.txt   — the person description used
"""

import sys
import os
import base64
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import OPENAI_API_KEY
from openai import OpenAI

OUTPUT_DIR = Path(__file__).parent / "selfie_output"
OUTPUT_DIR.mkdir(exist_ok=True)


def load_image_b64(path: str) -> tuple[str, str]:
    """Return (base64_data, media_type)."""
    ext = Path(path).suffix.lower()
    media_type = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif",
    }.get(ext, "image/jpeg")
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode(), media_type


def build_visual_prompt(client: OpenAI, goal: str) -> str:
    """Ask GPT to describe what success looks like visually for this specific goal."""
    resp = client.chat.completions.create(
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
    return resp.choices[0].message.content.strip()


def transform_with_gpt_image_1(client: OpenAI, selfie_path: str, goal: str) -> bytes:
    """Use gpt-image-1 edit endpoint — pass the actual selfie so it preserves the face."""
    print("  Using gpt-image-1.5 (images.edit) with selfie as reference...")
    visual = build_visual_prompt(client, goal)
    print(f"\n  Visual description: {visual}")
    prompt = (
        f"Transform this person's photo to show them having fully achieved their goal. "
        f"Keep their face, skin tone, and identity fully recognizable. "
        f"{visual} "
        "Cinematic studio portrait lighting. Photorealistic."
    )
    print(f"\n  Prompt: {prompt}\n")
    with open(selfie_path, "rb") as f:
        resp = client.images.edit(
            model="gpt-image-1.5",
            image=f,
            prompt=prompt,
            size="1024x1024",
            n=1,
        )
    return base64.b64decode(resp.data[0].b64_json)



def run(selfie_path: str, goal: str):
    client = OpenAI(api_key=OPENAI_API_KEY)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"\n  Selfie:  {selfie_path}")
    print(f"  Goal:    {goal}\n")

    image_bytes = transform_with_gpt_image_1(client, selfie_path, goal)
    method = "gpt-image-1"

    out_path = OUTPUT_DIR / f"aspirational_{ts}.png"
    out_path.write_bytes(image_bytes)
    print(f"\n  [{method}] Done.")
    print(f"  Output: {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    run(sys.argv[1], " ".join(sys.argv[2:]))
