# Life Agent

AI-powered life management system that helps organize your cognitive load — tasks, obligations, worries — into a structured database connected to your life goals, physical/mental state, and daily recommendations.

## How It Works

You chat with a team of AI agents, each named after an element. They interview you to build up your personal data, then synthesize it into prioritized daily plans.

**Onboarding flow:**
1. **Helium** asks about your life goals (priorities, stress levels)
2. **Lithium** checks your current physical/mental state
3. **Beryllium** captures your tasks, obligations, and worries
4. **Hydrogen** synthesizes everything into daily recommendations

After onboarding, agents check in periodically and you can update any area at any time.

## Architecture

```
Frontend (Vue 3 + Pinia)  <-->  FastAPI Backend  <-->  SQLite
                                      |
                                 Agent System
                            Hydrogen (Manager/Router)
                           /          |          \
                      Helium      Lithium     Beryllium
                    (Goals)      (State)      (Tasks)
```

### Agent System

| Agent | Model | Role |
|-------|-------|------|
| Hydrogen | gpt-5 | Manager/router — checks data state, routes to specialists, synthesizes daily recommendations and todo lists |
| Helium | gpt-5-mini | Life Goals specialist — interviews users to define goals with priority and stress scores |
| Lithium | gpt-5-mini | User State specialist — collects physical/mental check-in data (food, sleep, exercise, energy, soreness, sickness) |
| Beryllium | gpt-5-mini | Task Management specialist — captures one-time and recurring tasks with cognitive load scores linked to goals |

Each agent runs an internal ReAct tool-calling loop (LLM -> tool call -> result -> LLM, repeat until final response). Agents persist across messages — a specialist stays active until it explicitly hands off via `finish_conversation`. Hydrogen decides routing order based on what data exists.

### Tech Stack

- **Backend:** Python, FastAPI, SQLite, LangChain + OpenAI
- **Frontend:** Vue 3 (JavaScript), Pinia, Vue Router, Vite
- **Auth:** Cookie-based sessions with bcrypt password hashing
- **Themes:** 6 CSS themes (dark, light, green, blue, pink, beige)
- **Mobile-first** responsive design

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- An OpenAI API key

### Environment

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=sk-your-key-here
SECRET_KEY=your-random-secret-key
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-admin-password
```

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

The backend runs on `http://localhost:8000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on `http://localhost:5173` and proxies API requests to the backend.

### Production

Build the frontend and let FastAPI serve it:

```bash
cd frontend
npm run build
cd ../backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

FastAPI will serve the built frontend from `frontend/dist/`.

## Database

All tables use a flexible JSON data column:

| Table | Purpose |
|-------|---------|
| `users` | Accounts with username, password hash, theme preference, optional API key |
| `sessions` | Auth session tokens |
| `life_goals` | Goals with title, description, priority (1-10), stress (1-10), status |
| `user_states` | Physical/mental snapshots: food, exercise, sleep, energy, soreness, sickness |
| `one_time_tasks` | Tasks with deadline, estimated time, cognitive load (1-10), linked goal IDs |
| `recurring_tasks` | Repeating tasks with interval in days |
| `todo_lists` | AI-generated daily plans with reasoning |
| `chat_contexts` | Conversation history with full LLM context logs |
| `logs` | Structured application logs |
| `help_articles` | Help center content |

## API Endpoints

### Auth
- `POST /api/auth/register` — Create account
- `POST /api/auth/login` — Login (sets session cookie)
- `POST /api/auth/logout` — Logout
- `GET /api/auth/me` — Current user

### Chat
- `POST /api/chat` — Send message (with optional `session_id`)
- `GET /api/chat/history` — Conversation history (filterable by `session_id`)
- `GET /api/chat/sessions` — List chat sessions
- `GET /api/chat/active-agent` — Current active agent for a session
- `DELETE /api/chat/history/{id}` — Delete a message
- `DELETE /api/chat/history` — Clear conversation (optionally by `session_id`)

### Data (all scoped to current user)
- `/api/life-goals` — CRUD for life goals
- `/api/user-states` — CRUD for state check-ins
- `/api/tasks/one-time` — CRUD + complete for one-time tasks
- `/api/tasks/recurring` — CRUD + complete for recurring tasks
- `/api/todo-lists` — List and view todo lists

### User
- `GET/PUT /api/users/me` — Profile and theme
- `PUT /api/users/me/api-key` — Set personal OpenAI key

### Admin (requires admin role)
- `GET /api/admin/users` — List users
- `DELETE /api/admin/users/{id}` — Delete user
- `GET /api/admin/logs` — View logs
- CRUD `/api/admin/help-articles` — Manage help content

### Help
- `GET /api/help/articles` — List articles
- `GET /api/help/articles/{slug}` — Get article

## Features

- **Multi-session chat** — Multiple conversations per user (daily, topical, etc.)
- **Active agent indicator** — See which agent you're talking to
- **Full context viewer** — "See full context" on any AI message shows the complete LLM input, tool calls, and results
- **Database viewer** — Browse and edit all your data with friendly key-value display
- **6 themes** — Dark, light, green, blue, pink, beige (persisted per user)
- **Per-user API keys** — Use your own OpenAI key or the system default
- **Debug logging** — Complete conversation transcripts in `backend/logs/debug_conversations.log`
- **Context caching** — Agents share cached tool results within a session to reduce redundant API calls
- **Partial saves** — Agents save information as you provide it, without waiting for complete data

## Logging

Two log files in `backend/logs/`:

- **`life_agent.log`** — Operational log (agent routing, tool calls, errors)
- **`debug_conversations.log`** — Complete conversation transcripts for analysis

Tail the operational log during development:
```bash
tail -f backend/logs/life_agent.log
```

## Default Admin

On first run, an admin account is created from `.env` values (defaults to `admin` / `admin123`). Change this in production.
