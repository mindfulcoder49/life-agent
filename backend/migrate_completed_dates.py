"""
Migration: backfill completed_date for old task completion records.

Old records have completed_at (UTC ISO) but no completed_date field.
This script converts completed_at → user's local date and writes it as completed_date.

Safe to run multiple times — skips rows that already have completed_date set.

Usage:
    cd backend && venv/bin/python3 migrate_completed_dates.py [--dry-run]
"""

import sys
import json
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from config import DB_PATH

DRY_RUN = "--dry-run" in sys.argv


def get_user_tz(conn, user_id: int) -> ZoneInfo:
    row = conn.execute("SELECT data FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        return ZoneInfo("UTC")
    try:
        data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
        tz_str = data.get("timezone") or "UTC"
        return ZoneInfo(tz_str)
    except (ZoneInfoNotFoundError, Exception):
        return ZoneInfo("UTC")


def utc_iso_to_local_date(completed_at: str, tz: ZoneInfo) -> str:
    """Convert a UTC ISO timestamp string to a local YYYY-MM-DD date string."""
    # Handle both 'Z' suffix and '+00:00'
    ts = completed_at.replace("Z", "+00:00")
    dt = datetime.fromisoformat(ts).astimezone(tz)
    return dt.date().isoformat()


def migrate():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT id, data
        FROM one_time_tasks
        WHERE json_extract(data, '$.completed') = 1
          AND json_extract(data, '$.completed_at') IS NOT NULL
          AND json_extract(data, '$.completed_date') IS NULL
        """
    ).fetchall()

    print(f"Found {len(rows)} rows to migrate.")
    if DRY_RUN:
        print("(dry run — no changes will be written)")

    updated = 0
    skipped = 0

    # Cache user timezones to avoid repeated lookups
    tz_cache: dict[int, ZoneInfo] = {}

    for row in rows:
        data = json.loads(row["data"]) if isinstance(row["data"], str) else dict(row["data"])
        user_id = data.get("user_id")
        completed_at = data.get("completed_at")

        if not user_id or not completed_at:
            skipped += 1
            continue

        if user_id not in tz_cache:
            tz_cache[user_id] = get_user_tz(conn, user_id)
        tz = tz_cache[user_id]

        try:
            local_date = utc_iso_to_local_date(completed_at, tz)
        except Exception as e:
            print(f"  SKIP id={row['id']}: could not parse completed_at={completed_at!r}: {e}")
            skipped += 1
            continue

        utc_date = completed_at[:10]
        if local_date != utc_date:
            flag = " <-- date shifted"
        else:
            flag = ""

        print(f"  id={row['id']} user={user_id} tz={tz.key}  {utc_date} -> {local_date}{flag}")

        if not DRY_RUN:
            data["completed_date"] = local_date
            conn.execute(
                "UPDATE one_time_tasks SET data = ? WHERE id = ?",
                (json.dumps(data), row["id"])
            )
        updated += 1

    if not DRY_RUN:
        conn.commit()

    conn.close()
    print(f"\nDone. {updated} updated, {skipped} skipped.")
    if DRY_RUN:
        print("Re-run without --dry-run to apply.")


if __name__ == "__main__":
    migrate()
