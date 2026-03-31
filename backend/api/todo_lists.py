from fastapi import APIRouter, Request, HTTPException
from typing import Optional
from pydantic import BaseModel
from auth import get_current_user
from database import get_rows, get_row, count_rows, get_db, insert_row, update_row, delete_row, _now
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


VALID_SECTIONS = {"items", "habit_items", "mandatory_items", "overdue_items"}


class CompleteItemRequest(BaseModel):
    item_index: int
    section: Optional[str] = "items"
    metric_value: Optional[str] = None
    metric_notes: Optional[str] = None
    completion_date: Optional[str] = None  # YYYY-MM-DD, user's local date


@router.post("/{todo_id}/complete-item")
def complete_item(request: Request, todo_id: int, body: CompleteItemRequest):
    user = get_current_user(request)

    row = get_row("todo_lists", todo_id)
    if not row or row["data"].get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Todo list not found")

    section = body.section if body.section in VALID_SECTIONS else "items"
    items = row["data"].get(section, [])
    if body.item_index < 0 or body.item_index >= len(items):
        raise HTTPException(status_code=400, detail="Invalid item index")

    item = items[body.item_index]
    if not isinstance(item, dict):
        item = {"title": str(item)}
    source_type = item.get("source_type")
    source_task_id = item.get("source_task_id")

    completed_at = _now()
    completed_date = body.completion_date  # YYYY-MM-DD from client, or None

    if source_type == "one_time" and source_task_id:
        task_row = get_row("one_time_tasks", source_task_id)
        if task_row and task_row["data"].get("user_id") == user["id"]:
            task_data = task_row["data"]
            task_data["completed"] = True
            task_data["completed_at"] = completed_at
            task_data["completed_date"] = completed_date
            update_row("one_time_tasks", source_task_id, task_data)
        item["completed_task_id"] = source_task_id

    elif source_type == "recurring" and source_task_id:
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
                "completed_at": completed_at,
                "completed_date": completed_date,
                "from_recurring_id": source_task_id,
            }
            if recurring_data.get("metric"):
                one_time_data["metric_snapshot"] = recurring_data["metric"]
            if body.metric_value is not None:
                one_time_data["metric_value"] = body.metric_value
            if body.metric_notes is not None:
                one_time_data["metric_notes"] = body.metric_notes
            completed_id = insert_row("one_time_tasks", one_time_data)
            item["completed_task_id"] = completed_id

    else:
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
            "completed_at": completed_at,
            "completed_date": completed_date,
            "from_recurring_id": None,
        }
        completed_id = insert_row("one_time_tasks", one_time_data)
        item["completed_task_id"] = completed_id

    items[body.item_index] = item
    items[body.item_index]["completed"] = True

    updated_data = row["data"]
    updated_data[section] = items
    update_row("todo_lists", todo_id, updated_data)

    return get_row("todo_lists", todo_id)


class UncompleteItemRequest(BaseModel):
    item_index: int
    section: Optional[str] = "items"


@router.post("/{todo_id}/uncomplete-item")
def uncomplete_item(request: Request, todo_id: int, body: UncompleteItemRequest):
    user = get_current_user(request)

    row = get_row("todo_lists", todo_id)
    if not row or row["data"].get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Todo list not found")

    section = body.section if body.section in VALID_SECTIONS else "items"
    items = row["data"].get(section, [])
    if body.item_index < 0 or body.item_index >= len(items):
        raise HTTPException(status_code=400, detail="Invalid item index")

    item = items[body.item_index]
    if not isinstance(item, dict):
        raise HTTPException(status_code=400, detail="Item is not completable")

    source_type = item.get("source_type")
    completed_task_id = item.get("completed_task_id")

    if completed_task_id:
        if source_type == "one_time":
            # Revert the existing task to incomplete
            task_row = get_row("one_time_tasks", completed_task_id)
            if task_row and task_row["data"].get("user_id") == user["id"]:
                task_data = task_row["data"]
                task_data["completed"] = False
                task_data["completed_at"] = None
                update_row("one_time_tasks", completed_task_id, task_data)
        else:
            # For recurring and ad-hoc, we created the record — delete it
            task_row = get_row("one_time_tasks", completed_task_id)
            if task_row and task_row["data"].get("user_id") == user["id"]:
                delete_row("one_time_tasks", completed_task_id)

    item["completed"] = False
    item.pop("completed_task_id", None)
    items[body.item_index] = item

    updated_data = row["data"]
    updated_data[section] = items
    update_row("todo_lists", todo_id, updated_data)

    return get_row("todo_lists", todo_id)
