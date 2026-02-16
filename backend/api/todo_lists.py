from fastapi import APIRouter, Request
from auth import get_current_user
from database import get_rows, count_rows, get_db
import json

router = APIRouter(prefix="/api/todo-lists", tags=["todo_lists"])

@router.get("")
def list_todos(request: Request, limit: int = 50, offset: int = 0):
    user = get_current_user(request)
    rows = get_rows("todo_lists", filters={"user_id": user["id"]}, limit=limit, offset=offset)
    total = count_rows("todo_lists", filters={"user_id": user["id"]})
    return {"items": rows, "total": total}

@router.get("/by-date/{date}")
def get_by_date(request: Request, date: str):
    user = get_current_user(request)
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM todo_lists WHERE json_extract(data, '$.user_id') = ? AND json_extract(data, '$.date') = ?",
        (user["id"], date)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    d = dict(row)
    try:
        d["data"] = json.loads(d["data"])
    except (json.JSONDecodeError, TypeError):
        pass
    return d
