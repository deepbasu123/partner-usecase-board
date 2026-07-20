"""Tests for the Gmail-SMTP-backed _send and the best-effort _safe wrapper.

No network: smtplib.SMTP_SSL is patched. These assert the message we build
(From, To, Subject, body), that Bcc recipients are delivered via the SMTP
envelope WITHOUT appearing in any header (recipient privacy), and that _safe
swallows failures so the triggering request never breaks.
"""
from unittest.mock import patch, MagicMock

import pytest

from board_api import email


def _fake_smtp():
    """A MagicMock standing in for the SMTP_SSL context manager."""
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.__exit__.return_value = False
    return smtp


def test_send_logs_in_and_sends_message(monkeypatch):
    monkeypatch.setattr(email, "GMAIL_USER", "sender@gmail.com")
    monkeypatch.setattr(email, "GMAIL_APP_PASSWORD", "app-pw-16-chars!")
    smtp = _fake_smtp()

    with patch("board_api.email.smtplib.SMTP_SSL", return_value=smtp) as ctor:
        email._send(["me@databricks.com"], "Hi", "Body text")

    # connected to Gmail SSL with a timeout
    ctor.assert_called_once()
    assert ctor.call_args[0][0] == "smtp.gmail.com"
    assert ctor.call_args[0][1] == 465
    # authenticated with the app password
    smtp.login.assert_called_once_with("sender@gmail.com", "app-pw-16-chars!")
    # message sent
    smtp.send_message.assert_called_once()
    sent_msg = smtp.send_message.call_args[0][0]
    assert sent_msg["Subject"] == "Hi"
    assert sent_msg["To"] == "me@databricks.com"
    assert "sender@gmail.com" in sent_msg["From"]
    assert sent_msg.get_content().strip() == "Body text"
    # envelope (to_addrs) covers the To recipient
    assert smtp.send_message.call_args.kwargs["to_addrs"] == ["me@databricks.com"]


def test_bcc_recipients_delivered_but_hidden_from_headers(monkeypatch):
    """Fan-out puts partners in the SMTP envelope but NEVER in a visible header."""
    monkeypatch.setattr(email, "GMAIL_USER", "sender@gmail.com")
    monkeypatch.setattr(email, "GMAIL_APP_PASSWORD", "app-pw")
    smtp = _fake_smtp()

    partners = ["a@x.com", "b@y.com", "c@z.com"]
    with patch("board_api.email.smtplib.SMTP_SSL", return_value=smtp):
        email.send_new_use_case(partners, "New brief", "desc", "https://board")

    sent_msg = smtp.send_message.call_args[0][0]
    envelope = smtp.send_message.call_args.kwargs["to_addrs"]
    # All partners are actually delivered (in the envelope)...
    for p in partners:
        assert p in envelope
    # ...but NONE of them leak into any header (no Bcc header, not in To).
    assert sent_msg["Bcc"] is None
    header_blob = str(sent_msg)
    for p in partners:
        assert p not in header_blob
    # Visible To is the sending account itself, so a valid To header exists.
    assert sent_msg["To"] == "sender@gmail.com"


def test_send_raises_without_credentials(monkeypatch):
    monkeypatch.setattr(email, "GMAIL_USER", "")
    monkeypatch.setattr(email, "GMAIL_APP_PASSWORD", "")
    with pytest.raises(RuntimeError):
        email._send(["me@databricks.com"], "Hi", "Body")


def test_send_raises_on_smtp_error(monkeypatch):
    monkeypatch.setattr(email, "GMAIL_USER", "sender@gmail.com")
    monkeypatch.setattr(email, "GMAIL_APP_PASSWORD", "app-pw")
    with patch("board_api.email.smtplib.SMTP_SSL", side_effect=OSError("smtp down")):
        with pytest.raises(OSError):
            email._send(["me@databricks.com"], "Hi", "Body")


def test_safe_swallows_send_failure(monkeypatch):
    """A transport failure must NOT propagate — signup/EOI stay 200/201."""
    monkeypatch.setattr(email, "GMAIL_USER", "")  # forces _send to raise
    monkeypatch.setattr(email, "GMAIL_APP_PASSWORD", "")
    email._safe(["me@databricks.com"], "Hi", "Body")  # must not raise


def test_fanout_noop_on_empty_recipients(monkeypatch):
    """No partners → no SMTP connection attempted at all."""
    monkeypatch.setattr(email, "GMAIL_USER", "sender@gmail.com")
    monkeypatch.setattr(email, "GMAIL_APP_PASSWORD", "app-pw")
    with patch("board_api.email.smtplib.SMTP_SSL") as ctor:
        email.send_new_use_case([], "t", "d", "u")
    ctor.assert_not_called()
