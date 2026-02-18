import sqlite3
import json
from datetime import datetime, timezone
from config import DB_PATH

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS life_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS user_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS one_time_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS recurring_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS todo_lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS help_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS chat_contexts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT
        );
    """)
    # --- Migrations ---
    # Backfill session_id='default' on chat_contexts rows that don't have it
    conn.execute("""
        UPDATE chat_contexts
        SET data = json_set(data, '$.session_id', 'default'),
            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        WHERE json_extract(data, '$.session_id') IS NULL
    """)
    conn.commit()

    conn.close()

def _now():
    return datetime.now(timezone.utc).isoformat()

def insert_row(table, data: dict) -> int:
    conn = get_db()
    now = _now()
    cur = conn.execute(
        f"INSERT INTO {table} (data, created_at, updated_at) VALUES (?, ?, ?)",
        (json.dumps(data), now, now)
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id

def get_row(table, row_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_dict(row)

def get_rows(table, filters: dict = None, limit: int = 100, offset: int = 0, order_desc: bool = True) -> list[dict]:
    conn = get_db()
    query = f"SELECT * FROM {table}"
    params = []
    if filters:
        conditions = []
        for key, value in filters.items():
            conditions.append(f"json_extract(data, '$.{key}') = ?")
            params.append(value)
        query += " WHERE " + " AND ".join(conditions)
    order = "DESC" if order_desc else "ASC"
    query += f" ORDER BY id {order} LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]

def update_row(table, row_id: int, data: dict) -> bool:
    conn = get_db()
    now = _now()
    cur = conn.execute(
        f"UPDATE {table} SET data = ?, updated_at = ? WHERE id = ?",
        (json.dumps(data), now, row_id)
    )
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed

def delete_row(table, row_id: int) -> bool:
    conn = get_db()
    cur = conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed

def count_rows(table, filters: dict = None) -> int:
    conn = get_db()
    query = f"SELECT COUNT(*) FROM {table}"
    params = []
    if filters:
        conditions = []
        for key, value in filters.items():
            conditions.append(f"json_extract(data, '$.{key}') = ?")
            params.append(value)
        query += " WHERE " + " AND ".join(conditions)
    count = conn.execute(query, params).fetchone()[0]
    conn.close()
    return count

def _row_to_dict(row) -> dict:
    d = dict(row)
    try:
        d["data"] = json.loads(d["data"])
    except (json.JSONDecodeError, TypeError):
        pass
    return d
