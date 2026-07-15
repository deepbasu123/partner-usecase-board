"""Outbound email notifications for the Partner Use-Case Board.

Shared by both surfaces (partner portal + admin app). Best-effort by design:
a transport failure is logged and swallowed so it never breaks the HTTP
request that triggered it.

CANONICAL COPY. This file lives in common/ and is copied verbatim into each
backend package (portal_backend/email.py, admin-app/backend/email.py) so each
can `from . import email`. Edit here, then re-copy.

The concrete transport (_send) is chosen during the Task 0 spike (Gmail API or
an SMTP relay) and wired in only after explicit approval to send external mail.
Until then _send raises NotImplementedError; callers still succeed because
_safe() swallows it, and tests mock _send.
"""
import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger("board.email")

FROM_ADDR = os.environ.get("EMAIL_FROM", "onboarding@resend.dev")


RESEND_ENDPOINT = "https://api.resend.com/emails"


def _send(to: list[str], subject: str, body: str) -> None:
    """Deliver via Resend's REST API using stdlib urllib (no extra dep).

    Raises on missing key or non-2xx so _safe() logs and swallows it. Keep this
    signature stable — send_* and the tests depend on it.
    """
    key = os.environ.get("RESEND_API_KEY")
    if not key:
        raise RuntimeError("RESEND_API_KEY not set")
    payload = json.dumps({
        "from": os.environ.get("EMAIL_FROM", FROM_ADDR),
        "to": to,
        "subject": subject,
        "text": body,
    }).encode()
    req = urllib.request.Request(
        RESEND_ENDPOINT, data=payload, method="POST",
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        if not (200 <= resp.status < 300):
            raise RuntimeError(f"Resend returned {resp.status}")


def _safe(to: list[str], subject: str, body: str) -> None:
    """Best-effort send: log and swallow any transport error."""
    try:
        _send(to, subject, body)
    except Exception as e:  # noqa: BLE001 - notifications must never break requests
        log.warning("email send failed to %s (%r): %s", to, subject, e)


def send_welcome(to_email: str, company: str) -> None:
    _safe([to_email],
          "You're in — Databricks Partner Use-Case Board",
          f"Thanks for joining as {company}.\n\n"
          "We'll email you whenever a new use case is posted that you might be "
          "able to help with. You can browse the board any time.")


def send_new_use_case(to_emails: list[str], title: str, description: str,
                      board_url: str) -> None:
    _safe(to_emails,
          f"New partner use case: {title}",
          f"{title}\n\n{description}\n\nSee it on the board: {board_url}")


def send_new_eoi(to_emails: list[str], company: str, title: str,
                 approach: str) -> None:
    _safe(to_emails,
          f"New response to “{title}” from {company}",
          f"{company} expressed interest in: {title}\n\n"
          f"Their approach:\n{approach}")
