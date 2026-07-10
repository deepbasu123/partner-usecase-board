"""Tests for the Lakebase access module against a real Postgres."""
import pytest
from portal_backend import db


def test_get_or_create_partner_is_idempotent():
    p1 = db.get_or_create_partner("p@example.com", "Acme GT", "Pat")
    p2 = db.get_or_create_partner("p@example.com", "Acme GT", "Pat")
    assert p1["id"] == p2["id"]
    assert p1["email"] == "p@example.com"
    assert p1["company"] == "Acme GT"


def test_list_open_use_cases_returns_seeded_case():
    cases = db.list_open_use_cases()
    assert len(cases) >= 1
    assert all(c["status"] == "open" for c in cases)
    assert any("Workforce Management" in c["title"] for c in cases)


def test_get_use_case_found_and_missing():
    uc = db.list_open_use_cases()[0]
    fetched = db.get_use_case(uc["id"])
    assert fetched["id"] == uc["id"]
    assert db.get_use_case("00000000-0000-0000-0000-000000000000") is None


def test_create_response_then_duplicate_raises():
    p = db.get_or_create_partner("dup@example.com", "Acme GT", None)
    uc = db.list_open_use_cases()[0]
    r = db.create_response(uc["id"], p["id"], "we'd tackle it with X")
    assert r["approach"] == "we'd tackle it with X"
    with pytest.raises(db.DuplicateResponse):
        db.create_response(uc["id"], p["id"], "again")


def test_list_all_partners_includes_created():
    db.get_or_create_partner("listed@example.com", "Beta GT", None)
    partners = db.list_all_partners()
    assert any(p["email"] == "listed@example.com" for p in partners)
