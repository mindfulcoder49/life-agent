import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database import init_db, get_db, insert_row
from config import ADMIN_USERNAME, ADMIN_PASSWORD
from auth import hash_password
from logging_service import log_info
import json

def seed_admin():
    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM users WHERE json_extract(data, '$.username') = ?",
        (ADMIN_USERNAME,)
    ).fetchone()
    conn.close()
    if existing:
        return
    user_data = {
        "username": ADMIN_USERNAME,
        "password_hash": hash_password(ADMIN_PASSWORD),
        "display_name": "Admin",
        "is_admin": True,
        "openai_api_key": None,
        "theme": "dark",
        "settings": {},
    }
    insert_row("users", user_data)
    log_info("system", "seed", "Admin user created")

def seed_help_articles():
    from database import count_rows
    if count_rows("help_articles") > 0:
        return
    articles = [
        {
            "slug": "getting-started",
            "title": "Getting Started",
            "category": "basics",
            "order": 1,
            "body": (
                "# Getting Started\n\n"
                "Welcome to Life Agent! This system helps you organize the tasks, obligations, and worries "
                "that take up mental space, and turns them into structured daily plans.\n\n"
                "## Your Agent Team\n\n"
                "You'll chat with a team of AI agents, each named after an element:\n\n"
                "- **Hydrogen** — The manager. Routes you to the right specialist and creates daily recommendations.\n"
                "- **Helium** — Life Goals specialist. Helps you define your big-picture goals.\n"
                "- **Lithium** — State specialist. Checks in on how you're doing physically and mentally.\n"
                "- **Beryllium** — Task specialist. Captures your tasks, obligations, and worries.\n\n"
                "## Onboarding\n\n"
                "The first time you chat, the agents will walk you through onboarding:\n\n"
                "1. **Helium** asks about your life goals — what matters most to you, and how stressed you are about each one\n"
                "2. **Lithium** checks your current state — food, sleep, exercise, energy levels\n"
                "3. **Beryllium** captures your tasks — everything on your plate, from errands to big projects\n"
                "4. **Hydrogen** synthesizes it all into a prioritized daily plan\n\n"
                "## After Onboarding\n\n"
                "Once set up, you can:\n"
                "- Ask for a daily recommendation any time\n"
                "- Update your goals, state, or tasks by telling the agent what changed\n"
                "- Start new chat sessions for different days or topics\n"
                "- View and edit all your data in the Database tab\n"
                "- Check your todo lists in the Todo tab\n\n"
                "## Tips\n\n"
                "- You don't need to give every detail at once — agents save partial information and ask follow-ups\n"
                "- The active agent indicator at the top of chat shows who you're talking to\n"
                "- Tap any AI message to see the full context (what the AI received and what tools it called)\n"
                "- Use the sessions menu to start fresh conversations"
            ),
        },
        {
            "slug": "life-goals",
            "title": "Life Goals",
            "category": "basics",
            "order": 2,
            "body": (
                "# Life Goals\n\n"
                "Life goals are the big-picture objectives that drive your daily decisions. "
                "They're the foundation of how Life Agent prioritizes your tasks.\n\n"
                "## Goal Properties\n\n"
                "Each goal has:\n"
                "- **Title** — A short name for the goal\n"
                "- **Description** — More detail about what this means to you\n"
                "- **Priority (1-10)** — How important is this goal? 10 = most important\n"
                "- **Stress (1-10)** — How much does not having achieved this weigh on you? 10 = constantly on your mind\n"
                "- **Status** — Active, paused, or completed\n\n"
                "## How Goals Are Used\n\n"
                "When Hydrogen creates your daily recommendation, it considers:\n"
                "- Higher priority goals get more attention in task ordering\n"
                "- Higher stress goals may get prioritized to reduce your mental load\n"
                "- Tasks linked to goals are ranked higher than unlinked tasks\n\n"
                "## Examples\n\n"
                "- \"Get healthier\" — Priority: 8, Stress: 6\n"
                "- \"Finish degree\" — Priority: 9, Stress: 8\n"
                "- \"Save for house\" — Priority: 7, Stress: 5\n"
                "- \"Spend more time with family\" — Priority: 8, Stress: 4\n\n"
                "## Managing Goals\n\n"
                "You can add, update, or remove goals at any time by telling the chat agent, "
                "or by editing them directly in the Database tab under Life Goals."
            ),
        },
        {
            "slug": "user-state",
            "title": "Tracking Your State",
            "category": "basics",
            "order": 3,
            "body": (
                "# Tracking Your State\n\n"
                "Your physical and mental state directly affects what you can realistically accomplish in a day. "
                "Regular check-ins help the AI give better recommendations.\n\n"
                "## What Gets Tracked\n\n"
                "- **Food** — What you've eaten recently (free text)\n"
                "- **Exercise** — Recent physical activity (free text)\n"
                "- **Sleep** — Last night's duration and quality (free text)\n"
                "- **Energy (1-10)** — How much energy you have right now\n"
                "- **Soreness (1-10)** — Physical discomfort level\n"
                "- **Sickness (1-10)** — How sick you feel\n"
                "- **Notes** — Anything else about how you're feeling\n\n"
                "## How State Affects Recommendations\n\n"
                "- Low energy? The AI will suggest lighter, less cognitively demanding tasks\n"
                "- High soreness? Physical tasks get deprioritized\n"
                "- Feeling sick? The AI focuses on essentials only\n"
                "- Well rested and energetic? Time for the hard stuff\n\n"
                "## Check-in Frequency\n\n"
                "Hydrogen will route you to Lithium for a state check-in if it's been more than 4 hours "
                "since your last one. You can also request a check-in at any time by saying something like "
                "\"I want to update how I'm feeling.\"\n\n"
                "You don't need to provide every field — Lithium will save whatever you share and ask about the rest."
            ),
        },
        {
            "slug": "tasks",
            "title": "Tasks & Obligations",
            "category": "basics",
            "order": 4,
            "body": (
                "# Tasks & Obligations\n\n"
                "Tasks are the concrete things on your plate — from errands to big projects, "
                "from daily habits to looming deadlines.\n\n"
                "## One-Time Tasks\n\n"
                "Things you need to do once:\n"
                "- Appointments, errands, chores\n"
                "- Project milestones, assignments\n"
                "- Anything with a specific deadline\n\n"
                "Properties: title, description, deadline, estimated minutes, cognitive load (1-10), linked life goals.\n\n"
                "## Recurring Tasks\n\n"
                "Things you do on a regular schedule:\n"
                "- Exercise routines, meal prep, cleaning\n"
                "- Weekly reviews, check-ins, meetings\n"
                "- Medication, habits, maintenance\n\n"
                "Properties: title, description, interval (in days), estimated minutes, cognitive load (1-10), linked life goals.\n\n"
                "## Cognitive Load\n\n"
                "This is a key concept in Life Agent. Cognitive load (1-10) measures how much a task "
                "weighs on your mind when it's not done:\n"
                "- **1-3**: Background items that don't bother you much\n"
                "- **4-6**: Moderate weight — you think about them regularly\n"
                "- **7-10**: Heavy — these keep you up at night\n\n"
                "The AI uses cognitive load alongside deadlines and goal priority to decide what you should tackle first.\n\n"
                "## Completing Tasks\n\n"
                "Mark tasks complete through chat or the Database tab. "
                "Completing a recurring task creates a completion record and the task remains active for next time."
            ),
        },
        {
            "slug": "daily-recommendations",
            "title": "Daily Recommendations",
            "category": "features",
            "order": 5,
            "body": (
                "# Daily Recommendations\n\n"
                "The daily recommendation is where everything comes together. Hydrogen reads all your data "
                "and creates a prioritized plan for your day.\n\n"
                "## What It Considers\n\n"
                "- Your life goals and their priorities\n"
                "- Your current physical/mental state\n"
                "- Task deadlines and cognitive load\n"
                "- Overdue recurring tasks\n"
                "- Recently completed tasks (so it doesn't repeat them)\n"
                "- Estimated time for each task\n\n"
                "## How to Get One\n\n"
                "After onboarding is complete, Hydrogen will offer a daily recommendation automatically. "
                "You can also ask for one at any time:\n"
                "- \"What should I do today?\"\n"
                "- \"Give me a daily plan\"\n"
                "- \"I need a recommendation\"\n\n"
                "## Todo Lists\n\n"
                "When you approve a recommendation, Hydrogen saves it as a todo list. "
                "View your todo lists in the Todo tab — they include the AI's reasoning for each task's placement."
            ),
        },
        {
            "slug": "chat-sessions",
            "title": "Chat Sessions",
            "category": "features",
            "order": 6,
            "body": (
                "# Chat Sessions\n\n"
                "You can have multiple chat sessions — one per day, one per topic, or however you prefer.\n\n"
                "## Managing Sessions\n\n"
                "- The **sessions button** (speech bubble icon) in the chat header opens the session menu\n"
                "- Click **+ New** to start a fresh conversation\n"
                "- Click any existing session to switch to it\n"
                "- The **default** session is your main conversation\n\n"
                "## How Sessions Work\n\n"
                "Each session has its own:\n"
                "- Conversation history\n"
                "- Active agent state (which specialist is currently talking to you)\n"
                "- Context cache (so agents don't repeat tool calls within the same session)\n\n"
                "Your underlying data (goals, state, tasks) is shared across all sessions — "
                "they're just different conversation threads.\n\n"
                "## Clearing a Session\n\n"
                "The **trash icon** in the chat header clears the current session's conversation history "
                "and resets its agent state. Your data in the database is not affected."
            ),
        },
        {
            "slug": "database-viewer",
            "title": "Database Viewer",
            "category": "features",
            "order": 7,
            "body": (
                "# Database Viewer\n\n"
                "The Database tab lets you see and edit all your data directly.\n\n"
                "## Tables\n\n"
                "Switch between tables using the tabs at the top:\n"
                "- **Life Goals** — Your goals with priority and stress scores\n"
                "- **User States** — Your physical/mental check-in history\n"
                "- **One-Time Tasks** — Single tasks with deadlines\n"
                "- **Recurring Tasks** — Repeating tasks with intervals\n"
                "- **Todo Lists** — AI-generated daily plans\n"
                "- **Chat Contexts** — Conversation history\n\n"
                "## Viewing Records\n\n"
                "Records are displayed as readable key-value pairs. Each record shows:\n"
                "- An ID number and creation timestamp\n"
                "- All fields in a friendly format\n\n"
                "## Editing Records\n\n"
                "Click **Edit** on any record to modify it as JSON. Click **Save** to apply changes. "
                "This is useful for quick fixes without going through the chat.\n\n"
                "## Deleting Records\n\n"
                "Click **Del** to permanently remove a record. This cannot be undone."
            ),
        },
        {
            "slug": "themes",
            "title": "Themes",
            "category": "settings",
            "order": 8,
            "body": (
                "# Themes\n\n"
                "Life Agent comes with 6 color themes. Your choice is saved to your account "
                "and persists across sessions.\n\n"
                "## Available Themes\n\n"
                "- **Dark** — Dark background with cool accents (default)\n"
                "- **Light** — Clean white background\n"
                "- **Green** — Nature-inspired dark theme\n"
                "- **Blue** — Ocean-inspired dark theme\n"
                "- **Pink** — Warm pink-toned dark theme\n"
                "- **Beige** — Soft warm light theme\n\n"
                "## Changing Themes\n\n"
                "Click the palette icon in the top bar to open the theme picker. "
                "Click any theme to preview it — the picker stays open so you can try several."
            ),
        },
        {
            "slug": "api-key",
            "title": "Using Your Own API Key",
            "category": "settings",
            "order": 9,
            "body": (
                "# Using Your Own API Key\n\n"
                "By default, Life Agent uses the system's OpenAI API key for all conversations. "
                "You can optionally provide your own key.\n\n"
                "## Setting Your Key\n\n"
                "1. Go to **Settings** (gear icon in the top bar)\n"
                "2. Paste your OpenAI API key in the API key field\n"
                "3. Click Save\n\n"
                "Your key is stored in your account and used only for your conversations.\n\n"
                "## Removing Your Key\n\n"
                "Clear the API key field and save. The system will fall back to the default key.\n\n"
                "## Why Use Your Own Key?\n\n"
                "- If the system key has usage limits\n"
                "- If you want your usage on your own billing\n"
                "- If you have access to different models"
            ),
        },
        {
            "slug": "full-context",
            "title": "Viewing Full Context",
            "category": "features",
            "order": 10,
            "body": (
                "# Viewing Full Context\n\n"
                "Every AI message can show you exactly what happened behind the scenes.\n\n"
                "## How to View\n\n"
                "1. Tap any AI message in chat\n"
                "2. Click **See full context**\n"
                "3. A modal shows the complete context log\n\n"
                "## What You'll See\n\n"
                "- **System prompt** — The instructions the agent received\n"
                "- **Messages** — The conversation history sent to the AI\n"
                "- **Tool calls** — Which tools the agent called, with what arguments, and what results came back\n\n"
                "This is useful for understanding why the AI made certain decisions, "
                "debugging unexpected behavior, or just seeing how the agent system works."
            ),
        },
    ]
    for article in articles:
        insert_row("help_articles", article)
    log_info("system", "seed", f"Seeded {len(articles)} help articles")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_admin()
    seed_help_articles()
    # Initialize agent graph
    try:
        from agents.graph import create_graph_runner
        from api.chat import router as chat_router_module
        import api.chat as chat_module
        runner = create_graph_runner()
        chat_module.graph_runner = runner
        log_info("system", "startup", "Agent graph initialized")
    except Exception as e:
        log_info("system", "startup", f"Agent graph failed to initialize: {e}")
    yield

app = FastAPI(title="Life Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from api.auth_routes import router as auth_router
from api.chat import router as chat_router
from api.users import router as users_router
from api.life_goals import router as life_goals_router
from api.user_states import router as user_states_router
from api.tasks import router as tasks_router
from api.todo_lists import router as todo_lists_router
from api.admin import router as admin_router
from api.help import router as help_router

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(users_router)
app.include_router(life_goals_router)
app.include_router(user_states_router)
app.include_router(tasks_router)
app.include_router(todo_lists_router)
app.include_router(admin_router)
app.include_router(help_router)

# Serve frontend static files in production
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))
