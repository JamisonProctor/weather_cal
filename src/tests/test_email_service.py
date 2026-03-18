import os
from unittest.mock import MagicMock, patch

from src.services.email_service import send_email, send_welcome_email


def test_send_welcome_email_skips_when_unconfigured():
    """With SMTP_HOST unset, calling send_welcome_email should not raise."""
    env = {k: v for k, v in os.environ.items() if k != "SMTP_HOST"}
    with patch.dict(os.environ, env, clear=True):
        send_welcome_email(
            "user@example.com",
            "webcal://example.com/feed/token/weather.ics",
            "Munich",
        )


def test_send_welcome_email_calls_smtp():
    """When SMTP_HOST is set, sendmail is called with the correct to address."""
    mock_smtp = MagicMock()
    mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
    mock_smtp.__exit__ = MagicMock(return_value=False)

    with patch.dict(os.environ, {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "587",
        "SMTP_USER": "sender@example.com",
        "SMTP_PASSWORD": "secret",
    }):
        with patch("smtplib.SMTP", return_value=mock_smtp):
            send_welcome_email(
                "user@example.com",
                "webcal://example.com/feed/token/weather.ics",
                "Munich",
            )

    mock_smtp.sendmail.assert_called_once()
    _, to_addr, _ = mock_smtp.sendmail.call_args[0]
    assert to_addr == "user@example.com"


def test_send_welcome_email_contains_feedback_email():
    """Welcome email body includes hello@weathercal.app for feedback."""
    with patch.dict(os.environ, {"SMTP_HOST": "smtp.example.com", "SMTP_USER": "x", "SMTP_PASSWORD": "x"}):
        with patch("smtplib.SMTP") as mock_cls:
            mock_smtp = MagicMock()
            mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
            mock_smtp.__exit__ = MagicMock(return_value=False)
            mock_cls.return_value = mock_smtp
            send_welcome_email("user@example.com", "webcal://x", "Munich")
            _, _, msg_str = mock_smtp.sendmail.call_args[0]
            assert "hello@weathercal.app" in msg_str

