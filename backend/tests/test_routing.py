"""
Flow test: verify Hydrogen routes correctly after Lithium state check
when tasks already exist in the system.

Run with:
  cd backend && venv/bin/python3 tests/test_routing.py
"""

import requests
import json
import sys

def _discover_port():
    import os
    # Env var takes precedence (useful for CI)
    if os.environ.get("BACKEND_PORT"):
        return int(os.environ["BACKEND_PORT"])
    # Fall back to .backend_port file written by dev.sh
    port_file = os.path.join(os.path.dirname(__file__), "..", "..", ".backend_port")
    port_file = os.path.normpath(port_file)
    if os.path.exists(port_file):
        return int(open(port_file).read().strip())
    raise RuntimeError("Cannot discover backend port. Set BACKEND_PORT env var or run via dev.sh.")

BASE = f"http://localhost:{_discover_port()}/api/admin/test"
HEADERS = {"X-Api-Key": "dev-admin-api-key"}
SESSION = "test-routing-001"


def chat(message):
    r = requests.post(f"{BASE}/chat", headers=HEADERS,
                      json={"message": message, "session_id": SESSION})
    r.raise_for_status()
    return r.json()


def reset():
    r = requests.delete(f"{BASE}/session/{SESSION}", headers=HEADERS)
    r.raise_for_status()


def db(table, user_scoped=True, limit=200):
    r = requests.get(f"{BASE}/db/{table}", headers=HEADERS,
                     params={"user_scoped": user_scoped, "limit": limit})
    r.raise_for_status()
    return r.json()["items"]


def query(sql, params=None):
    r = requests.post(f"{BASE}/db/query", headers=HEADERS,
                      json={"sql": sql, "params": params or []})
    r.raise_for_status()
    return r.json()["rows"]


def log_tail(n=30):
    r = requests.get(f"{BASE}/log/tail", headers=HEADERS, params={"lines": n})
    r.raise_for_status()
    return r.json()["lines"]


def check(condition, label):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}")
    if not condition:
        print("\n--- Last 20 log lines ---")
        for line in log_tail(20):
            print(" ", line)
        sys.exit(1)


# ── Setup ─────────────────────────────────────────────────────────────────────

print("\n=== Test: Hydrogen routing after Lithium state check ===\n")

print("Resetting session and wiping test user data...")
reset()

# Get test user ID
test_user_rows = query(
    "SELECT id FROM users WHERE json_extract(data, '$.username') = ?",
    ["__test__"]
)
assert test_user_rows, "Test user not found in DB"
uid = test_user_rows[0]["id"]
print(f"  Test user id: {uid}")

# Wipe any leftover data from a prior run
for table in ["life_goals", "user_states", "one_time_tasks", "recurring_tasks", "todo_lists"]:
    query(f"DELETE FROM {table} WHERE json_extract(data, '$.user_id') = ?", [uid])
print("  Test user data wiped")

# Seed one life goal
query(
    "INSERT INTO life_goals (data, created_at, updated_at) VALUES (json_object('user_id',?,'title',?,'description',?,'priority',8,'stress',5,'status','active'), datetime('now'), datetime('now'))",
    [uid, "Get stronger", "Build muscle and strength over time"]
)

# Seed one recurring task
query(
    "INSERT INTO recurring_tasks (data, created_at, updated_at) VALUES (json_object('user_id',?,'title',?,'description',?,'interval_days',1,'estimated_minutes',60,'cognitive_load',5,'life_goal_ids',json_array(),'active',1,'mandatory',0), datetime('now'), datetime('now'))",
    [uid, "Lift weights", "Daily strength training session"]
)

goals = db("life_goals")
tasks = db("recurring_tasks")
print(f"  Seeded: {len(goals)} goal(s), {len(tasks)} recurring task(s)")
check(len(goals) == 1, "Life goal seeded")
check(len(tasks) == 1, "Recurring task seeded")

# ── Turn 1: hello — goals exist, no recent state → should route to Lithium ───

print("\nTurn 1: 'hello'")
r1 = chat("hello")
print(f"  active_agent: {r1['active_agent']}")
print(f"  response: {r1['response'][:140].strip()}...")

check(r1["active_agent"] == "lithium", "Goals exist, no recent state → Hydrogen routes to Lithium")

# ── Turn 2: Provide state numbers ────────────────────────────────────────────

print("\nTurn 2: give state")
r2 = chat("energy 8, soreness 2, sickness 1")
print(f"  active_agent: {r2['active_agent']}")
print(f"  response: {r2['response'][:140].strip()}...")

check(r2["active_agent"] == "lithium", "Lithium stays active while collecting/confirming state")

# ── Turn 3: Confirm ───────────────────────────────────────────────────────────

print("\nTurn 3: confirm (no changes)")
r3 = chat("no, that looks right")
print(f"  active_agent: {r3['active_agent']}")
print(f"  response: {r3['response'][:200].strip()}...")

# State should be saved
states = db("user_states")
check(len(states) > 0, "User state record written to DB")
if states:
    s = states[0]["data"]
    check(s.get("energy") == 8, f"Energy saved correctly (got {s.get('energy')})")

# Hydrogen runs after Lithium hands off — it knows tasks exist and should
# offer a recommendation, NOT route to Beryllium for task setup
response_lower = r3["response"].lower()

routed_for_task_setup = (
    r3["active_agent"] == "beryllium" and
    any(w in response_lower for w in ["add", "capture", "what tasks", "tell me about", "what's on your plate"])
)
check(not routed_for_task_setup, "Hydrogen did NOT wrongly route to Beryllium for task setup")

offered_recommendation = any(w in response_lower for w in [
    "recommend", "plan", "today", "suggestion", "shall i", "want me to", "daily"
])
check(offered_recommendation, "Hydrogen offered a daily recommendation (tasks exist, state fresh)")

# ── Turn 4: Accept recommendation → todo list created ─────────────────────────

print("\nTurn 4: accept recommendation")
r4 = chat("yes")
print(f"  active_agent: {r4['active_agent']}")
print(f"  response: {r4['response'][:200].strip()}...")

todo_lists = db("todo_lists")
check(len(todo_lists) > 0, "Todo list created in DB after recommendation accepted")
if todo_lists:
    tl = todo_lists[0]["data"]
    check("items" in tl, "Todo list has items section")
    print(f"  Todo list: {len(tl.get('items', []))} AI items, "
          f"{len(tl.get('mandatory_items', []))} mandatory, "
          f"{len(tl.get('overdue_items', []))} overdue")

# ── Done ─────────────────────────────────────────────────────────────────────

print("\n=== All checks passed ===\n")
