import logging
import os
from datetime import datetime, timezone

from src.services.email_service import send_email
from src.utils.db import get_connection as _conn
from src.web.db import get_user_by_id

logger = logging.getLogger(__name__)


def send_google_alert(db_path: str, user_id: int, failure_type: str, error_detail: str = "") -> None:
    """Send admin email when Google OAuth credentials fail. No-op if ADMIN_EMAIL unset."""
    try:
        admin_email = os.getenv("ADMIN_EMAIL", "")
        if not admin_email:
            return

        # Dedup: skip if alert already sent for this failure cycle
        conn = _conn(db_path)
        try:
            row = conn.execute(
                "SELECT alert_sent_at FROM google_tokens WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if row and row["alert_sent_at"]:
                return
        finally:
            conn.close()

        # Look up user email for context
        user = get_user_by_id(db_path, user_id)
        user_email = user["email"] if user else f"unknown (id={user_id})"

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        subject = f"[WeatherCal] Google OAuth {failure_type} — {user_email}"

        detail_line = f"\nError: {error_detail}" if error_detail else ""

        text_body = f"""Google OAuth failure detected.

User: {user_email} (id={user_id})
Type: {failure_type}
Time: {now}{detail_line}

This user's ICS feed is now showing a stale "moved to Google Calendar" message.
Check the dashboard or logs and reconnect if needed.

— WeatherCal alerts"""

        html_body = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:system-ui,-apple-system,sans-serif">
  <div style="max-width:560px;margin:40px auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb">
    <div style="background:#dc2626;padding:20px 32px">
      <h1 style="margin:0;color:#ffffff;font-size:1.2rem;font-weight:700">WeatherCal — OAuth Alert</h1>
    </div>
    <div style="padding:24px 32px">
      <table style="border-collapse:collapse;font-size:0.95rem;color:#111;line-height:1.7">
        <tr><td style="padding-right:16px;font-weight:600">User</td><td>{user_email} (id={user_id})</td></tr>
        <tr><td style="padding-right:16px;font-weight:600">Type</td><td>{failure_type}</td></tr>
        <tr><td style="padding-right:16px;font-weight:600">Time</td><td>{now}</td></tr>
        {"<tr><td style='padding-right:16px;font-weight:600'>Error</td><td>" + error_detail + "</td></tr>" if error_detail else ""}
      </table>
      <p style="margin:20px 0 0;font-size:0.9rem;color:#374151;line-height:1.6">
        This user's ICS feed is now showing a stale "moved to Google Calendar" message.
        Check the dashboard or logs and reconnect if needed.
      </p>
    </div>
  </div>
</body>
</html>"""

        send_email(admin_email, subject, html_body, text_body)

        # Mark alert as sent
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = _conn(db_path)
        try:
            conn.execute(
                "UPDATE google_tokens SET alert_sent_at = ? WHERE user_id = ?",
                (now_iso, user_id),
            )
            conn.commit()
        finally:
            conn.close()

    except Exception:
        logger.exception("Failed to send Google OAuth alert for user_id=%s", user_id)
