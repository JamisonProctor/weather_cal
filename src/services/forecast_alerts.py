"""Forecast staleness and API failure alerting.

Sends admin emails when forecast data goes stale or API failures accumulate.
No-ops gracefully if ADMIN_EMAIL or SMTP_HOST are not configured.
"""

import logging
import os
from datetime import datetime, timezone

from src.constants import (
    ALERT_COOLDOWN_HOURS,
    CONSECUTIVE_FAILURE_THRESHOLD,
    STALENESS_THRESHOLD_HOURS,
)
from src.services.email_service import send_email
from src.utils.db import get_connection as _conn

logger = logging.getLogger(__name__)


def log_refresh_result(db_path: str, tier: str, success: bool, error: str = None) -> None:
    """Record a refresh attempt in the log table."""
    conn = _conn(db_path)
    try:
        conn.execute(
            "INSERT INTO forecast_refresh_log (tier, status, created_at, error) VALUES (?, ?, ?, ?)",
            (tier, "success" if success else "failure", datetime.now(timezone.utc).isoformat(), error),
        )
        conn.commit()
    except Exception:
        logger.exception("Failed to log refresh result")
    finally:
        conn.close()


def check_consecutive_failures(db_path: str) -> tuple:
    """Check if the last N refresh attempts all failed.

    Returns (is_failing, count, last_error).
    """
    threshold = int(os.getenv("CONSECUTIVE_FAILURE_THRESHOLD", CONSECUTIVE_FAILURE_THRESHOLD))
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            "SELECT status, error FROM forecast_refresh_log ORDER BY id DESC LIMIT ?",
            (threshold,),
        ).fetchall()
        if len(rows) < threshold:
            return False, len(rows), None
        all_failed = all(r["status"] == "failure" for r in rows)
        last_error = rows[0]["error"] if rows else None
        return all_failed, len(rows), last_error
    except Exception:
        logger.exception("Failed to check consecutive failures")
        return False, 0, None
    finally:
        conn.close()


def check_staleness(db_path: str) -> tuple:
    """Check if forecast data is stale.

    Returns (is_stale, last_updated_str, hours_since_update).
    """
    threshold = float(os.getenv("STALENESS_THRESHOLD_HOURS", STALENESS_THRESHOLD_HOURS))
    conn = _conn(db_path)
    try:
        row = conn.execute("SELECT MAX(last_updated) FROM forecast").fetchone()
        if not row or not row[0]:
            return True, None, None
        last_updated = row[0]
        try:
            last_dt = datetime.fromisoformat(last_updated)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            hours_since = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
        except (ValueError, TypeError):
            return True, last_updated, None
        return hours_since >= threshold, last_updated, hours_since
    except Exception:
        logger.exception("Failed to check staleness")
        return False, None, None
    finally:
        conn.close()


def _send_stale_alert(db_path: str, last_updated: str, hours_stale: float) -> None:
    """Send a stale-data alert email, with dedup."""
    admin_email = os.getenv("ADMIN_EMAIL", "")
    if not admin_email:
        return

    cooldown = float(os.getenv("ALERT_COOLDOWN_HOURS", ALERT_COOLDOWN_HOURS))
    conn = _conn(db_path)
    try:
        # Check for active alert already sent within cooldown
        row = conn.execute(
            "SELECT alert_sent_at FROM forecast_alerts "
            "WHERE alert_type = 'stale_data' AND status = 'active' AND alert_sent_at IS NOT NULL "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row and row["alert_sent_at"]:
            try:
                sent_dt = datetime.fromisoformat(row["alert_sent_at"])
                if sent_dt.tzinfo is None:
                    sent_dt = sent_dt.replace(tzinfo=timezone.utc)
                hours_since_sent = (datetime.now(timezone.utc) - sent_dt).total_seconds() / 3600
                if hours_since_sent < cooldown:
                    return
            except (ValueError, TypeError):
                pass
    finally:
        conn.close()

    now = datetime.now(timezone.utc)
    now_str = now.strftime("%Y-%m-%d %H:%M UTC")
    hours_str = f"{hours_stale:.0f}" if hours_stale else "unknown"

    subject = f"[WeatherCal] Forecast data stale \u2014 no update in {hours_str}h"
    text_body = f"""Forecast data is stale.

Last updated: {last_updated or 'never'}
Hours since update: {hours_str}
Time: {now_str}

Check Open-Meteo API status and application logs.

\u2014 WeatherCal alerts"""

    html_body = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:system-ui,-apple-system,sans-serif">
  <div style="max-width:560px;margin:40px auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb">
    <div style="background:#dc2626;padding:20px 32px">
      <h1 style="margin:0;color:#ffffff;font-size:1.2rem;font-weight:700">WeatherCal \u2014 Stale Data Alert</h1>
    </div>
    <div style="padding:24px 32px">
      <table style="border-collapse:collapse;font-size:0.95rem;color:#111;line-height:1.7">
        <tr><td style="padding-right:16px;font-weight:600">Last Updated</td><td>{last_updated or 'never'}</td></tr>
        <tr><td style="padding-right:16px;font-weight:600">Hours Stale</td><td>{hours_str}</td></tr>
        <tr><td style="padding-right:16px;font-weight:600">Time</td><td>{now_str}</td></tr>
      </table>
      <p style="margin:20px 0 0;font-size:0.9rem;color:#374151;line-height:1.6">
        Check Open-Meteo API status and application logs.
      </p>
    </div>
  </div>
</body>
</html>"""

    send_email(admin_email, subject, html_body, text_body)

    # Record alert
    conn = _conn(db_path)
    try:
        conn.execute(
            "INSERT INTO forecast_alerts (alert_type, status, created_at, alert_sent_at, details) "
            "VALUES ('stale_data', 'active', ?, ?, ?)",
            (now.isoformat(), now.isoformat(), f"Hours stale: {hours_str}, last updated: {last_updated}"),
        )
        conn.commit()
    finally:
        conn.close()


def _send_failure_alert(db_path: str, count: int, last_error: str) -> None:
    """Send an API failure alert email, with dedup."""
    admin_email = os.getenv("ADMIN_EMAIL", "")
    if not admin_email:
        return

    cooldown = float(os.getenv("ALERT_COOLDOWN_HOURS", ALERT_COOLDOWN_HOURS))
    conn = _conn(db_path)
    try:
        row = conn.execute(
            "SELECT alert_sent_at FROM forecast_alerts "
            "WHERE alert_type = 'api_failure' AND status = 'active' AND alert_sent_at IS NOT NULL "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row and row["alert_sent_at"]:
            try:
                sent_dt = datetime.fromisoformat(row["alert_sent_at"])
                if sent_dt.tzinfo is None:
                    sent_dt = sent_dt.replace(tzinfo=timezone.utc)
                hours_since_sent = (datetime.now(timezone.utc) - sent_dt).total_seconds() / 3600
                if hours_since_sent < cooldown:
                    return
            except (ValueError, TypeError):
                pass
    finally:
        conn.close()

    now = datetime.now(timezone.utc)
    now_str = now.strftime("%Y-%m-%d %H:%M UTC")
    error_display = (last_error or "unknown")[:200]

    subject = f"[WeatherCal] API failures \u2014 {count} consecutive errors"
    text_body = f"""API failures detected.

Consecutive failures: {count}
Last error: {error_display}
Time: {now_str}

Check Open-Meteo API parameter names and application logs.

\u2014 WeatherCal alerts"""

    html_body = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:system-ui,-apple-system,sans-serif">
  <div style="max-width:560px;margin:40px auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb">
    <div style="background:#dc2626;padding:20px 32px">
      <h1 style="margin:0;color:#ffffff;font-size:1.2rem;font-weight:700">WeatherCal \u2014 API Failure Alert</h1>
    </div>
    <div style="padding:24px 32px">
      <table style="border-collapse:collapse;font-size:0.95rem;color:#111;line-height:1.7">
        <tr><td style="padding-right:16px;font-weight:600">Consecutive Failures</td><td>{count}</td></tr>
        <tr><td style="padding-right:16px;font-weight:600">Last Error</td><td>{error_display}</td></tr>
        <tr><td style="padding-right:16px;font-weight:600">Time</td><td>{now_str}</td></tr>
      </table>
      <p style="margin:20px 0 0;font-size:0.9rem;color:#374151;line-height:1.6">
        Check Open-Meteo API parameter names and application logs.
      </p>
    </div>
  </div>
</body>
</html>"""

    send_email(admin_email, subject, html_body, text_body)

    conn = _conn(db_path)
    try:
        conn.execute(
            "INSERT INTO forecast_alerts (alert_type, status, created_at, alert_sent_at, details) "
            "VALUES ('api_failure', 'active', ?, ?, ?)",
            (now.isoformat(), now.isoformat(), f"Count: {count}, error: {error_display}"),
        )
        conn.commit()
    finally:
        conn.close()


def _send_recovery_alert(db_path: str) -> None:
    """Resolve active alerts and send a recovery notification."""
    admin_email = os.getenv("ADMIN_EMAIL", "")
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            "SELECT id, alert_type, created_at FROM forecast_alerts WHERE status = 'active'"
        ).fetchall()
        if not rows:
            return

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        now_str = now.strftime("%Y-%m-%d %H:%M UTC")

        # Calculate outage duration from oldest active alert
        oldest_created = min(r["created_at"] for r in rows)
        try:
            oldest_dt = datetime.fromisoformat(oldest_created)
            if oldest_dt.tzinfo is None:
                oldest_dt = oldest_dt.replace(tzinfo=timezone.utc)
            duration_hours = (now - oldest_dt).total_seconds() / 3600
            duration_str = f"{duration_hours:.1f}h"
        except (ValueError, TypeError):
            duration_str = "unknown"

        # Resolve all active alerts
        conn.execute(
            "UPDATE forecast_alerts SET status = 'resolved', resolved_at = ?, recovery_sent_at = ? "
            "WHERE status = 'active'",
            (now_iso, now_iso),
        )
        conn.commit()

        if not admin_email:
            return

        alert_types = sorted(set(r["alert_type"] for r in rows))
        types_str = ", ".join(alert_types)

        subject = "[WeatherCal] Forecast data recovered"
        text_body = f"""Forecasts are updating again.

Resolved: {types_str}
Outage duration: {duration_str}
Recovery time: {now_str}

\u2014 WeatherCal alerts"""

        html_body = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:system-ui,-apple-system,sans-serif">
  <div style="max-width:560px;margin:40px auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb">
    <div style="background:#16a34a;padding:20px 32px">
      <h1 style="margin:0;color:#ffffff;font-size:1.2rem;font-weight:700">WeatherCal \u2014 Recovered</h1>
    </div>
    <div style="padding:24px 32px">
      <table style="border-collapse:collapse;font-size:0.95rem;color:#111;line-height:1.7">
        <tr><td style="padding-right:16px;font-weight:600">Resolved</td><td>{types_str}</td></tr>
        <tr><td style="padding-right:16px;font-weight:600">Outage Duration</td><td>{duration_str}</td></tr>
        <tr><td style="padding-right:16px;font-weight:600">Recovery Time</td><td>{now_str}</td></tr>
      </table>
      <p style="margin:20px 0 0;font-size:0.9rem;color:#374151;line-height:1.6">
        Forecasts are updating again. No action needed.
      </p>
    </div>
  </div>
</body>
</html>"""

        send_email(admin_email, subject, html_body, text_body)

    except Exception:
        logger.exception("Failed to send recovery alert")
    finally:
        conn.close()


def check_and_alert(db_path: str) -> None:
    """Orchestrator: check staleness and failures, send alerts or recovery."""
    try:
        is_stale, last_updated, hours_stale = check_staleness(db_path)
        is_failing, count, last_error = check_consecutive_failures(db_path)

        if is_stale or is_failing:
            if is_stale and hours_stale is not None:
                _send_stale_alert(db_path, last_updated, hours_stale)
            if is_failing:
                _send_failure_alert(db_path, count, last_error)
        else:
            # Everything is healthy — resolve any active alerts
            _send_recovery_alert(db_path)
    except Exception:
        logger.exception("check_and_alert failed")
