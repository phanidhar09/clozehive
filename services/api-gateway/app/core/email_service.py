"""
Email delivery service.

Provider is selected by EMAIL_PROVIDER:
  • console — log the email instead of sending (default; safe for local dev/tests).
  • smtp    — send via SMTP (dev: Mailpit at smtp://mailpit:1025, no auth/TLS).
  • resend  — send via the Resend HTTP API (production).

All send functions swallow and log delivery errors rather than raising: callers
like /forgot-password must return the same generic 202 whether or not the email
went out, so a provider outage can't leak account existence or 500 the endpoint.
Failures are visible via the error log (and Sentry, when configured).
"""

from __future__ import annotations

from email.message import EmailMessage

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger("email_service")

_RESEND_API_URL = "https://api.resend.com/emails"


async def _send_via_smtp(msg: EmailMessage) -> None:
    import aiosmtplib

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username or None,
        password=settings.smtp_password or None,
        use_tls=settings.smtp_use_tls,
        start_tls=settings.smtp_starttls or None,  # None = auto-negotiate
        timeout=15,
    )


async def _send_via_resend(to: str, subject: str, html: str, text: str) -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.email_from,
                "to": [to],
                "subject": subject,
                "html": html,
                "text": text,
            },
        )
        resp.raise_for_status()


async def send_email(to: str, subject: str, html: str, text: str) -> bool:
    """Send an email via the configured provider. Returns True on success.

    Never raises — see module docstring.
    """
    provider = settings.email_provider.lower()
    try:
        if provider == "console":
            logger.info(
                "email_console_delivery",
                to=to,
                subject=subject,
                body_text=text,
            )
            return True
        if provider == "smtp":
            msg = EmailMessage()
            msg["From"] = settings.email_from
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(text)
            msg.add_alternative(html, subtype="html")
            await _send_via_smtp(msg)
        elif provider == "resend":
            if not settings.resend_api_key:
                logger.error("email_send_failed", to=to, reason="RESEND_API_KEY is not set")
                return False
            await _send_via_resend(to, subject, html, text)
        else:
            logger.error("email_send_failed", to=to, reason=f"unknown EMAIL_PROVIDER {provider!r}")
            return False
        logger.info("email_sent", to=to, subject=subject, provider=provider)
        return True
    except Exception as exc:  # noqa: BLE001 — delivery failure must not propagate
        logger.error("email_send_failed", to=to, provider=provider, error=str(exc))
        return False


def _layout(title: str, body_html: str) -> str:
    """Minimal, client-safe HTML wrapper (inline styles only)."""
    return f"""\
<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background:#f6f5f3;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr><td align="center" style="padding:32px 16px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="max-width:480px;background:#ffffff;border-radius:12px;padding:32px;">
          <tr><td style="font-size:20px;font-weight:700;color:#1a1a1a;padding-bottom:16px;">
            Clozehive
          </td></tr>
          <tr><td style="font-size:16px;font-weight:600;color:#1a1a1a;padding-bottom:12px;">
            {title}
          </td></tr>
          <tr><td style="font-size:14px;line-height:1.6;color:#444444;">
            {body_html}
          </td></tr>
          <tr><td style="font-size:12px;color:#999999;padding-top:24px;">
            If you didn't request this, you can safely ignore this email.
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""


async def send_password_reset(email: str, reset_url: str) -> bool:
    """Send the password-reset link. The link expires in 30 minutes."""
    subject = "Reset your Clozehive password"
    text = (
        "We received a request to reset your Clozehive password.\n\n"
        f"Reset it here (link expires in 30 minutes):\n{reset_url}\n\n"
        "If you didn't request this, you can safely ignore this email."
    )
    html = _layout(
        "Reset your password",
        "We received a request to reset your Clozehive password. "
        "Click the button below to choose a new one. "
        "This link expires in <strong>30 minutes</strong>."
        f"""<div style="padding:20px 0;">
          <a href="{reset_url}"
             style="background:#1a1a1a;color:#ffffff;text-decoration:none;
                    padding:12px 24px;border-radius:8px;font-size:14px;font-weight:600;display:inline-block;">
            Reset password
          </a>
        </div>
        <div style="font-size:12px;color:#777777;word-break:break-all;">
          Or paste this link into your browser:<br>{reset_url}
        </div>""",
    )
    return await send_email(to=email, subject=subject, html=html, text=text)
