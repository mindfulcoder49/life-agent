# Life Agent — Project Reference

## Running the project

```bash
bash dev.sh
```

- Picks a random free port for the backend, writes it to `.backend_port`
- Starts FastAPI backend with `uvicorn --reload` at that port
- Injects `APP_URL=http://localhost:5173` into the backend process (used for magic link emails)
- Starts Vite frontend dev server at `http://localhost:5173`
- Vite proxies `/api/*` to the backend port

## Project layout

```
life-agent/
├── dev.sh                  # Dev runner (see above)
├── fly.toml                # Fly.io config — app: life-agent, region: iad
├── fly.secrets.sh          # gitignored — run to push secrets to Fly
├── .env                    # gitignored — local secrets
├── backend/
│   ├── main.py             # FastAPI app, lifespan, router registration, SPA fallback
│   ├── config.py           # All env vars (OPENAI_API_KEY, SMTP_*, APP_URL, etc.)
│   ├── database.py         # SQLite helpers: init_db, insert_row, get_row, get_rows, update_row, delete_row, count_rows
│   ├── auth.py             # Session auth: create_session, get_session_user, get_current_user, require_admin
│   ├── models.py           # Pydantic request models
│   ├── runtime_config.py   # Per-agent model overrides (get_agent_model)
│   ├── file_logger.py      # logger + log_conversation_turn
│   ├── agents/
│   │   ├── graph.py        # Agent dispatcher: create_graph_runner() → run / run_stream / reset
│   │   ├── hydrogen.py     # Manager/router agent
│   │   ├── helium.py       # Life goals specialist
│   │   ├── lithium.py      # State check-in specialist
│   │   ├── beryllium.py    # Tasks & metrics specialist
│   │   ├── boron.py        # Weekly review specialist
│   │   └── tools/
│   │       ├── life_goal_tools.py   # make_life_goal_tools, fetch_life_goals, format_goals_for_prompt
│   │       ├── state_tools.py       # fetch_recent_states, format_states_for_prompt
│   │       ├── task_tools.py        # make_task_tools, fetch_tasks, format_tasks_for_prompt, fetch_recent_metric_completions
│   │       ├── todo_tools.py        # make_todo_tools
│   │       ├── review_tools.py      # fetch_last_weekly_review
│   │       └── help_tools.py        # make_help_tools
│   ├── api/
│   │   ├── auth_routes.py  # /api/auth/* — login, register, logout, me, magic link
│   │   ├── chat.py         # /api/chat — SSE streaming chat endpoint
│   │   ├── life_goals.py   # /api/life-goals CRUD
│   │   ├── user_states.py  # /api/user-states CRUD
│   │   ├── tasks.py        # /api/tasks CRUD
│   │   ├── todo_lists.py   # /api/todo-lists CRUD
│   │   ├── users.py        # /api/users — profile, API key
│   │   ├── onboarding.py   # /api/onboarding/* — unauthenticated onboarding flow
│   │   ├── welcome.py      # /api/welcome/suggestions — GPT task suggestions for new users
│   │   ├── admin.py        # /api/admin — admin tools
│   │   └── help.py         # /api/help — help articles
│   └── tests/
│       ├── stress_mini.py              # Headless stress test runner (see Testing below)
│       ├── test_selfie_transform.py    # Selfie → aspirational image test script
│       ├── selfie_output/              # gitignored — generated images
│       └── reports/                    # gitignored — timing reports from stress runs
└── frontend/
    ├── src/
    │   ├── App.vue                 # Root — auth guard, top bar, bottom nav
    │   ├── router.js               # Hash-based router; routes: /welcome /chat /todo /database /settings /admin /login /onboarding /setup-password /help
    │   ├── api/client.js           # Axios instance (baseURL: /api, withCredentials); 401 skips public routes
    │   ├── stores/auth.js          # Pinia auth store (fetchMe, login, register, logout)
    │   ├── stores/chat.js          # Pinia chat store — messages, streaming, sessions, pendingMessage
    │   ├── stores/theme.js         # Pinia theme store
    │   └── components/
    │       ├── OnboardingView.vue  # Unauthenticated onboarding flow (goal → selfie → image → email)
    │       ├── LoginView.vue       # Two-tab: password login OR request magic link
    │       ├── SetPasswordView.vue # First-time password setup via magic token (?token= query param)
    │       ├── WelcomeView.vue     # Post-login dashboard (state sliders + suggestions or action buttons)
    │       ├── ChatView.vue        # Main chat UI with SSE streaming; consumes chat.pendingMessage on mount
    │       ├── TodoView.vue        # Todo list viewer
    │       ├── DatabaseView.vue    # Raw DB viewer/editor
    │       ├── SettingsView.vue    # User settings
    │       └── AdminView.vue       # Admin panel
    └── vite.config.js              # Proxies /api/* to backend port (reads VITE_BACKEND_PORT)
```

## Database

SQLite at `backend/life_agent.db` (prod: `/data/life_agent.db` on Fly volume).

All tables use a JSON blob pattern:
```sql
CREATE TABLE foo (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT DEFAULT (datetime('now')),
  data TEXT NOT NULL  -- JSON blob
)
```

Access via `json_extract(data, '$.field')`. Key tables:
- `users` — username, email, password_hash, display_name, is_admin, openai_api_key, theme, timezone
- `sessions` — session_token, user_id, expires_at, type ("magic" for magic-link tokens)
- `life_goals` — user_id, title, description, priority (1-10), stress (1-10), status
- `user_states` — user_id, energy, soreness, sickness, notes, created_at
- `one_time_tasks` — user_id, title, description, deadline, estimated_minutes, cognitive_load, completed, completed_at, completed_date
- `recurring_tasks` — user_id, title, description, interval_days, estimated_minutes, cognitive_load, active, mandatory, metric (JSON)
- `metric_completions` — user_id, task_id, metric_value, completed_date, est_calories, est_protein_g, etc.
- `todo_lists` — user_id, items (JSON array), created_at
- `chat_contexts` — user_id, session_id, role, content, context_log, agent

Helper functions in `database.py`: `insert_row(table, data) → int`, `get_row(table, id)`, `get_rows(table, filters, limit, offset, order_desc)`, `update_row(table, id, data)`, `delete_row(table, id)`, `count_rows(table, filters)`.

`completed_date` is YYYY-MM-DD in the user's local timezone (use `user_today(user_id)` from database.py). `completed_at` is UTC ISO wall-clock.

## Agent system

`create_graph_runner()` in `agents/graph.py` returns a `run` function with methods:
- `run(user_id, message, session_id)` — blocking
- `run_stream(user_id, message, session_id, on_event)` — async, streams tokens via callback
- `run.reset(user_id, session_id)` — clear session state
- `run.invalidate_goals_cache(user_id)` — bust goal cache after writes
- `run.invalidate_metrics_cache(user_id)` — bust metrics cache after writes

Each agent runner signature: `run_X(user_id, messages, context_cache, on_event) → {response, context_log, hand_off_to}`.

`context_cache` is a dict shared across all turns in a session:
- `life_goals` — pre-fetched, cleared by invalidate_goals_cache
- `recent_states` — pre-fetched each session
- `recent_metrics` — pre-fetched, cleared by invalidate_metrics_cache
- `last_weekly_review` — pre-fetched each session
- `tasks` — pre-fetched, cleared by any write tool in task_tools.py
- `has_tasks` — bool, cached
- `oldest_todo_date` — for weekly review eligibility
- `task_plan` — optional, set by Boron when handing off to Beryllium

Performance rule: tasks and goals are pre-injected into every agent's system prompt. The `get_tasks` and `get_life_goals` tools have explicit docstrings pointing to the section name (`'## Current Tasks'`) so models don't call them unnecessarily.

Code-level pre-routing in `graph.py`: if no life goals exist, skip Hydrogen LLM and go straight to Helium.

## Auth

Session cookie: `session_token` (HttpOnly, SameSite=Lax). Session expires in 72 hours.

**Onboarding magic link (new users):**
1. `POST /api/onboarding/claim` → creates user with `needs_password_setup: true` + life goal → inserts magic session row (`type: "magic"`, 24hr expiry) → sends email
2. User clicks link → `GET /api/auth/magic?token=xxx`:
   - `needs_password_setup: true` → redirect to `/#/setup-password?token=xxx` (token NOT burned yet)
   - Otherwise → burn token, create real session, set cookie, redirect to `/#/welcome`
3. `POST /api/auth/setup-password` → validates token, hashes password, clears `needs_password_setup`, burns token, creates session, sets cookie

**Existing user magic link:** `POST /api/auth/request-magic-link` → find user by email → send link → same `GET /api/auth/magic` flow (skips password setup since flag is false).

**Username/password:** `POST /api/auth/login`.

**401 interceptor** (`api/client.js`): redirects to `#/onboarding` on 401, BUT skips redirect if already on a public route (`#/onboarding`, `#/login`, `#/setup-password`). This prevents the `fetchMe()` call in App.vue from kicking unauthenticated users off public pages.

## Onboarding flow (unauthenticated)

`OnboardingView.vue` stages: `chat → selfie → processing → result → sent`

1. User types goal → `POST /api/onboarding/chat` (GPT-4.1-mini extracts + confirms goal, asks for selfie)
2. User uploads selfie → `POST /api/onboarding/transform` (multipart: image + goal) → GPT-4.1-mini writes visual description → gpt-image-1.5 generates aspirational image → returns base64 PNG
3. User enters email → `POST /api/onboarding/claim` → user created, goal saved, `aspirational_image_b64` stored in user data, magic link emailed

Unauthenticated users are redirected to `/onboarding`. `/login` is for existing users (password or magic link).

After clicking the magic link, new users go to `/setup-password` to set a password, then land on `/welcome`.

## Welcome dashboard

`WelcomeView.vue` — shown to all users after login (linked from bottom nav "Home").

**New user** (`is_new: true` from `/api/users/me`, i.e. no `user_states` rows yet): 3 stages:
1. `state` — energy/soreness/sickness sliders (1–10, CSS gradient fill via `--fill` custom property)
2. `loading` — calls `POST /api/user-states` + `GET /api/welcome/suggestions` (GPT-4.1-mini generates 10-12 task suggestions as JSON based on goal + state)
3. `suggestions` — card grid multi-select (all pre-selected); confirm saves tasks to DB then sets `chat.pendingMessage` and routes to `/chat`

**Returning user**: single screen — sliders + 3 action buttons (Build my plan / Weekly review / Update tasks). Button click POSTs state then sets `chat.pendingMessage = message` and routes to `/chat`.

**`chat.pendingMessage`** (Pinia store, `stores/chat.js`): WelcomeView sets it instead of using `?msg=` URL query params. ChatView reads and clears it in `onMounted` before sending. This prevents duplicate messages when ChatView remounts.

`GET /api/welcome/suggestions` params: `goal`, `energy`, `soreness`, `sickness`. Returns `{"suggestions": [{title, type, interval_days, estimated_minutes, cognitive_load, emoji, description, metric}]}`.

## Selfie transform (standalone test)

```bash
cd backend
venv/bin/python3 tests/test_selfie_transform.py /path/to/selfie.jpg "your goal here"
# Output: tests/selfie_output/aspirational_<timestamp>.png
```

Uses gpt-image-1.5 via `client.images.edit`. The script calls GPT-4.1-mini first to generate a goal-appropriate visual description, then passes that into the image edit prompt.

## Testing

All tests require the backend to be running (`bash dev.sh` or `BACKEND_PORT=... uvicorn ...`).

### Auth flow test (fast, no LLM calls)

```bash
cd backend && venv/bin/python3 tests/test_auth_flow.py
```

Tests the full new-user auth flow without sending real emails:
1. `POST /api/onboarding/claim` — user + goal created, magic session row inserted
2. Reads token from DB directly (no email required)
3. `GET /api/auth/magic?token=...` — verifies redirect to `/#/setup-password`, token NOT burned
4. `POST /api/auth/setup-password` — verifies password set, `needs_password_setup` cleared, token burned, session cookie set
5. `GET /api/auth/me` with new cookie — verifies session is valid
6. `POST /api/auth/request-magic-link` for existing user — verifies redirect goes to `/#/welcome` (not setup-password), token burned

### Agent routing test (1 LLM call per turn)

```bash
cd backend && venv/bin/python3 tests/test_routing.py
```

Verifies Hydrogen routes correctly to Lithium (state check) when goals exist but no recent state, then back to Hydrogen after state is saved, and that a todo list is created after accepting the recommendation.

### Stress test (all agents, many LLM calls)

```bash
cd backend && venv/bin/python3 tests/stress_mini.py
```

Runs 7 headless scenarios against the live backend using the `__test__` user with all agents set to gpt-5-mini. Scenarios cover routing, Beryllium nutrition/task capture, Hydrogen synthesis, Helium goal capture, context cache discipline, and Lithium edge cases. Saves timing reports to `tests/reports/timing_<timestamp>.txt`.

Uses `/api/admin/test/*` endpoints (X-Api-Key: dev-admin-api-key) for DB inspection, session reset, and model overrides.

## Deployment

```bash
bash fly.secrets.sh   # push secrets (first time or when secrets change)
fly deploy            # from backend/ or root depending on Dockerfile location
```

After deploy, run migration if needed:
```bash
fly ssh console
python3 migrate_completed_dates.py --dry-run
python3 migrate_completed_dates.py
```

`COOKIE_SECURE=true` and `APP_URL=https://life-agent.fly.dev` are set in Fly environment (fly.toml and fly.secrets.sh respectively).

## Config env vars

| Var | Default | Notes |
|-----|---------|-------|
| `OPENAI_API_KEY` | — | Required |
| `SECRET_KEY` | dev-secret-key | Change in prod |
| `APP_URL` | http://localhost:5173 | Set dynamically in dev.sh; set to Fly URL in fly.secrets.sh |
| `MAIL_HOST` | smtp.hostinger.com | |
| `MAIL_PORT` | 587 | |
| `MAIL_USERNAME` | — | |
| `MAIL_PASSWORD` | — | |
| `MAIL_FROM_ADDRESS` | — | |
| `MAIL_FROM_NAME` | Life Agent | |
| `COOKIE_SECURE` | false | Set to true in fly.toml |
| `DB_PATH` | backend/life_agent.db | /data/life_agent.db on Fly |
| `LOG_DIR` | backend/logs/ | /data/logs on Fly |
