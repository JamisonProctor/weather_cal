# GDPR Data Retention Compliance

## Context
The privacy policy is live and the data handling code (deletion cleanup, data export) has been implemented. Two GDPR gaps remain:

1. **Poll logs store IP addresses forever** — IP addresses are PII under GDPR. The `poll_log` table accumulates indefinitely with no purge mechanism. Art. 5(1)(c) (data minimization) and Art. 5(1)(e) (storage limitation) require a retention limit.

2. **Soft-deleted user rows retain PII forever** — When a user deletes their account, the `users` row (email, password_hash) persists with `is_active=0`. All linked data is now cleaned up, but the core PII in the user row stays. Art. 17 (right to erasure) requires eventual removal.

Both gaps are already identified in the Obsidian plan (`WeatherCal Google OAuth Setup.md` → Part 1.5 → Step 2).

## Changes

### 1. Add `purge_old_poll_logs()` to `src/web/db.py`
Delete poll_log entries older than 90 days:
```python
def purge_old_poll_logs(db_path: str) -> int:
    cutoff = (datetime.now() - timedelta(days=90)).isoformat()
    conn = _conn(db_path)
    try:
        cur = conn.execute("DELETE FROM poll_log WHERE polled_at < ?", (cutoff,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
```

### 2. Add `hard_delete_inactive_users()` to `src/web/db.py`
Hard-delete user rows that have been soft-deleted for 30+ days. Need to track *when* soft-delete happened — add a `deactivated_at` column to `users` table.

- Add migration in `ForecastStore._init_db()` (in `src/services/forecast_store.py`, near line 72 with the other ALTER TABLE migrations): `ALTER TABLE users ADD COLUMN deactivated_at TEXT`
- Update `delete_user_account()` to set `deactivated_at = datetime.now().isoformat()` alongside `is_active = 0`
- New function:
```python
def hard_delete_inactive_users(db_path: str) -> int:
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()
    conn = _conn(db_path)
    try:
        cur = conn.execute(
            "DELETE FROM users WHERE is_active = 0 AND deactivated_at IS NOT NULL AND deactivated_at < ?",
            (cutoff,)
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
```

### 3. Run purge tasks in daily scheduler — `src/app/main.py`
Add calls to both purge functions at the top of `main()` (the daily job, runs at `SCHEDULE_TIME`, default 00:23). Log the counts. Import from `src.web.db`.

### 4. Update privacy policy — `src/web/templates/privacy.html`
Add a "Data Retention" section stating:
- Poll logs (including IP addresses) are automatically deleted after 90 days
- Deactivated accounts are permanently deleted after 30 days

### 5. Tests — `src/tests/test_web_db.py` or `src/tests/test_web_routes.py`
- `purge_old_poll_logs()` deletes entries older than 90 days, keeps recent ones
- `hard_delete_inactive_users()` deletes users deactivated 30+ days ago, keeps recent deactivations
- `delete_user_account()` sets `deactivated_at`

## Files to modify
- `src/services/forecast_store.py` — add `deactivated_at` column migration in `_init_db()` (~line 72)
- `src/web/db.py` — add `purge_old_poll_logs()`, `hard_delete_inactive_users()`, update `delete_user_account()` to set `deactivated_at`
- `src/app/main.py` — call both purge functions at top of `main()`
- `src/web/templates/privacy.html` — add "Data Retention" section between "How We Store" and "What We Share"
- `src/tests/test_web_routes.py` — tests for purge functions and deactivated_at

## Verification
- `python -m pytest src/tests/ -q --tb=short`
- Manually verify: create user → delete account → confirm `deactivated_at` is set → verify hard-delete function removes row after cutoff
