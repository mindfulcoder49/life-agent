from fastapi import APIRouter, Request, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import Optional
from models import HelpArticleCreate, DataUpdate
from auth import require_admin
from database import get_rows, get_row, delete_row, insert_row, update_row, count_rows, get_db
from file_logger import is_debug_enabled, set_debug_enabled
import json
import os as _os

router = APIRouter(prefix="/api/admin", tags=["admin"])

@router.get("/users")
def list_users(request: Request, limit: int = 50, offset: int = 0):
    require_admin(request)
    rows = get_rows("users", limit=limit, offset=offset)
    result = []
    for row in rows:
        d = row["data"]
        result.append({
            "id": row["id"],
            "username": d["username"],
            "display_name": d.get("display_name"),
            "is_admin": d.get("is_admin", False),
            "created_at": row["created_at"],
        })
    total = count_rows("users")
    return {"items": result, "total": total}

@router.delete("/users/{user_id}")
def delete_user(request: Request, user_id: int):
    admin = require_admin(request)
    if admin["id"] == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    delete_row("users", user_id)
    return {"ok": True}

@router.get("/logs")
def list_logs(request: Request, limit: int = 100, offset: int = 0, level: str = None, source: str = None):
    require_admin(request)
    filters = {}
    if level:
        filters["level"] = level
    if source:
        filters["source"] = source
    rows = get_rows("logs", filters=filters, limit=limit, offset=offset)
    total = count_rows("logs", filters=filters)
    return {"items": rows, "total": total}

@router.get("/debug-logging")
def get_debug_logging(request: Request):
    require_admin(request)
    return {"enabled": is_debug_enabled()}


class DebugLoggingUpdate(BaseModel):
    enabled: bool


@router.put("/debug-logging")
def update_debug_logging(request: Request, body: DebugLoggingUpdate):
    require_admin(request)
    set_debug_enabled(body.enabled)
    return {"enabled": is_debug_enabled()}


@router.get("/help-articles")
def list_articles(request: Request):
    require_admin(request)
    return get_rows("help_articles", limit=200, order_desc=False)

@router.post("/help-articles")
def create_article(request: Request, body: HelpArticleCreate):
    require_admin(request)
    row_id = insert_row("help_articles", body.model_dump())
    return get_row("help_articles", row_id)

@router.put("/help-articles/{article_id}")
def update_article(request: Request, article_id: int, body: DataUpdate):
    require_admin(request)
    row = get_row("help_articles", article_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    merged = {**row["data"], **body.data}
    update_row("help_articles", article_id, merged)
    return get_row("help_articles", article_id)

@router.delete("/help-articles/{article_id}")
def delete_article(request: Request, article_id: int):
    require_admin(request)
    delete_row("help_articles", article_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Test API — API key auth, no browser session required
# ---------------------------------------------------------------------------

_test_user_id_cache: int | None = None


def _require_api_key(x_api_key: str = Header(default=None)):
    from config import ADMIN_API_KEY
    if not x_api_key or x_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing X-Api-Key header")


def _get_test_user_id() -> int:
    global _test_user_id_cache
    if _test_user_id_cache is not None:
        return _test_user_id_cache
    from config import TEST_USER_USERNAME
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM users WHERE json_extract(data, '$.username') = ?",
        (TEST_USER_USERNAME,)
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=500, detail="Test user not found — check server startup logs")
    _test_user_id_cache = row["id"]
    return _test_user_id_cache


class TestChatRequest(BaseModel):
    message: str
    session_id: str = "test-default"


@router.post("/test/chat", dependencies=[Depends(_require_api_key)])
async def test_chat(body: TestChatRequest):
    import api.chat as chat_module
    if chat_module.graph_runner is None:
        raise HTTPException(status_code=503, detail="Agent system not initialized")
    user_id = _get_test_user_id()
    result = await chat_module.graph_runner(user_id, body.message, body.session_id)
    return result


@router.delete("/test/session/{session_id}", dependencies=[Depends(_require_api_key)])
def test_reset_session(session_id: str):
    import api.chat as chat_module
    user_id = _get_test_user_id()
    if chat_module.graph_runner and hasattr(chat_module.graph_runner, "reset"):
        chat_module.graph_runner.reset(user_id, session_id)
    conn = get_db()
    conn.execute(
        "DELETE FROM chat_contexts WHERE json_extract(data, '$.user_id') = ? AND json_extract(data, '$.session_id') = ?",
        (user_id, session_id)
    )
    conn.commit()
    conn.close()
    return {"ok": True, "session_id": session_id}


_ALLOWED_TEST_TABLES = {
    "life_goals", "user_states", "one_time_tasks", "recurring_tasks",
    "todo_lists", "chat_contexts", "weekly_reviews",
}


@router.get("/test/db/{table}", dependencies=[Depends(_require_api_key)])
def test_db_table(table: str, limit: int = 50, user_scoped: bool = True):
    if table not in _ALLOWED_TEST_TABLES:
        raise HTTPException(
            status_code=400,
            detail=f"Table '{table}' not accessible. Allowed: {sorted(_ALLOWED_TEST_TABLES)}"
        )
    filters = {"user_id": _get_test_user_id()} if user_scoped else {}
    rows = get_rows(table, filters=filters, limit=limit)
    return {"table": table, "items": rows, "count": len(rows)}


class TestDbQueryRequest(BaseModel):
    sql: str
    params: list = []


@router.get("/test/whoami", dependencies=[Depends(_require_api_key)])
def test_whoami():
    """Return the test user's id and username."""
    uid = _get_test_user_id()
    from config import TEST_USER_USERNAME
    return {"id": uid, "username": TEST_USER_USERNAME}


@router.post("/test/db/query", dependencies=[Depends(_require_api_key)])
def test_db_query(body: TestDbQueryRequest):
    try:
        conn = get_db()
        cursor = conn.execute(body.sql, body.params)
        cols = [d[0] for d in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        conn.commit()
        conn.close()
        return {"rows": [{cols[i]: row[i] for i in range(len(cols))} for row in rows], "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/test/config", dependencies=[Depends(_require_api_key)])
def test_get_config():
    """Return current effective model for every agent."""
    from runtime_config import get_status
    return get_status()


class TestConfigUpdate(BaseModel):
    agent: str
    model: str


@router.put("/test/config", dependencies=[Depends(_require_api_key)])
def test_set_config(body: TestConfigUpdate):
    """Override the model for a specific agent at runtime (no restart needed)."""
    from runtime_config import set_agent_model
    try:
        set_agent_model(body.agent, body.model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    from runtime_config import get_status
    return get_status()


@router.delete("/test/config/{agent}", dependencies=[Depends(_require_api_key)])
def test_reset_config(agent: str):
    """Reset a single agent back to its default model."""
    from runtime_config import reset_agent_model, get_status
    reset_agent_model(agent)
    return get_status()


@router.delete("/test/config", dependencies=[Depends(_require_api_key)])
def test_reset_all_config():
    """Reset all agents to their default models."""
    from runtime_config import reset_all, get_status
    reset_all()
    return get_status()


@router.get("/test/log/tail", dependencies=[Depends(_require_api_key)])
def test_log_tail(lines: int = 100):
    from config import LOG_DIR
    log_path = _os.path.join(LOG_DIR, "life_agent.log")
    if not _os.path.exists(log_path):
        return {"lines": [], "path": log_path}
    with open(log_path, "r") as f:
        all_lines = f.readlines()
    return {"lines": [l.rstrip() for l in all_lines[-lines:]], "total_lines": len(all_lines)}
