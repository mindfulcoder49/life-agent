"""
Interactive test console for stress-testing agent quality.

Usage:
  cd backend
  venv/bin/python3 tests/interactive.py [session_id]

Commands (prefix with /):
  /model <agent> <model>   — override model for an agent (e.g. /model hydrogen gpt-5-mini)
  /model reset             — reset all agents to defaults
  /model status            — show current model config
  /reset                   — wipe current session and start fresh
  /session <id>            — switch to a different session
  /db <table>              — dump test user's rows from a table
  /log [n]                 — tail last n lines of server log (default 30)
  /agent                   — show current active agent
  /quit                    — exit
"""

import os
import sys
import json
import requests

# ── Port discovery ────────────────────────────────────────────────────────────

def _discover_port():
    if os.environ.get("BACKEND_PORT"):
        return int(os.environ["BACKEND_PORT"])
    port_file = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".backend_port"))
    if os.path.exists(port_file):
        return int(open(port_file).read().strip())
    raise RuntimeError("Cannot discover backend port. Set BACKEND_PORT env var or run via dev.sh.")

BASE = f"http://localhost:{_discover_port()}/api/admin/test"
HEADERS = {"X-Api-Key": "dev-admin-api-key"}

# ── API helpers ───────────────────────────────────────────────────────────────

def chat(message, session_id):
    r = requests.post(f"{BASE}/chat", headers=HEADERS,
                      json={"message": message, "session_id": session_id}, timeout=120)
    r.raise_for_status()
    return r.json()

def reset_session(session_id):
    r = requests.delete(f"{BASE}/session/{session_id}", headers=HEADERS)
    r.raise_for_status()

def get_config():
    r = requests.get(f"{BASE}/config", headers=HEADERS)
    r.raise_for_status()
    return r.json()

def set_model(agent, model):
    r = requests.put(f"{BASE}/config", headers=HEADERS,
                     json={"agent": agent, "model": model})
    r.raise_for_status()
    return r.json()

def reset_model(agent=None):
    if agent:
        r = requests.delete(f"{BASE}/config/{agent}", headers=HEADERS)
    else:
        r = requests.delete(f"{BASE}/config", headers=HEADERS)
    r.raise_for_status()
    return r.json()

def get_db(table):
    r = requests.get(f"{BASE}/db/{table}", headers=HEADERS, params={"limit": 50})
    r.raise_for_status()
    return r.json()

def get_log(n=30):
    r = requests.get(f"{BASE}/log/tail", headers=HEADERS, params={"lines": n})
    r.raise_for_status()
    return r.json()["lines"]

# ── Display helpers ───────────────────────────────────────────────────────────

def print_config(cfg):
    print("\n  Model config:")
    for agent, info in sorted(cfg.items()):
        flag = " [OVERRIDE]" if info["overridden"] else ""
        print(f"    {agent:12} {info['model']}{flag}")
    print()

def print_response(result):
    agent = result.get("active_agent", "?")
    response = result.get("response", "")
    print(f"\n  [{agent}] {response}\n")

# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    session_id = sys.argv[1] if len(sys.argv) > 1 else "interactive-test"
    print(f"\n=== Life Agent Interactive Tester ===")
    print(f"  Session: {session_id}")
    print(f"  Backend: {BASE}")
    print(f"  Type /help for commands\n")
    print_config(get_config())

    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not line:
            continue

        if line.startswith("/"):
            parts = line.split()
            cmd = parts[0]

            if cmd in ("/quit", "/exit", "/q"):
                break

            elif cmd == "/help":
                print(__doc__)

            elif cmd == "/reset":
                reset_session(session_id)
                print(f"  Session '{session_id}' reset.\n")

            elif cmd == "/session":
                if len(parts) < 2:
                    print(f"  Current session: {session_id}\n")
                else:
                    session_id = parts[1]
                    print(f"  Switched to session: {session_id}\n")

            elif cmd == "/model":
                if len(parts) == 2 and parts[1] == "reset":
                    print_config(reset_model())
                elif len(parts) == 2 and parts[1] == "status":
                    print_config(get_config())
                elif len(parts) == 3:
                    try:
                        print_config(set_model(parts[1], parts[2]))
                    except requests.HTTPError as e:
                        print(f"  Error: {e.response.json().get('detail', str(e))}\n")
                else:
                    print("  Usage: /model <agent> <model>  |  /model reset  |  /model status\n")

            elif cmd == "/db":
                if len(parts) < 2:
                    print("  Usage: /db <table>\n")
                else:
                    result = get_db(parts[1])
                    print(f"\n  {result['count']} rows from {parts[1]}:")
                    for row in result["items"]:
                        print(f"    id={row['id']} {json.dumps(row['data'], indent=None)[:120]}")
                    print()

            elif cmd == "/log":
                n = int(parts[1]) if len(parts) > 1 else 30
                for line_ in get_log(n):
                    print(" ", line_)
                print()

            elif cmd == "/agent":
                # Peek at active agent via a harmless empty-ish check
                cfg = get_config()
                print(f"  (use /log to check active agent from log)\n")

            else:
                print(f"  Unknown command: {cmd}. Type /help.\n")

        else:
            try:
                result = chat(line, session_id)
                print_response(result)
            except requests.HTTPError as e:
                print(f"  HTTP error: {e.response.status_code} {e.response.text[:200]}\n")
            except requests.Timeout:
                print("  Request timed out.\n")
            except Exception as e:
                print(f"  Error: {e}\n")


if __name__ == "__main__":
    main()
