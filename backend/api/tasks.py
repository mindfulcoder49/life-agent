from fastapi import APIRouter, Request, HTTPException
from typing import Optional
from models import OneTimeTaskCreate, RecurringTaskCreate, RecurringCompleteRequest, DataUpdate
from auth import get_current_user
from database import insert_row, get_row, get_rows, update_row, delete_row, count_rows, _now

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

# --- One-time tasks ---

@router.get("/one-time")
def list_one_time(request: Request, limit: int = 50, offset: int = 0):
    user = get_current_user(request)
    rows = get_rows("one_time_tasks", filters={"user_id": user["id"]}, limit=limit, offset=offset)
    total = count_rows("one_time_tasks", filters={"user_id": user["id"]})
    return {"items": rows, "total": total}

@router.post("/one-time")
def create_one_time(request: Request, body: OneTimeTaskCreate):
    user = get_current_user(request)
    data = {"user_id": user["id"], "completed": False, "completed_at": None, "from_recurring_id": None, **body.model_dump()}
    row_id = insert_row("one_time_tasks", data)
    return get_row("one_time_tasks", row_id)

@router.get("/one-time/{task_id}")
def get_one_time(request: Request, task_id: int):
    user = get_current_user(request)
    row = get_row("one_time_tasks", task_id)
    if not row or row["data"].get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Not found")
    return row

@router.put("/one-time/{task_id}")
def update_one_time(request: Request, task_id: int, body: DataUpdate):
    user = get_current_user(request)
    row = get_row("one_time_tasks", task_id)
    if not row or row["data"].get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Not found")
    merged = {**row["data"], **body.data}
    merged["user_id"] = user["id"]
    update_row("one_time_tasks", task_id, merged)
    return get_row("one_time_tasks", task_id)

@router.delete("/one-time/{task_id}")
def delete_one_time(request: Request, task_id: int):
    user = get_current_user(request)
    row = get_row("one_time_tasks", task_id)
    if not row or row["data"].get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Not found")
    delete_row("one_time_tasks", task_id)
    return {"ok": True}

@router.post("/one-time/{task_id}/complete")
def complete_one_time(request: Request, task_id: int):
    user = get_current_user(request)
    row = get_row("one_time_tasks", task_id)
    if not row or row["data"].get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Not found")
    data = row["data"]
    data["completed"] = True
    data["completed_at"] = _now()
    update_row("one_time_tasks", task_id, data)
    return get_row("one_time_tasks", task_id)

# --- Recurring tasks ---

@router.get("/recurring")
def list_recurring(request: Request, limit: int = 50, offset: int = 0):
    user = get_current_user(request)
    rows = get_rows("recurring_tasks", filters={"user_id": user["id"]}, limit=limit, offset=offset)
    total = count_rows("recurring_tasks", filters={"user_id": user["id"]})
    return {"items": rows, "total": total}

@router.post("/recurring")
def create_recurring(request: Request, body: RecurringTaskCreate):
    user = get_current_user(request)
    data = {"user_id": user["id"], "active": True, **body.model_dump()}
    row_id = insert_row("recurring_tasks", data)
    return get_row("recurring_tasks", row_id)

@router.get("/recurring/{task_id}")
def get_recurring(request: Request, task_id: int):
    user = get_current_user(request)
    row = get_row("recurring_tasks", task_id)
    if not row or row["data"].get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Not found")
    return row

@router.put("/recurring/{task_id}")
def update_recurring(request: Request, task_id: int, body: DataUpdate):
    user = get_current_user(request)
    row = get_row("recurring_tasks", task_id)
    if not row or row["data"].get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Not found")
    merged = {**row["data"], **body.data}
    merged["user_id"] = user["id"]
    update_row("recurring_tasks", task_id, merged)
    return get_row("recurring_tasks", task_id)

@router.delete("/recurring/{task_id}")
def delete_recurring(request: Request, task_id: int):
    user = get_current_user(request)
    row = get_row("recurring_tasks", task_id)
    if not row or row["data"].get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Not found")
    delete_row("recurring_tasks", task_id)
    return {"ok": True}

@router.post("/recurring/{task_id}/complete")
def complete_recurring(request: Request, task_id: int, body: Optional[RecurringCompleteRequest] = None):
    user = get_current_user(request)
    row = get_row("recurring_tasks", task_id)
    if not row or row["data"].get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Not found")
    recurring_data = row["data"]
    one_time_data = {
        "user_id": user["id"],
        "title": recurring_data["title"],
        "description": recurring_data.get("description", ""),
        "estimated_minutes": recurring_data.get("estimated_minutes"),
        "cognitive_load": recurring_data.get("cognitive_load", 5),
        "life_goal_ids": recurring_data.get("life_goal_ids", []),
        "completed": True,
        "completed_at": _now(),
        "from_recurring_id": task_id,
    }
    if recurring_data.get("metric"):
        one_time_data["metric_snapshot"] = recurring_data["metric"]
    if body:
        if body.metric_value is not None:
            one_time_data["metric_value"] = body.metric_value
        if body.metric_notes is not None:
            one_time_data["metric_notes"] = body.metric_notes
        if body.est_calories is not None:
            one_time_data["est_calories"] = body.est_calories
        if body.est_protein_g is not None:
            one_time_data["est_protein_g"] = body.est_protein_g
        if body.est_carbs_g is not None:
            one_time_data["est_carbs_g"] = body.est_carbs_g
        if body.est_fat_g is not None:
            one_time_data["est_fat_g"] = body.est_fat_g
    completed_id = insert_row("one_time_tasks", one_time_data)
    return {"ok": True, "completed_record_id": completed_id, "message": "Recurring task completed"}
