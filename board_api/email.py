"""Outbound email notifications for lakeAlliance.

Transport is Gmail SMTP (smtplib, stdlib — no extra dependency). We use a Gmail
account + an app password because the app owns no sending domain; Gmail delivers
to any recipient, unlike Resend's shared onboarding@ sender (owner-only). The
account is set via GMAIL_USER / GMAIL_APP_PASSWORD (a 16-char Google App Password,
which requires 2-Step Verification on that Google account).

Best-effort by design: a transport failure is logged and swallowed (by _safe or
per-recipient inside _fanout) so it never breaks the HTTP request that triggered
it (signup / post / EOI stay 200/201).

Delivery & privacy: a fan-out (a new use case → every partner) sends ONE
individual message per recipient, with that recipient's address in the visible
To. This keeps recipients private (each person only ever sees their own address)
AND improves inbox placement — a single Bcc blast with no real To recipient is a
strong spam-filter signal, which is why an earlier Bcc version landed in Spam.
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


def _connect() -> smtplib.SMTP_SSL:
    """Open an authenticated Gmail SMTP connection. Raises if creds are missing.

    Timeout is well under the serverless function budget so a hung SMTP call
    can't cascade into a platform 504 on the triggering request.
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        raise RuntimeError("GMAIL_USER / GMAIL_APP_PASSWORD not set")
    s = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=8)
    s.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    return s


def _build(to_email: str, subject: str, body: str) -> EmailMessage:
    """Build one plain-text message addressed (visible To) to a single recipient."""
    msg = EmailMessage()
    msg["From"] = f"{FROM_NAME} <{GMAIL_USER}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def _send(to: list[str], subject: str, body: str) -> None:
    """Send ONE message with every address in `to` in the visible To header.

    Used for single-recipient mail (e.g. welcome). Raises on missing creds or
    SMTP error so _safe() logs and swallows it. Keep the signature stable — the
    send_* helpers and the tests depend on it.
    """
    if not to:
        return
    with _connect() as s:
        s.send_message(_build(", ".join(to), subject, body))


def _safe(to: list[str], subject: str, body: str) -> None:
    """Best-effort single send: log and swallow any transport error."""
    try:
        _send(to, subject, body)
    except Exception as e:  # noqa: BLE001 - notifications must never break requests
        log.warning("email send failed (to=%s subj=%r): %s", to, subject, e)


def _fanout(recipients: list[str], subject: str, body: str) -> None:
    """Send an INDIVIDUAL copy to each recipient over one SMTP connection.

    Each message carries only that recipient's address in To — so no one sees
    another's address, and there is a real To recipient (better deliverability
    than a Bcc blast). Best-effort per recipient: one bad address is logged and
    skipped without blocking the rest; a connect/login failure is swallowed so
    the triggering request never breaks.
    """
    # Dedupe (preserve order) and drop empties.
    recips = [r for r in dict.fromkeys(recipients) if r]
    if not recips:
        return
    try:
        with _connect() as s:
            for r in recips:
                try:
                    s.send_message(_build(r, subject, body))
                except Exception as e:  # noqa: BLE001 - one bad recipient must not stop the rest
                    log.warning("email send failed to %s (subj=%r): %s", r, subject, e)
    except Exception as e:  # noqa: BLE001 - connect/login failure must never break the request
        log.warning("email fanout connect/login failed (subj=%r): %s", subject, e)


def send_welcome(to_email: str, company: str) -> None:
    _safe([to_email],
          "You're in — lakeAlliance",
          f"Thanks for joining as {company}.\n\n"
          "We'll email you whenever a new use case is posted that you might be "
          "able to help with. You can browse the board any time.")


def send_new_use_case(to_emails: list[str], title: str, description: str,
                      board_url: str) -> None:
    # One individual email per partner (own address in To) — private + better
    # inbox placement than a Bcc blast.
    _fanout(to_emails,
            f"New partner use case: {title}",
            f"{title}\n\n{description}\n\nSee it on the board: {board_url}")


def send_new_eoi(to_emails: list[str], company: str, title: str,
                 approach: str) -> None:
    # One individual email per (internal) notify recipient.
    _fanout(to_emails,
            f"New response to “{title}” from {company}",
            f"{company} expressed interest in: {title}\n\n"
            f"Their approach:\n{approach}")
