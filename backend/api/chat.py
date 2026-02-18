import asyncio
import json

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
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

@router.post("/stream")
async def chat_stream(request: Request, body: ChatRequest):
    user = get_current_user(request)
    if graph_runner is None:
        raise HTTPException(status_code=503, detail="Agent system not initialized")
    if not hasattr(graph_runner, 'run_stream'):
        raise HTTPException(status_code=503, detail="Streaming not available")

    queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def on_event(event_type, data):
        loop.call_soon_threadsafe(queue.put_nowait, (event_type, data))

    async def run_graph():
        try:
            result = await graph_runner.run_stream(
                user["id"], body.message, body.session_id or "default", on_event)
            loop.call_soon_threadsafe(queue.put_nowait, ("done", result))
        except Exception as e:
            log_error("chat", "stream_error", str(e), user_id=user["id"])
            loop.call_soon_threadsafe(queue.put_nowait, ("error", {"detail": str(e)}))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, ("__end__", None))

    task = asyncio.create_task(run_graph())

    async def event_generator():
        while True:
            event_type, data = await queue.get()
            if event_type == "__end__":
                break
            yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        await task

    log_info("chat", "stream", "Streaming chat started", user_id=user["id"])
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@router.get("/sessions")
def get_sessions(request: Request):
    user = get_current_user(request)
    if graph_runner and hasattr(graph_runner, 'list_sessions'):
        sessions = graph_runner.list_sessions(user["id"])
        return {"sessions": sessions}
    return {"sessions": []}

@router.get("/history")
def get_history(request: Request, session_id: str = "default"):
    user = get_current_user(request)
    filters = {"user_id": user["id"], "session_id": session_id}
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
def clear_history(request: Request, session_id: str = "default"):
    user = get_current_user(request)
    conn = get_db()
    conn.execute(
        "DELETE FROM chat_contexts WHERE json_extract(data, '$.user_id') = ? AND json_extract(data, '$.session_id') = ?",
        (user["id"], session_id)
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
