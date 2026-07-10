"""Tests for the shared email module. Transport (_send) is mocked, so these
run with no network and regardless of which transport Task 0 selects."""
from unittest.mock import patch

from portal_backend import email


def test_welcome_calls_send_with_company():
    with patch.object(email, "_send") as m:
        email.send_welcome("p@example.com", "Acme GT")
    assert m.called
    to, subject, body = m.call_args[0]
    assert to == ["p@example.com"]
    assert "Acme GT" in body


def test_new_use_case_addresses_all_partners_and_includes_link():
    with patch.object(email, "_send") as m:
        email.send_new_use_case(["a@x.com", "b@y.com"], "WFM ANZ",
                                 "desc here", "https://board.example.com")
    to, subject, body = m.call_args[0]
    assert to == ["a@x.com", "b@y.com"]
    assert "WFM ANZ" in subject
    assert "https://board.example.com" in body


def test_new_eoi_includes_company_and_approach():
    with patch.object(email, "_send") as m:
        email.send_new_eoi(["team@databricks.example"], "Acme GT",
                           "WFM ANZ", "we would use X and Y")
    to, subject, body = m.call_args[0]
    assert "Acme GT" in subject
    assert "we would use X and Y" in body


def test_send_failure_is_swallowed():
    # A transport error must never propagate into the request path.
    with patch.object(email, "_send", side_effect=RuntimeError("smtp down")):
        email.send_welcome("p@example.com", "Acme GT")  # must not raise
