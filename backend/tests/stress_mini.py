"""
Stress test: all agents on gpt-5-mini. Looking for failure modes.

Run with:
  cd backend && venv/bin/python3 tests/stress_mini.py
"""

import os, sys, json, requests, textwrap, re
from datetime import datetime

def _discover_port():
    if os.environ.get("BACKEND_PORT"):
        return int(os.environ["BACKEND_PORT"])
    port_file = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".backend_port"))
    if os.path.exists(port_file):
        return int(open(port_file).read().strip())
    raise RuntimeError("Cannot discover backend port.")

BASE = f"http://localhost:{_discover_port()}/api/admin/test"
H = {"X-Api-Key": "dev-admin-api-key"}

def api(method, path, **kw):
    r = getattr(requests, method)(f"{BASE}{path}", headers=H, timeout=120, **kw)
    r.raise_for_status()
    return r.json()

def chat(msg, sid):
    return api("post", "/chat", json={"message": msg, "session_id": sid})

def reset(sid):
    api("delete", f"/session/{sid}")

def query(sql, params=None):
    return api("post", "/db/query", json={"sql": sql, "params": params or []})["rows"]

def set_all_mini():
    for agent in ["hydrogen", "helium", "lithium", "beryllium", "boron"]:
        api("put", "/config", json={"agent": agent, "model": "gpt-5-mini"})

def reset_models():
    api("delete", "/config")

# ── Display ───────────────────────────────────────────────────────────────────

PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"
NOTE = "[NOTE]"

def wrap(text, width=90, indent="        "):
    return textwrap.fill(text, width=width, initial_indent=indent, subsequent_indent=indent)

def turn(sid, msg, label=""):
    tag = f" ({label})" if label else ""
    print(f"\n  >> {msg!r}{tag}")
    r = chat(msg, sid)
    agent = r["active_agent"]
    resp = r["response"] or ""
    print(f"  [{agent}]")
    print(wrap(resp[:500] + ("..." if len(resp) > 500 else "")))
    return r

def check(cond, label):
    print(f"  {PASS if cond else FAIL} {label}")
    return cond

def note(label):
    print(f"  {NOTE} {label}")

def header(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

# ── Test user setup ───────────────────────────────────────────────────────────

def get_uid():
    return api("get", "/whoami")["id"]

def seed_full_state(uid):
    """Seed goals + tasks + recent state for stress tests that need context."""
    for t in ["life_goals","user_states","one_time_tasks","recurring_tasks","todo_lists"]:
        query(f"DELETE FROM {t} WHERE json_extract(data,'$.user_id')=?", [uid])

    # Goals
    goals = [
        ("Build muscle and strength", "Competing in physique show in 6 months", 9, 7),
        ("Grow personal brand to 10k followers", "Content on LinkedIn + Instagram", 8, 6),
        ("Launch a paid product", "AI system or structured program", 9, 8),
    ]
    for title, desc, pri, stress in goals:
        query("INSERT INTO life_goals (data,created_at,updated_at) VALUES (json_object('user_id',?,'title',?,'description',?,'priority',?,'stress',?,'status','active'),datetime('now'),datetime('now'))",
              [uid, title, desc, pri, stress])

    # Recurring tasks
    rtasks = [
        ("Lift weights", "Strength training", 1, 75, 0),
        ("Log breakfast", "Track morning meal", 1, 10, 1),
        ("Log lunch", "Track midday meal", 1, 10, 1),
        ("Log dinner", "Track evening meal", 1, 10, 1),
        ("Weigh in", "Morning bodyweight in lbs", 1, 3, 1),
        ("Post content", "Ship 1-2 pieces", 1, 30, 0),
        ("Outbound touches", "DMs and comments", 1, 45, 0),
        ("Log sleep", "Hours slept", 1, 3, 1),
        ("Gymnastics skill work", "Skill training session", 1, 45, 0),
    ]
    for title, desc, interval, mins, mandatory in rtasks:
        query("INSERT INTO recurring_tasks (data,created_at,updated_at) VALUES (json_object('user_id',?,'title',?,'description',?,'interval_days',?,'estimated_minutes',?,'cognitive_load',5,'life_goal_ids',json_array(),'active',1,'mandatory',?),datetime('now'),datetime('now'))",
              [uid, title, desc, interval, mins, mandatory])

    # One-time tasks
    otasks = [
        ("Write core thesis", "1-2 sentence public identity statement", "2026-03-22", 8),
        ("Build site MVP", "Basic landing page", "2026-03-25", 7),
        ("Record 10 raw training videos", "B-roll for content pipeline", "2026-03-28", 6),
        ("Set up email capture", "Convert followers to email list", "2026-04-01", 7),
        ("Launch first paid product", "1-3 buyers sufficient", "2026-04-30", 9),
    ]
    for title, desc, deadline, cog in otasks:
        query("INSERT INTO one_time_tasks (data,created_at,updated_at) VALUES (json_object('user_id',?,'title',?,'description',?,'deadline',?,'estimated_minutes',90,'cognitive_load',?,'life_goal_ids',json_array(),'completed',0),datetime('now'),datetime('now'))",
              [uid, title, desc, deadline, cog])

    # Recent state
    query("INSERT INTO user_states (data,created_at,updated_at) VALUES (json_object('user_id',?,'energy',8,'soreness',2,'sickness',1,'notes',''),datetime('now','−1 hour'),datetime('now','−1 hour'))",
          [uid])


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 1: Routing — ambiguous and multi-intent messages
# ═══════════════════════════════════════════════════════════════════════════════

def test_routing_ambiguous(uid):
    header("SCENARIO 1: Routing — ambiguous & multi-intent messages")
    seed_full_state(uid)

    # 1a: User says something that looks like a task add but is actually a check-in request
    sid = "stress-routing-a"
    reset(sid)
    r = turn(sid, "I need to add a task and also check how I'm feeling today", "multi-intent: tasks + state")
    note("Should route to lithium (state check first) or ask to clarify — not silently drop one intent")
    check(r["active_agent"] in ("lithium", "hydrogen"), "Didn't blindly route to beryllium only")

    # 1b: User sends a message that looks like a recommendation request mid-sentence
    sid = "stress-routing-b"
    reset(sid)
    r = turn(sid, "what do you think I should focus on", "vague recommendation ask")
    note("Should offer recommendation or ask for more context — not route to helium/lithium")
    check(r["active_agent"] in ("hydrogen", "lithium"), "Reasonable routing for vague ask")

    # 1c: Explicit beryllium request buried in casual language
    sid = "stress-routing-c"
    reset(sid)
    r = turn(sid, "hey just wanted to let you know I had chicken and rice for lunch", "implicit metric log")
    note("Should route to beryllium to log the meal, not just acknowledge")
    check(r["active_agent"] == "beryllium", "Meal mention routes to beryllium")

    # 1d: Weekly review mention when not eligible
    sid = "stress-routing-d"
    reset(sid)
    r = turn(sid, "can we do a weekly review", "weekly review request")
    note("App is new — should either decline or handle gracefully, not crash or hallucinate")
    check("response" in r and len(r["response"]) > 10, "Got a real response")


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 2: Beryllium — nutrition estimation from vague meal descriptions
# ═══════════════════════════════════════════════════════════════════════════════

def test_beryllium_nutrition(uid):
    header("SCENARIO 2: Beryllium — nutrition estimation quality")
    seed_full_state(uid)

    sid = "stress-bery-nutrition"
    reset(sid)

    # Force into beryllium
    r = turn(sid, "log my meals for today", "enter beryllium")

    r = turn(sid, "breakfast was like a big bowl of oatmeal with peanut butter and a banana and some coffee with oat milk", "vague breakfast")
    note("Should estimate macros — not ask for exact weights, should be confident with rough estimates")
    logged_macros = any(x in r["response"].lower() for x in ["cal", "protein", "carb", "fat", "g"])
    check(logged_macros, "Beryllium included macro estimates in response")

    r = turn(sid, "lunch was a chipotle burrito bowl, steak, extra rice, guac, sour cream, cheese, lettuce, salsa", "complex restaurant meal")
    note("Complex Chipotle order — should estimate ~1000-1300 cal range, high protein")
    logged_macros2 = any(x in r["response"].lower() for x in ["cal", "protein"])
    check(logged_macros2, "Beryllium estimated macros for complex meal")

    r = turn(sid, "dinner I just picked at stuff, had like half a chicken breast and some salad and a couple crackers, wasn't that hungry", "vague low-cal dinner")
    note("Low-cal vague description — should estimate lower (~300-500 cal), not hallucinate a big meal")
    check("response" in r and len(r["response"]) > 20, "Got a response for vague dinner")


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 3: Beryllium — complex task capture without hallucinating fields
# ═══════════════════════════════════════════════════════════════════════════════

def test_beryllium_task_capture(uid):
    header("SCENARIO 3: Beryllium — task capture discipline")
    seed_full_state(uid)

    sid = "stress-bery-tasks"
    reset(sid)

    r = turn(sid, "I need to add some tasks", "enter beryllium")

    # Dump a wall of tasks with mixed types, deadlines, and vague descriptions
    r = turn(sid,
        "ok so I need to: finish the VibeCode event prep by April 7th it's really stressing me out, "
        "also I want to start doing cold exposure every morning that's recurring obviously, "
        "and I have to respond to the 3 brand deal emails sitting in my inbox that's pretty urgent, "
        "oh and I've been meaning to read Outlive by Peter Attia not super urgent just want to do it",
        "wall of mixed tasks")
    note("Should capture ALL 4 tasks with correct types — one-time (VibeCode, emails), recurring (cold exposure), one-time (book)")
    note("Cognitive load: VibeCode should be high (stressed), emails should be moderate-high (urgent)")

    # Check something was actually saved
    import time; time.sleep(1)
    tasks_ot = query("SELECT COUNT(*) as c FROM one_time_tasks WHERE json_extract(data,'$.user_id')=? AND json_extract(data,'$.completed')=0", [uid])
    tasks_rec = query("SELECT COUNT(*) as c FROM recurring_tasks WHERE json_extract(data,'$.user_id')=? AND json_extract(data,'$.active')=1", [uid])
    note(f"DB after dump: {tasks_ot[0]['c']} one-time tasks, {tasks_rec[0]['c']} recurring tasks")

    # Now send a correction — does it handle update vs re-create?
    r = turn(sid, "actually the VibeCode deadline is April 6th not 7th", "correction mid-capture")
    note("Should UPDATE the existing task, not create a duplicate")
    check("update" in r["response"].lower() or "changed" in r["response"].lower() or "april 6" in r["response"].lower(),
          "Acknowledged the correction")


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 4: Hydrogen synthesis — todo list quality with complex context
# ═══════════════════════════════════════════════════════════════════════════════

def test_hydrogen_synthesis(uid):
    header("SCENARIO 4: Hydrogen synthesis — todo list prioritization")
    seed_full_state(uid)

    sid = "stress-hydro-synth"
    reset(sid)

    # Fast-path to recommendation: state is recent, tasks exist
    r = turn(sid, "give me today's plan", "direct recommendation request")
    note("Should skip lithium (state fresh) and offer recommendation directly")
    check(r["active_agent"] in ("hydrogen",), "Hydrogen handles it directly (state fresh)")
    offered = any(w in r["response"].lower() for w in ["recommend","plan","today","priorit","focus"])
    check(offered, "Hydrogen offered a plan / recommendation")

    r = turn(sid, "yes", "accept recommendation")
    note("Should create todo list — check deadline awareness and state awareness")

    import time; time.sleep(1)
    todos = query("SELECT data FROM todo_lists WHERE json_extract(data,'$.user_id')=? ORDER BY id DESC LIMIT 1", [uid])
    if todos:
        tl = json.loads(todos[0]["data"]) if isinstance(todos[0]["data"], str) else todos[0]["data"]
        items = tl.get("items", [])
        note(f"Todo list has {len(items)} AI items, {len(tl.get('mandatory_items',[]))} mandatory, {len(tl.get('overdue_items',[]))} overdue")
        check(len(items) > 0, "Todo list has AI-chosen items")
        # Check the reasoning is substantive
        reasoning = tl.get("reasoning", "")
        check(len(reasoning) > 50, f"Reasoning is substantive ({len(reasoning)} chars)")
    else:
        check(False, "Todo list was created in DB")

    # Now a tricky follow-up: user says something was missed
    r = turn(sid, "you forgot to include my site MVP task", "missed item complaint")
    note("Should add the missed item to the existing list, not create a new one")
    check(r["active_agent"] == "hydrogen", "Hydrogen handles the correction")
    check(any(w in r["response"].lower() for w in ["add","added","updated","include","included"]),
          "Hydrogen acknowledged adding the item")


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 5: Helium — nuanced goal setting under pressure
# ═══════════════════════════════════════════════════════════════════════════════

def test_helium_goals(uid):
    header("SCENARIO 5: Helium — nuanced goal capture")
    # Start fresh — no goals
    for t in ["life_goals","user_states","one_time_tasks","recurring_tasks","todo_lists"]:
        query(f"DELETE FROM {t} WHERE json_extract(data,'$.user_id')=?", [uid])

    sid = "stress-helium-goals"
    reset(sid)

    r = turn(sid, "hello", "enter helium — no goals")
    check(r["active_agent"] == "helium", "Routed to helium with no goals")

    # Give a complex, run-on life situation
    r = turn(sid,
        "ok so my main thing right now is I want to compete in a physique show but I'm also "
        "really stressed about money so I'm trying to build an online business at the same time "
        "and I'm also doing gymnastics and ballet which is kind of a separate passion thing "
        "but it feeds into the content I make. I guess the money thing stresses me out the most "
        "but long term the physique goal is probably #1. I don't know how to rank these.",
        "complex multi-goal life dump")
    note("Should parse 3-4 distinct goals, assign reasonable priority/stress, not lump everything together")
    note("Money/business stress should be HIGH stress even if not #1 priority")

    import time; time.sleep(1)
    goals = query("SELECT COUNT(*) as c FROM life_goals WHERE json_extract(data,'$.user_id')=?", [uid])
    note(f"Goals saved so far: {goals[0]['c']}")
    check(goals[0]["c"] >= 2, "At least 2 distinct goals captured from the dump")


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 6: Context cache discipline — does mini re-call tools unnecessarily?
# ═══════════════════════════════════════════════════════════════════════════════

def test_cache_discipline(uid):
    header("SCENARIO 6: Context cache discipline — unnecessary tool re-calls")
    seed_full_state(uid)

    sid = "stress-cache"
    reset(sid)

    r = turn(sid, "give me today's plan", "initial plan request")
    r = turn(sid, "yes let's do it", "accept plan")
    r = turn(sid, "actually wait, can you add my email capture task to the list too", "add to list")

    note("Check log for repeated get_tasks / get_life_goals calls on 3rd turn")
    log = api("get", "/log/tail?lines=40")["lines"]
    tool_calls_turn3 = [l for l in log if "calling tool" in l and "stress-cache" not in l]
    repeated_get_tasks = sum(1 for l in tool_calls_turn3 if "get_tasks" in l)
    note(f"get_tasks calls in recent log window: {repeated_get_tasks}")
    check(repeated_get_tasks <= 2, "get_tasks not called excessively (mini respects cache instructions)")


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 7: Lithium — weird / incomplete state inputs
# ═══════════════════════════════════════════════════════════════════════════════

def test_lithium_edge_cases(uid):
    header("SCENARIO 7: Lithium — edge case inputs")
    seed_full_state(uid)
    # Remove recent state so lithium triggers
    query("DELETE FROM user_states WHERE json_extract(data,'$.user_id')=?", [uid])

    sid = "stress-lithium-edge"
    reset(sid)

    r = turn(sid, "hello", "trigger lithium")
    check(r["active_agent"] == "lithium", "Lithium active")

    # Give only one value — should ask for the rest, not save with defaults
    r = turn(sid, "energy is about a 7", "incomplete state — only energy")
    note("Should ask for soreness + sickness, NOT save yet with assumed values")
    saved = query("SELECT COUNT(*) as c FROM user_states WHERE json_extract(data,'$.user_id')=?", [uid])
    check(saved[0]["c"] == 0, "Did NOT save state prematurely with only one field")

    # Give nonsense value
    r = turn(sid, "soreness is 0, sickness is like a meh", "nonsense sickness value")
    note("'meh' is not a number — should ask for clarification or map it reasonably, not crash")
    check("response" in r and len(r["response"]) > 5, "Handled non-numeric input without crashing")

    # Give all three
    r = turn(sid, "energy 7, soreness 1, sickness 1", "complete state")
    r = turn(sid, "that's right", "confirm")
    saved2 = query("SELECT COUNT(*) as c FROM user_states WHERE json_extract(data,'$.user_id')=?", [uid])
    check(saved2[0]["c"] >= 1, "State eventually saved after correction flow")


# ═══════════════════════════════════════════════════════════════════════════════
# RUN ALL
# ═══════════════════════════════════════════════════════════════════════════════

def save_timing_report(run_start: datetime):
    """Fetch logs since run_start, parse LLM gaps, write a timing report."""
    lines = api("get", "/log/tail?lines=800")["lines"]

    pat = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[\w+\] life_agent: \[user=\d+[^\]]*\] (.+)$')
    entries = []
    for line in lines:
        m = pat.match(line)
        if m:
            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            if ts >= run_start:
                entries.append((ts, m.group(2)))

    gaps = []
    for i in range(1, len(entries)):
        delta = (entries[i][0] - entries[i-1][0]).seconds
        if delta >= 2:
            gaps.append((delta, entries[i-1][1], entries[i][1]))

    gaps.sort(reverse=True)

    report_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(report_dir, exist_ok=True)
    fname = os.path.join(report_dir, f"timing_{run_start.strftime('%Y%m%d_%H%M%S')}.txt")

    with open(fname, "w") as f:
        f.write(f"Stress test timing report — {run_start.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"{'='*70}\n\n")

        f.write("TOP GAPS (slowest LLM round-trips, descending)\n")
        f.write(f"{'─'*70}\n")
        for delta, before, after in gaps[:30]:
            f.write(f"  {delta:>3}s  waiting after: {before[:70]}\n")
            f.write(f"       resolved by:  {after[:70]}\n\n")

        f.write(f"\nALL GAPS >= 2s ({len(gaps)} total)\n")
        f.write(f"{'─'*70}\n")
        for delta, before, after in gaps:
            f.write(f"  {delta:>3}s  {before[:55]}  →  {after[:40]}\n")

        f.write(f"\n{'='*70}\n")
        f.write(f"Total entries parsed: {len(entries)}\n")

    # Also print a short summary to stdout
    print(f"\n  Timing report saved: {fname}")
    if gaps:
        print(f"  Slowest gaps (top 5):")
        for delta, before, after in gaps[:5]:
            print(f"    {delta:>3}s  {before[:55]}")
            print(f"         → {after[:55]}")


if __name__ == "__main__":
    run_start = datetime.now()

    print("\n" + "█"*70)
    print("  STRESS TEST: All agents on gpt-5-mini")
    print("█"*70)

    set_all_mini()
    print("\n  Models set to gpt-5-mini for all agents.\n")

    uid = get_uid()
    print(f"  Test user id: {uid}\n")

    try:
        test_routing_ambiguous(uid)
        test_beryllium_nutrition(uid)
        test_beryllium_task_capture(uid)
        test_hydrogen_synthesis(uid)
        test_helium_goals(uid)
        test_cache_discipline(uid)
        test_lithium_edge_cases(uid)
    finally:
        reset_models()
        print("\n  Models reset to defaults.\n")

    print("█"*70)
    print("  Stress test complete. Review [FAIL]/[NOTE] lines above.")
    print("█"*70 + "\n")

    save_timing_report(run_start)
