from fastapi import APIRouter, Request, HTTPException
from models import HelpArticleCreate, DataUpdate
from auth import require_admin
from database import get_rows, get_row, delete_row, insert_row, update_row, count_rows, get_db
import json

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
