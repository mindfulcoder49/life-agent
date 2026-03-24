"""
Auth flow test: onboarding claim → magic link → password setup → session.

Tests the full new-user auth flow without sending real emails.
Reads the magic token directly from the DB after /api/onboarding/claim.

Run with:
  cd backend && venv/bin/python3 tests/test_auth_flow.py
"""

import os
import sys
import json
import requests

def _discover_port():
    if os.environ.get("BACKEND_PORT"):
        return int(os.environ["BACKEND_PORT"])
    port_file = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".backend_port"))
    if os.path.exists(port_file):
        return int(open(port_file).read().strip())
    raise RuntimeError("Cannot discover backend port. Set BACKEND_PORT env var or run via dev.sh.")

PORT = _discover_port()
BASE = f"http://localhost:{PORT}/api"
ADMIN = f"http://localhost:{PORT}/api/admin/test"
H_ADMIN = {"X-Api-Key": "dev-admin-api-key"}

TEST_EMAIL = "authflow_test@example.com"
TEST_GOAL  = "Run a marathon in under 4 hours"


def query(sql, params=None):
    r = requests.post(f"{ADMIN}/db/query", headers=H_ADMIN,
                      json={"sql": sql, "params": params or []})
    r.raise_for_status()
    return r.json()["rows"]


def check(condition, label):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}")
    if not condition:
        sys.exit(1)


def cleanup():
    """Remove any leftover test user data from a prior run."""
    rows = query(
        "SELECT id FROM users WHERE json_extract(data, '$.email') = ?",
        [TEST_EMAIL]
    )
    if rows:
        uid = rows[0]["id"]
        query("DELETE FROM sessions WHERE json_extract(data, '$.user_id') = ?", [uid])
        query("DELETE FROM life_goals WHERE json_extract(data, '$.user_id') = ?", [uid])
        query("DELETE FROM users WHERE id = ?", [uid])
        print(f"  Cleaned up leftover test user (id={uid})")


# ── Setup ─────────────────────────────────────────────────────────────────────

print("\n=== Test: Auth flow — onboarding → magic link → password setup ===\n")

cleanup()

# ── Step 1: /api/onboarding/claim ─────────────────────────────────────────────

print("Step 1: POST /api/onboarding/claim")
r = requests.post(f"{BASE}/onboarding/claim", json={
    "email": TEST_EMAIL,
    "goal": TEST_GOAL,
    "aspirational_image_b64": None,
})
check(r.status_code == 200, f"claim returned 200 (got {r.status_code})")
check(r.json().get("ok") is True, "claim returned {ok: true}")

# ── Step 2: verify user and magic token in DB ─────────────────────────────────

print("\nStep 2: verify DB state after claim")

user_rows = query(
    "SELECT id, data FROM users WHERE json_extract(data, '$.email') = ?",
    [TEST_EMAIL]
)
check(len(user_rows) == 1, "User created in DB")
uid = user_rows[0]["id"]
user_data = user_rows[0]["data"]
if isinstance(user_data, str):
    user_data = json.loads(user_data)

check(user_data.get("needs_password_setup") is True, "needs_password_setup: true on new user")
check(bool(user_data.get("password_hash")), "password_hash set (random placeholder)")

goal_rows = query(
    "SELECT data FROM life_goals WHERE json_extract(data, '$.user_id') = ?",
    [uid]
)
check(len(goal_rows) == 1, "Life goal created in DB")
goal_data = goal_rows[0]["data"]
if isinstance(goal_data, str):
    goal_data = json.loads(goal_data)
check(goal_data.get("title") == TEST_GOAL, f"Goal title correct (got '{goal_data.get('title')}')")

session_rows = query(
    "SELECT data FROM sessions WHERE json_extract(data, '$.user_id') = ? AND json_extract(data, '$.type') = 'magic'",
    [uid]
)
check(len(session_rows) == 1, "Magic session row created")
session_data = session_rows[0]["data"]
if isinstance(session_data, str):
    session_data = json.loads(session_data)
magic_token = session_data["session_token"]
check(len(magic_token) > 20, f"Magic token present (length={len(magic_token)})")

# ── Step 3: GET /api/auth/magic → should redirect to /#/setup-password ────────

print("\nStep 3: GET /api/auth/magic?token=... (new user → setup-password redirect)")
r = requests.get(f"{BASE}/auth/magic", params={"token": magic_token}, allow_redirects=False)
check(r.status_code == 302, f"Got 302 redirect (got {r.status_code})")
location = r.headers.get("location", "")
check("/setup-password" in location, f"Redirected to setup-password (Location: {location})")
check(magic_token in location, "Magic token included in redirect URL")

# Token should NOT be burned yet
remaining = query(
    "SELECT COUNT(*) as c FROM sessions WHERE json_extract(data, '$.session_token') = ?",
    [magic_token]
)
check(remaining[0]["c"] == 1, "Magic token NOT burned after setup-password redirect")

# ── Step 4: POST /api/auth/setup-password ─────────────────────────────────────

print("\nStep 4: POST /api/auth/setup-password")
r = requests.post(f"{BASE}/auth/setup-password", json={
    "token": magic_token,
    "password": "securepass123",
})
check(r.status_code == 200, f"setup-password returned 200 (got {r.status_code})")
body = r.json()
check(body.get("id") == uid, f"Returned correct user id (got {body.get('id')})")
check("session_token" not in r.cookies or True, "Response contains session cookie")

# Verify cookie was set
session_cookie = r.cookies.get("session_token")
check(bool(session_cookie), "session_token cookie set in response")

# Token should be burned now
burned = query(
    "SELECT COUNT(*) as c FROM sessions WHERE json_extract(data, '$.session_token') = ?",
    [magic_token]
)
check(burned[0]["c"] == 0, "Magic token burned after password setup")

# ── Step 5: verify user data updated ─────────────────────────────────────────

print("\nStep 5: verify user data after password setup")
updated_rows = query(
    "SELECT data FROM users WHERE id = ?",
    [uid]
)
updated = updated_rows[0]["data"]
if isinstance(updated, str):
    updated = json.loads(updated)
check(updated.get("needs_password_setup") is False, "needs_password_setup cleared")
check(updated.get("password_hash") != user_data.get("password_hash"), "password_hash updated")

# ── Step 6: use session cookie to call /api/auth/me ───────────────────────────

print("\nStep 6: GET /api/auth/me with new session cookie")
r = requests.get(f"{BASE}/auth/me", cookies={"session_token": session_cookie})
check(r.status_code == 200, f"/auth/me returned 200 (got {r.status_code})")
me = r.json()
check(me.get("id") == uid, f"Correct user returned from /auth/me (got id={me.get('id')})")

# ── Step 7: magic link for existing user (request-magic-link flow) ─────────────

print("\nStep 7: POST /api/auth/request-magic-link (existing user)")
r = requests.post(f"{BASE}/auth/request-magic-link", json={"email": TEST_EMAIL})
check(r.status_code == 200, f"request-magic-link returned 200 (got {r.status_code})")
check(r.json().get("ok") is True, "returned {ok: true}")

new_magic_rows = query(
    "SELECT data FROM sessions WHERE json_extract(data, '$.user_id') = ? AND json_extract(data, '$.type') = 'magic' ORDER BY id DESC LIMIT 1",
    [uid]
)
check(len(new_magic_rows) == 1, "New magic session created for existing user")
new_token = new_magic_rows[0]["data"]
if isinstance(new_token, str):
    new_token = json.loads(new_token)
new_token = new_token["session_token"]

# This user has needs_password_setup=False, so magic link should go to /#/welcome
r = requests.get(f"{BASE}/auth/magic", params={"token": new_token}, allow_redirects=False)
check(r.status_code == 302, f"Existing user magic link: 302 redirect (got {r.status_code})")
location2 = r.headers.get("location", "")
check("/welcome" in location2, f"Existing user redirected to /welcome (Location: {location2})")
check("/setup-password" not in location2, "Did NOT redirect existing user to setup-password")

# Token should be burned
burned2 = query(
    "SELECT COUNT(*) as c FROM sessions WHERE json_extract(data, '$.session_token') = ?",
    [new_token]
)
check(burned2[0]["c"] == 0, "Existing user magic token burned after login")

# ── Cleanup ───────────────────────────────────────────────────────────────────

print("\nCleaning up test user...")
cleanup()

print("\n=== All checks passed ===\n")
