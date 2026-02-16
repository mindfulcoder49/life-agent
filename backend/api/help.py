from fastapi import APIRouter, HTTPException
from database import get_rows, get_db
import json

router = APIRouter(prefix="/api/help", tags=["help"])

@router.get("/articles")
def list_articles(category: str = None):
    filters = {}
    if category:
        filters["category"] = category
    rows = get_rows("help_articles", filters=filters, limit=200, order_desc=False)
    return {"items": rows}

@router.get("/articles/{slug}")
def get_article(slug: str):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM help_articles WHERE json_extract(data, '$.slug') = ?",
        (slug,)
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    d = dict(row)
    try:
        d["data"] = json.loads(d["data"])
    except (json.JSONDecodeError, TypeError):
        pass
    return d
