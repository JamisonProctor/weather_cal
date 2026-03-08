import hashlib
import sqlite3
import uuid
from datetime import datetime


def _external_key(source_url: str, start_time: str) -> str:
    raw = f"{source_url}|{start_time}"
    return hashlib.sha256(raw.encode()).hexdigest()


def store_events(db_path: str, events: list[dict], now: datetime) -> dict:
    """Store extracted events idempotently.

    - external_key = sha256(source_url + "|" + start_time)
    - If external_key exists: update fields if changed
    - If external_key is new: insert
    - Discard events with end_time before now
    - Return {"created": int, "updated": int, "discarded_past": int}
    """
    stats = {"created": 0, "updated": 0, "discarded_past": 0}
    if not events:
        return stats

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        for event in events:
            start_time = event.get("start_time", "")
            end_time = event.get("end_time", start_time)
            source_url = event.get("source_url", "")

            # Discard past events
            try:
                if datetime.fromisoformat(end_time) < now:
                    stats["discarded_past"] += 1
                    continue
            except (ValueError, TypeError):
                stats["discarded_past"] += 1
                continue

            ext_key = _external_key(source_url, start_time)

            existing = conn.execute(
                "SELECT * FROM events WHERE external_key = ?", (ext_key,)
            ).fetchone()

            if existing:
                # Check if anything changed
                changed = False
                for field in ("title", "location", "description", "category"):
                    if event.get(field) != existing[field]:
                        changed = True
                        break
                if not changed:
                    is_paid_val = 1 if event.get("is_paid") else 0
                    if is_paid_val != existing["is_paid"]:
                        changed = True

                if changed:
                    conn.execute(
                        """UPDATE events SET title=?, location=?, description=?,
                           category=?, is_paid=?, source_url=?
                           WHERE external_key=?""",
                        (
                            event.get("title", ""),
                            event.get("location", ""),
                            event.get("description", ""),
                            event.get("category"),
                            1 if event.get("is_paid") else 0,
                            source_url,
                            ext_key,
                        ),
                    )
                    stats["updated"] += 1
            else:
                conn.execute(
                    """INSERT INTO events
                       (id, title, start_time, end_time, location, description,
                        source_url, external_key, category, is_paid, is_calendar_candidate, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                    (
                        str(uuid.uuid4()),
                        event.get("title", ""),
                        start_time,
                        end_time,
                        event.get("location", ""),
                        event.get("description", ""),
                        source_url,
                        ext_key,
                        event.get("category"),
                        1 if event.get("is_paid") else 0,
                        now.isoformat(),
                    ),
                )
                stats["created"] += 1

        conn.commit()
    finally:
        conn.close()

    return stats
