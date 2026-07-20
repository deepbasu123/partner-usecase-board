"""Tests for the Gmail-SMTP-backed email layer.

No network: smtplib.SMTP_SSL is patched. These assert that a fan-out sends ONE
individual message per recipient (each recipient's own address in the visible
To, never seeing the others), that single sends work, and that failures are
swallowed so the triggering request never breaks.
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


def _creds(monkeypatch):
    monkeypatch.setattr(email, "GMAIL_USER", "sender@gmail.com")
    monkeypatch.setattr(email, "GMAIL_APP_PASSWORD", "app-pw-16-chars!")


def test_send_logs_in_and_sends_single_message(monkeypatch):
    _creds(monkeypatch)
    smtp = _fake_smtp()
    with patch("board_api.email.smtplib.SMTP_SSL", return_value=smtp) as ctor:
        email._send(["me@databricks.com"], "Hi", "Body text")

    ctor.assert_called_once()
    assert ctor.call_args[0][0] == "smtp.gmail.com"
    assert ctor.call_args[0][1] == 465
    smtp.login.assert_called_once_with("sender@gmail.com", "app-pw-16-chars!")
    smtp.send_message.assert_called_once()
    sent = smtp.send_message.call_args[0][0]
    assert sent["To"] == "me@databricks.com"
    assert sent["Subject"] == "Hi"
    assert "sender@gmail.com" in sent["From"]
    assert sent.get_content().strip() == "Body text"


def test_fanout_sends_one_individual_message_per_recipient(monkeypatch):
    """Each partner gets their OWN message with only their address in To —
    nobody is in another's To, and there is no Bcc header at all."""
    _creds(monkeypatch)
    smtp = _fake_smtp()
    partners = ["a@x.com", "b@y.com", "c@z.com"]

    with patch("board_api.email.smtplib.SMTP_SSL", return_value=smtp):
        email.send_new_use_case(partners, "New brief", "desc", "https://board")

    # one message per recipient, single connection reused (login once)
    assert smtp.send_message.call_count == 3
    smtp.login.assert_called_once()

    tos = [call.args[0]["To"] for call in smtp.send_message.call_args_list]
    assert tos == partners  # order preserved, each its own To

    # No message leaks another recipient (own address only) and no Bcc header.
    for call in smtp.send_message.call_args_list:
        msg = call.args[0]
        assert msg["Bcc"] is None
        others = [p for p in partners if p != msg["To"]]
        blob = str(msg)
        for o in others:
            assert o not in blob


def test_fanout_dedupes_and_drops_empty(monkeypatch):
    _creds(monkeypatch)
    smtp = _fake_smtp()
    with patch("board_api.email.smtplib.SMTP_SSL", return_value=smtp):
        email.send_new_use_case(["a@x.com", "a@x.com", "", "b@y.com"], "t", "d", "u")
    tos = [c.args[0]["To"] for c in smtp.send_message.call_args_list]
    assert tos == ["a@x.com", "b@y.com"]  # deduped, empties dropped


def test_fanout_one_bad_recipient_does_not_stop_the_rest(monkeypatch):
    """A per-recipient send error is logged and skipped; others still go."""
    _creds(monkeypatch)
    smtp = _fake_smtp()
    # Fail only the middle recipient.
    def send_message(msg, *a, **k):
        if msg["To"] == "b@y.com":
            raise smtplib_error()
    import smtplib
    def smtplib_error():
        return smtplib.SMTPRecipientsRefused({"b@y.com": (550, b"nope")})
    smtp.send_message.side_effect = send_message

    with patch("board_api.email.smtplib.SMTP_SSL", return_value=smtp):
        email.send_new_use_case(["a@x.com", "b@y.com", "c@z.com"], "t", "d", "u")

    # attempted all three despite the middle one failing
    assert smtp.send_message.call_count == 3


def test_send_raises_without_credentials(monkeypatch):
    monkeypatch.setattr(email, "GMAIL_USER", "")
    monkeypatch.setattr(email, "GMAIL_APP_PASSWORD", "")
    with pytest.raises(RuntimeError):
        email._send(["me@databricks.com"], "Hi", "Body")


def test_safe_swallows_send_failure(monkeypatch):
    """A transport failure must NOT propagate — signup/EOI stay 200/201."""
    monkeypatch.setattr(email, "GMAIL_USER", "")  # forces _connect to raise
    monkeypatch.setattr(email, "GMAIL_APP_PASSWORD", "")
    email._safe(["me@databricks.com"], "Hi", "Body")  # must not raise


def test_fanout_swallows_connect_failure(monkeypatch):
    """A connect/login failure in a fan-out must not break the request either."""
    monkeypatch.setattr(email, "GMAIL_USER", "")
    monkeypatch.setattr(email, "GMAIL_APP_PASSWORD", "")
    email.send_new_use_case(["a@x.com"], "t", "d", "u")  # must not raise


def test_fanout_noop_on_empty_recipients(monkeypatch):
    """No recipients → no SMTP connection attempted at all."""
    _creds(monkeypatch)
    with patch("board_api.email.smtplib.SMTP_SSL") as ctor:
        email.send_new_use_case([], "t", "d", "u")
    ctor.assert_not_called()
