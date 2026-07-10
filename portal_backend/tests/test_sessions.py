"""Tests for signed-cookie sessions (no DB needed)."""
from portal_backend import sessions


def test_roundtrip():
    tok = sessions.make_session_cookie("abc-123")
    assert sessions.read_session_cookie(tok) == "abc-123"


def test_tampered_returns_none():
    tok = sessions.make_session_cookie("abc-123")
    assert sessions.read_session_cookie(tok + "x") is None


def test_garbage_returns_none():
    assert sessions.read_session_cookie("not-a-token") is None


def test_empty_returns_none():
    assert sessions.read_session_cookie("") is None


def test_cookie_name_constant():
    assert sessions.SESSION_COOKIE_NAME == "pub_session"
