"""Tests for the Lakebase access module against a real Postgres."""
import pytest


def test_get_or_create_partner_is_idempotent(db):
    p1 = db.get_or_create_partner("p@example.com", "Acme GT", "Pat")
    p2 = db.get_or_create_partner("p@example.com", "Acme GT", "Pat")
    assert p1["id"] == p2["id"]
    assert p1["email"] == "p@example.com"
    assert p1["company"] == "Acme GT"


def test_ids_are_strings_not_uuid_objects(db):
    # UUID objects break cookie signing (itsdangerous JSON) and JSON responses,
    # so db.py must return ids as plain strings.
    p = db.get_or_create_partner("strcheck@example.com", "Acme GT", None)
    assert isinstance(p["id"], str)
    uc = db.list_open_use_cases()[0]
    assert isinstance(uc["id"], str)
    r = db.create_response(uc["id"], p["id"], "x")
    assert isinstance(r["id"], str)
    assert isinstance(r["use_case_id"], str)
    assert isinstance(r["partner_id"], str)


def test_list_open_use_cases_returns_seeded_case(db):
    cases = db.list_open_use_cases()
    assert len(cases) >= 1
    assert all(c["status"] == "open" for c in cases)
    assert any("Workforce Management" in c["title"] for c in cases)


def test_get_use_case_found_and_missing(db):
    uc = db.list_open_use_cases()[0]
    fetched = db.get_use_case(uc["id"])
    assert fetched["id"] == uc["id"]
    assert db.get_use_case("00000000-0000-0000-0000-000000000000") is None


def test_create_response_then_duplicate_raises(db):
    p = db.get_or_create_partner("dup@example.com", "Acme GT", None)
    uc = db.list_open_use_cases()[0]
    r = db.create_response(uc["id"], p["id"], "we'd tackle it with X")
    assert r["approach"] == "we'd tackle it with X"
    with pytest.raises(db.DuplicateResponse):
        db.create_response(uc["id"], p["id"], "again")


def test_list_all_partners_includes_created(db):
    db.get_or_create_partner("listed@example.com", "Beta GT", None)
    partners = db.list_all_partners()
    assert any(p["email"] == "listed@example.com" for p in partners)


def test_get_partner_found_and_missing(db):
    p = db.get_or_create_partner("fetch@example.com", "Gamma GT", None)
    assert db.get_partner(p["id"])["company"] == "Gamma GT"
    assert db.get_partner("00000000-0000-0000-0000-000000000000") is None
