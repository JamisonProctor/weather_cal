import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, html_body: str, text_body: str) -> None:
    """Send via SMTP TLS. No-op if SMTP_HOST not configured."""
    host = os.getenv("SMTP_HOST", "")
    if not host:
        return

    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    from_addr = os.getenv("SMTP_FROM", user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(host, port) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(user, password)
            smtp.sendmail(from_addr, to, msg.as_string())
        logger.info("Email sent to %s", to)
    except Exception:
        logger.exception("Failed to send email to %s", to)


def send_welcome_email(to_email: str, webcal_url: str, location: str) -> None:
    """Build and send the welcome email."""
    subject = "Welcome to WeatherCal \u2600\ufe0f \u2014 your forecast is ready"

    html_body = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:system-ui,-apple-system,sans-serif">
  <div style="max-width:560px;margin:40px auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb">
    <div style="background:#2563eb;padding:28px 32px">
      <h1 style="margin:0;color:#ffffff;font-size:1.4rem;font-weight:700">WeatherCal \u2600\ufe0f</h1>
    </div>
    <div style="padding:32px">
      <p style="margin:0 0 16px;font-size:1rem;color:#111;line-height:1.6">
        Your weather feed for <strong>{location}</strong> is ready. Subscribe once and your calendar app will show 14-day forecasts updated every morning.
      </p>
      <p style="margin:0 0 28px;font-size:0.95rem;color:#374151;line-height:1.6">
        Click the button below to add it to your calendar app.
      </p>
      <a href="{webcal_url}" style="display:inline-block;padding:14px 28px;background:#2563eb;color:#ffffff;text-decoration:none;border-radius:8px;font-size:1rem;font-weight:600">
        Add to calendar
      </a>
      <div style="margin-top:32px;padding-top:24px;border-top:1px solid #f3f4f6">
        <p style="margin:0 0 8px;font-size:0.9rem;font-weight:600;color:#374151">What to expect:</p>
        <ul style="margin:0;padding-left:20px;color:#374151;font-size:0.9rem;line-height:1.7">
          <li>Daily summaries with emoji weather forecasts (e.g. &#x26C5; 12&#176;C)</li>
          <li>Warning events for rain &#x2602;&#xFE0F;, wind &#x1F32C;&#xFE0F;, cold &#x1F976;, snow &#x2603;&#xFE0F;, and heat &#x1F975;</li>
          <li>Weather alerts showing exactly when bad weather arrives</li>
        </ul>
      </div>
    </div>
    <div style="padding:20px 32px;background:#f9fafb;border-top:1px solid #e5e7eb;text-align:center">
      <p style="margin:0 0 6px;font-size:0.85rem;color:#6b7280">Respond to this email or reach out anytime at <a href="mailto:hello@weathercal.app" style="color:#2563eb;text-decoration:none">hello@weathercal.app</a></p>
      <p style="margin:0;font-size:0.8rem;color:#9ca3af">weathercal.app \u2014 weather in your calendar</p>
    </div>
  </div>
</body>
</html>"""

    text_body = f"""Welcome to WeatherCal!

Your weather feed for {location} is ready.

Add it to your calendar app using this URL:
{webcal_url}

What to expect:
- Daily summaries with emoji weather forecasts
- Warning events for rain, wind, cold, snow, and heat
- Weather alerts showing exactly when bad weather arrives

Respond to this email or reach out anytime at hello@weathercal.app

-- weathercal.app"""

    send_email(to_email, subject, html_body, text_body)


