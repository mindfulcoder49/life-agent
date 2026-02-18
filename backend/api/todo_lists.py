from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from auth import get_current_user
from database import get_rows, get_row, count_rows, get_db, insert_row, update_row, _now
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


class CompleteItemRequest(BaseModel):
    item_index: int


@router.post("/{todo_id}/complete-item")
def complete_item(request: Request, todo_id: int, body: CompleteItemRequest):
    user = get_current_user(request)

    # Fetch and verify ownership
    row = get_row("todo_lists", todo_id)
    if not row or row["data"].get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Todo list not found")

    items = row["data"].get("items", [])
    if body.item_index < 0 or body.item_index >= len(items):
        raise HTTPException(status_code=400, detail="Invalid item index")

    item = items[body.item_index]
    if not isinstance(item, dict):
        item = {"title": str(item)}
    source_type = item.get("source_type")
    source_task_id = item.get("source_task_id")

    if source_type == "one_time" and source_task_id:
        # Complete the existing one-time task
        task_row = get_row("one_time_tasks", source_task_id)
        if task_row and task_row["data"].get("user_id") == user["id"]:
            task_data = task_row["data"]
            task_data["completed"] = True
            task_data["completed_at"] = _now()
            update_row("one_time_tasks", source_task_id, task_data)

    elif source_type == "recurring" and source_task_id:
        # Create a completed one-time record from the recurring task
        recurring_row = get_row("recurring_tasks", source_task_id)
        if recurring_row and recurring_row["data"].get("user_id") == user["id"]:
            recurring_data = recurring_row["data"]
            one_time_data = {
                "user_id": user["id"],
                "title": recurring_data.get("title", item.get("title", "")),
                "description": recurring_data.get("description", ""),
                "deadline": None,
                "estimated_minutes": recurring_data.get("estimated_minutes"),
                "cognitive_load": recurring_data.get("cognitive_load", 5),
                "life_goal_ids": recurring_data.get("life_goal_ids", []),
                "completed": True,
                "completed_at": _now(),
                "from_recurring_id": source_task_id,
            }
            insert_row("one_time_tasks", one_time_data)

    else:
        # Ad-hoc item — create a new completed one-time task
        title = item.get("title") if isinstance(item, dict) else str(item)
        one_time_data = {
            "user_id": user["id"],
            "title": title,
            "description": "",
            "deadline": None,
            "estimated_minutes": item.get("estimated_minutes") if isinstance(item, dict) else None,
            "cognitive_load": 5,
            "life_goal_ids": [],
            "completed": True,
            "completed_at": _now(),
            "from_recurring_id": None,
        }
        insert_row("one_time_tasks", one_time_data)

    # Mark item as completed in the todo list
    items[body.item_index] = item if isinstance(item, dict) else {"title": str(item)}
    items[body.item_index]["completed"] = True

    # Save updated todo list
    updated_data = row["data"]
    updated_data["items"] = items
    update_row("todo_lists", todo_id, updated_data)

    return get_row("todo_lists", todo_id)
