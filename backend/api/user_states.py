from fastapi import APIRouter, Request, HTTPException
from models import UserStateCreate, DataUpdate
from auth import get_current_user
from database import insert_row, get_row, get_rows, update_row, delete_row, count_rows

router = APIRouter(prefix="/api/user-states", tags=["user_states"])

@router.get("")
def list_states(request: Request, limit: int = 50, offset: int = 0):
    user = get_current_user(request)
    rows = get_rows("user_states", filters={"user_id": user["id"]}, limit=limit, offset=offset)
    total = count_rows("user_states", filters={"user_id": user["id"]})
    return {"items": rows, "total": total}

@router.post("")
def create_state(request: Request, body: UserStateCreate):
    user = get_current_user(request)
    data = {"user_id": user["id"], **body.model_dump()}
    row_id = insert_row("user_states", data)
    return get_row("user_states", row_id)

@router.get("/{state_id}")
def get_state(request: Request, state_id: int):
    user = get_current_user(request)
    row = get_row("user_states", state_id)
    if not row or row["data"].get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Not found")
    return row

@router.put("/{state_id}")
def update_state(request: Request, state_id: int, body: DataUpdate):
    user = get_current_user(request)
    row = get_row("user_states", state_id)
    if not row or row["data"].get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Not found")
    merged = {**row["data"], **body.data}
    merged["user_id"] = user["id"]
    update_row("user_states", state_id, merged)
    return get_row("user_states", state_id)

@router.delete("/{state_id}")
def delete_state(request: Request, state_id: int):
    user = get_current_user(request)
    row = get_row("user_states", state_id)
    if not row or row["data"].get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Not found")
    delete_row("user_states", state_id)
    return {"ok": True}
