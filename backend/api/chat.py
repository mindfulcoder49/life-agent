from fastapi import APIRouter, Request, HTTPException
from models import ChatRequest
from auth import get_current_user
from database import insert_row, get_rows, get_row, count_rows, get_db
from logging_service import log_info, log_error

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Will be set by main.py after graph is built
graph_runner = None

@router.post("")
async def chat(request: Request, body: ChatRequest):
    user = get_current_user(request)
    if graph_runner is None:
        raise HTTPException(status_code=503, detail="Agent system not initialized")
    try:
        result = await graph_runner(user["id"], body.message, body.session_id or "default")
        log_info("chat", "message", f"Chat message processed", user_id=user["id"])
        return result
    except Exception as e:
        log_error("chat", "error", str(e), user_id=user["id"])
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sessions")
def get_sessions(request: Request):
    user = get_current_user(request)
    if graph_runner and hasattr(graph_runner, 'list_sessions'):
        sessions = graph_runner.list_sessions(user["id"])
        return {"sessions": sessions}
    return {"sessions": []}

@router.get("/history")
def get_history(request: Request, session_id: str = None):
    user = get_current_user(request)
    filters = {"user_id": user["id"]}
    if session_id:
        filters["session_id"] = session_id
    rows = get_rows("chat_contexts", filters=filters, limit=200, order_desc=False)
    return {"items": rows}

@router.delete("/history/{message_id}")
def delete_message(request: Request, message_id: int):
    user = get_current_user(request)
    row = get_row("chat_contexts", message_id)
    if not row or row["data"].get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Not found")
    from database import delete_row
    delete_row("chat_contexts", message_id)
    return {"ok": True}

@router.delete("/history")
def clear_history(request: Request, session_id: str = None):
    user = get_current_user(request)
    conn = get_db()
    if session_id:
        conn.execute(
            "DELETE FROM chat_contexts WHERE json_extract(data, '$.user_id') = ? AND json_extract(data, '$.session_id') = ?",
            (user["id"], session_id)
        )
    else:
        conn.execute(
            "DELETE FROM chat_contexts WHERE json_extract(data, '$.user_id') = ?",
            (user["id"],)
        )
    conn.commit()
    conn.close()
    # Also reset in-memory conversation state
    if graph_runner and hasattr(graph_runner, 'reset'):
        graph_runner.reset(user["id"], session_id)
    return {"ok": True}

@router.get("/active-agent")
def get_active_agent(request: Request, session_id: str = "default"):
    user = get_current_user(request)
    if graph_runner and hasattr(graph_runner, 'get_active_agent'):
        agent = graph_runner.get_active_agent(user["id"], session_id)
        from agents.graph import AGENT_LABELS
        return {
            "active_agent": agent or "hydrogen",
            "active_agent_label": AGENT_LABELS.get(agent or "hydrogen"),
        }
    return {"active_agent": "hydrogen", "active_agent_label": "Hydrogen (Manager)"}
