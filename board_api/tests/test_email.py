"""Tests for the Resend-backed _send and the best-effort _safe wrapper.

No network: urllib.request.urlopen is patched. These assert the request we
build (URL, auth header, JSON payload) and that _safe swallows failures.
"""
import json
from unittest.mock import patch, MagicMock

import pytest

from board_api import email


def _fake_resp(status=200, body=b'{"id":"re_123"}'):
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = body
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def test_send_posts_to_resend_with_auth_and_payload(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("EMAIL_FROM", "onboarding@resend.dev")
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["auth"] = req.get_header("Authorization")
        captured["ctype"] = req.get_header("Content-type")
        captured["body"] = json.loads(req.data.decode())
        return _fake_resp()

    with patch("board_api.email.urllib.request.urlopen", side_effect=fake_urlopen):
        email._send(["me@databricks.com"], "Hi", "Body text")

    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["method"] == "POST"
    assert captured["auth"] == "Bearer re_test_key"
    assert captured["ctype"] == "application/json"
    assert captured["body"] == {
        "from": "onboarding@resend.dev",
        "to": ["me@databricks.com"],
        "subject": "Hi",
        "text": "Body text",
    }


def test_send_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        email._send(["me@databricks.com"], "Hi", "Body")


def test_send_raises_on_non_2xx(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    import urllib.error
    with patch("board_api.email.urllib.request.urlopen",
               side_effect=__import__("urllib").error.HTTPError(
                   "https://api.resend.com/emails", 422, "Unprocessable", {}, None)):
        with pytest.raises(urllib.error.HTTPError):
            email._send(["me@databricks.com"], "Hi", "Body")


def test_safe_swallows_send_failure(monkeypatch):
    """A transport failure must NOT propagate — signup/EOI stay 200/201."""
    monkeypatch.delenv("RESEND_API_KEY", raising=False)  # forces _send to raise
    # Must not raise:
    email._safe(["me@databricks.com"], "Hi", "Body")
