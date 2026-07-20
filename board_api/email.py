"""Outbound email notifications for lakeAlliance.

Transport is Gmail SMTP (smtplib, stdlib — no extra dependency). We use a Gmail
account + an app password because the app owns no sending domain; Gmail delivers
to any recipient, unlike Resend's shared onboarding@ sender (owner-only). The
account is set via GMAIL_USER / GMAIL_APP_PASSWORD (a 16-char Google App Password,
which requires 2-Step Verification on that Google account).

Best-effort by design: a transport failure is logged and swallowed by _safe() so
it never breaks the HTTP request that triggered it (signup / post / EOI stay
200/201).

Privacy: multi-recipient notifications (a new use case → every partner) are sent
with the recipients in **Bcc**, never the visible To — so partners never see one
another's email addresses. Single-recipient mail (welcome) uses To normally.
"""
import logging
import os
import smtplib
from email.message import EmailMessage  # stdlib email pkg (absolute import; not this module)

log = logging.getLogger("board.email")

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))          # SSL
GMAIL_USER = os.environ.get("GMAIL_USER", "")                # the sending Gmail address
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")  # 16-char Google App Password
FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "lakeAlliance")  # friendly display name


def _send(to: list[str], subject: str, body: str, bcc: list[str] | None = None) -> None:
    """Deliver one message via Gmail SMTP.

    `to` addresses appear in the visible To header; `bcc` addresses are delivered
    but never appear in any header (recipient privacy). Raises on missing
    credentials or SMTP error so _safe() logs and swallows it. Keep the signature
    stable — the send_* helpers and the tests depend on it.
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        raise RuntimeError("GMAIL_USER / GMAIL_APP_PASSWORD not set")

    envelope = list(to) + list(bcc or [])
    if not envelope:
        return  # nothing to deliver

    msg = EmailMessage()
    msg["From"] = f"{FROM_NAME} <{GMAIL_USER}>"
    msg["To"] = ", ".join(to) or GMAIL_USER  # never leave To empty
    msg["Subject"] = subject
    msg.set_content(body)

    # Timeout well under the serverless function budget so a hung SMTP call can't
    # cascade into a platform 504 on the triggering request.
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=8) as s:
        s.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        # Explicit to_addrs = the full envelope, so Bcc recipients are delivered
        # without a Bcc header ever being written.
        s.send_message(msg, to_addrs=envelope)


def _safe(to: list[str], subject: str, body: str, bcc: list[str] | None = None) -> None:
    """Best-effort send: log and swallow any transport error."""
    try:
        _send(to, subject, body, bcc=bcc)
    except Exception as e:  # noqa: BLE001 - notifications must never break requests
        log.warning("email send failed (to=%s bcc=%s subj=%r): %s", to, bcc, subject, e)


def _fanout(recipients: list[str], subject: str, body: str) -> None:
    """Send one message to many recipients, each hidden from the others via Bcc.

    The visible To is the sending account itself, so there is a valid To header
    and the owner also gets a copy; every real recipient is in Bcc.
    """
    if not recipients:
        return
    _safe([GMAIL_USER], subject, body, bcc=recipients)


def send_welcome(to_email: str, company: str) -> None:
    _safe([to_email],
          "You're in — lakeAlliance",
          f"Thanks for joining as {company}.\n\n"
          "We'll email you whenever a new use case is posted that you might be "
          "able to help with. You can browse the board any time.")


def send_new_use_case(to_emails: list[str], title: str, description: str,
                      board_url: str) -> None:
    # Bcc every partner so recipients never see one another's addresses.
    _fanout(to_emails,
            f"New partner use case: {title}",
            f"{title}\n\n{description}\n\nSee it on the board: {board_url}")


def send_new_eoi(to_emails: list[str], company: str, title: str,
                 approach: str) -> None:
    # Bcc the (internal) notify recipients too, for consistency and safety.
    _fanout(to_emails,
            f"New response to “{title}” from {company}",
            f"{company} expressed interest in: {title}\n\n"
            f"Their approach:\n{approach}")
