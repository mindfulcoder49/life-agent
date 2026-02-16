from fastapi import APIRouter, Request, HTTPException
from models import LifeGoalCreate, DataUpdate
from auth import get_current_user
from database import insert_row, get_row, get_rows, update_row, delete_row, count_rows

router = APIRouter(prefix="/api/life-goals", tags=["life_goals"])

@router.get("")
def list_goals(request: Request, limit: int = 50, offset: int = 0):
    user = get_current_user(request)
    rows = get_rows("life_goals", filters={"user_id": user["id"]}, limit=limit, offset=offset)
    total = count_rows("life_goals", filters={"user_id": user["id"]})
    return {"items": rows, "total": total}

@router.post("")
def create_goal(request: Request, body: LifeGoalCreate):
    user = get_current_user(request)
    data = {"user_id": user["id"], **body.model_dump()}
    row_id = insert_row("life_goals", data)
    return get_row("life_goals", row_id)

@router.get("/{goal_id}")
def get_goal(request: Request, goal_id: int):
    user = get_current_user(request)
    row = get_row("life_goals", goal_id)
    if not row or row["data"].get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Not found")
    return row

@router.put("/{goal_id}")
def update_goal(request: Request, goal_id: int, body: DataUpdate):
    user = get_current_user(request)
    row = get_row("life_goals", goal_id)
    if not row or row["data"].get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Not found")
    merged = {**row["data"], **body.data}
    merged["user_id"] = user["id"]
    update_row("life_goals", goal_id, merged)
    return get_row("life_goals", goal_id)

@router.delete("/{goal_id}")
def delete_goal(request: Request, goal_id: int):
    user = get_current_user(request)
    row = get_row("life_goals", goal_id)
    if not row or row["data"].get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Not found")
    delete_row("life_goals", goal_id)
    return {"ok": True}
